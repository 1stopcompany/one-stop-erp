"""
Warehouse stock rules in one place: every quantity change goes through
record_movement(), which locks the StockLevel row, refuses to take stock below
zero, and writes the ledger row -- views and signals never touch
StockLevel.quantity themselves.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import (
    Warehouse, StockLevel, StockMovement, PurchaseOrderLine, PurchaseRequisition,
    PurchaseRequisitionLine,
)

DEFAULT_WAREHOUSE_NAME = "Main Warehouse"


def fmt_qty(value) -> str:
    """5.00 -> '5', 12.50 -> '12.5' (for messages)."""
    return format(Decimal(value).normalize(), "f")


class StockError(Exception):
    """A stock change that would break a rule (e.g. issuing more than is on hand)."""


def default_warehouse() -> Warehouse:
    wh = Warehouse.objects.filter(is_active=True, project__isnull=True).order_by("id").first()
    return wh or Warehouse.objects.get_or_create(name=DEFAULT_WAREHOUSE_NAME)[0]


def warehouse_for_receipt(po) -> Warehouse:
    """Goods received against a PO go to its project's own site store if there is one, else the main warehouse."""
    site = Warehouse.objects.filter(is_active=True, project_id=po.project_id).order_by("id").first()
    return site or default_warehouse()


@transaction.atomic
def record_movement(warehouse, item, movement_type, quantity, user=None, project=None,
                    remarks="", po_receipt=None, clamp=False):
    """
    Apply a signed `quantity` to the warehouse's stock of `item`. Raises StockError
    if the result would be negative -- unless `clamp` is set (used when mirroring a
    receipt edit/delete, where refusing would block the receipt itself), in which
    case the change is trimmed to what is actually on hand.
    """
    quantity = Decimal(quantity)
    level, _ = StockLevel.objects.select_for_update().get_or_create(warehouse=warehouse, item=item)
    new_balance = level.quantity + quantity
    if new_balance < 0:
        if not clamp:
            raise StockError(
                f"Only {fmt_qty(level.quantity)} of {item.full_code} on hand in {warehouse.name} "
                f"-- cannot take out {fmt_qty(-quantity)}."
            )
        quantity = -level.quantity
        new_balance = Decimal("0")
    if quantity == 0:
        return None
    level.quantity = new_balance
    level.save(update_fields=["quantity", "updated_date"])
    return StockMovement.objects.create(
        warehouse=warehouse, item=item, movement_type=movement_type, quantity=quantity,
        balance_after=new_balance, project=project, po_receipt=po_receipt,
        remarks=remarks[:255], created_by=user,
    )


def sync_receipt(receipt) -> None:
    """Keep stock in step with a POReceipt: first save adds it, later edits add/remove the difference."""
    applied = receipt.stock_movements.aggregate(s=Sum("quantity"))["s"] or Decimal("0")
    delta = receipt.quantity_received - applied
    if delta == 0:
        return
    line = receipt.po_line
    existing = receipt.stock_movements.order_by("id").first()
    warehouse = existing.warehouse if existing else warehouse_for_receipt(line.po)
    record_movement(
        warehouse, line.item, "adjustment" if existing else "receipt", delta,
        user=receipt.received_by, project=line.po.project, po_receipt=receipt,
        remarks=f"PO {line.po.po_number}" + (" (receipt edited)" if existing else ""), clamp=True,
    )


def reverse_receipt(receipt_id, line, user=None) -> None:
    """A deleted POReceipt takes its goods back out of stock (as far as they are still there)."""
    moves = StockMovement.objects.filter(po_receipt_id=receipt_id)
    applied = moves.aggregate(s=Sum("quantity"))["s"] or Decimal("0")
    first = moves.order_by("id").first()
    if applied <= 0 or not first:
        return
    record_movement(
        first.warehouse, line.item, "adjustment", -applied, user=user, project=line.po.project,
        remarks=f"PO {line.po.po_number} receipt deleted", clamp=True,
    )


# ---------- reporting ----------

def on_order_by_item() -> dict:
    """
    Quantity already on its way per item, so the re-order list doesn't ask for
    something that has already been requested/ordered: outstanding PO lines, plus
    PR lines that are approved/in progress but haven't become a PO line yet.
    """
    totals: dict = {}
    open_po = PurchaseOrderLine.objects.filter(
        po__status__in=["draft", "sent", "confirmed", "partial_received"],
        quantity_received__lt=F("quantity_ordered"),
    ).values_list("item_id", "quantity_ordered", "quantity_received")
    for item_id, ordered, received in open_po:
        totals[item_id] = totals.get(item_id, Decimal("0")) + (ordered - received)
    pending_pr = PurchaseRequisitionLine.objects.filter(
        pr__status__in=["submitted", "approved", "in_procurement"], po_lines__isnull=True,
    ).values_list("item_id", "quantity_requested")
    for item_id, qty in pending_pr:
        totals[item_id] = totals.get(item_id, Decimal("0")) + qty
    return totals


def low_stock_levels(warehouse=None):
    """StockLevels at or below their minimum (limit set), most urgent first."""
    qs = StockLevel.objects.select_related("item", "warehouse").filter(
        min_quantity__gt=0, quantity__lte=F("min_quantity"), warehouse__is_active=True,
    )
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    return qs.order_by("quantity", "item__full_code")


@transaction.atomic
def create_replenishment_pr(level_quantities, project, user, required_date=None):
    """
    Draft PR for the given [(StockLevel, quantity)] -- the "must be ordered from the
    suppliers" step. Left as a draft so it goes through the normal
    submit -> approve -> RFQ -> PO workflow.
    """
    pr = PurchaseRequisition.objects.create(
        project=project, required_date=required_date or (timezone.localdate() + timedelta(days=7)),
        requested_by=user, status="draft",
        remarks="Warehouse re-order: items at or below their minimum stock level.",
    )
    for order, (level, qty) in enumerate(level_quantities):
        PurchaseRequisitionLine.objects.create(
            pr=pr, item=level.item, quantity_requested=qty, unit=level.item.unit or "pcs",
            remarks=f"{level.warehouse.name}: {fmt_qty(level.quantity)} on hand, minimum {fmt_qty(level.min_quantity)}",
            order=order,
        )
    return pr
