"""
Warehouse section of Procurement: stock on hand, minimum-stock limits, issuing
to projects, stock-take adjustments, the movement ledger, and the re-order list
that turns low stock into a draft purchase requisition.

Anyone logged in can see stock; changing it (limits, issue, adjust, re-order,
warehouses) is limited to procurement officers and admins.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms_warehouse import (
    WarehouseForm, StockLimitForm, StockIssueForm, StockAdjustForm, ReorderForm,
)
from .models import Warehouse, StockLevel, StockMovement, ItemMaster
from .services_warehouse import (
    StockError, record_movement, low_stock_levels, on_order_by_item,
    create_replenishment_pr, default_warehouse, fmt_qty,
)
from .views import _can_work_procurement


def _deny():
    return HttpResponseForbidden("Only procurement officers and admins can change warehouse stock.")


def _form_page(request, form, title):
    return render(request, "procurement/form.html", {"form": form, "title": title})


def _warn_if_low(request, warehouse, item):
    level = StockLevel.objects.filter(warehouse=warehouse, item=item).first()
    if level and level.is_low:
        messages.warning(
            request,
            f"{item.full_code} is now at {fmt_qty(level.quantity)} in {warehouse.name} -- at or below its minimum of "
            f"{fmt_qty(level.min_quantity)}. It must be re-ordered from the suppliers (see Items to re-order).",
        )


# ---------------------------------------------------------------- stock on hand

@login_required
def stock_list(request):
    # Make sure at least one warehouse exists so the page (and receiving) always has somewhere to put stock.
    default_warehouse()

    warehouse_id = request.GET.get("warehouse", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()

    levels = StockLevel.objects.select_related("item", "warehouse").filter(warehouse__is_active=True)
    # A row only matters if there is stock or a limit -- skip empty leftovers.
    levels = levels.filter(Q(quantity__gt=0) | Q(min_quantity__gt=0))
    if warehouse_id.isdigit():
        levels = levels.filter(warehouse_id=int(warehouse_id))
    if q:
        levels = levels.filter(
            Q(item__full_code__icontains=q) | Q(item__description__icontains=q) | Q(item__barcode_value__iexact=q)
        )
    if status == "out":
        levels = levels.filter(min_quantity__gt=0, quantity__lte=0)
    elif status == "low":
        levels = levels.filter(min_quantity__gt=0, quantity__lte=F("min_quantity"))
    elif status == "ok":
        levels = levels.exclude(min_quantity__gt=0, quantity__lte=F("min_quantity"))

    on_order = on_order_by_item()
    rows = []
    for level in levels:
        level.on_order = on_order.get(level.item_id, Decimal("0"))
        rows.append(level)

    all_levels = StockLevel.objects.filter(warehouse__is_active=True).filter(Q(quantity__gt=0) | Q(min_quantity__gt=0))
    low_qs = all_levels.filter(min_quantity__gt=0, quantity__lte=F("min_quantity"))
    context = {
        "rows": rows,
        "warehouses": Warehouse.objects.filter(is_active=True),
        "warehouse_id": warehouse_id, "status": status, "q": q,
        "total_items": all_levels.count(),
        "low_count": low_qs.count(),
        "out_count": low_qs.filter(quantity__lte=0).count(),
        "can_edit": _can_work_procurement(request.user),
    }
    return render(request, "procurement/warehouse/stock_list.html", context)


# ---------------------------------------------------------------- limits / issue / adjust

@login_required
def stock_limit(request):
    if not _can_work_procurement(request.user):
        return _deny()
    initial = {}
    if request.GET.get("item", "").isdigit():
        initial["item"] = int(request.GET["item"])
    if request.GET.get("warehouse", "").isdigit():
        initial["warehouse"] = int(request.GET["warehouse"])
    if "item" in initial and "warehouse" in initial:
        existing = StockLevel.objects.filter(item_id=initial["item"], warehouse_id=initial["warehouse"]).first()
        if existing:
            initial.update(min_quantity=existing.min_quantity, reorder_quantity=existing.reorder_quantity)

    form = StockLimitForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        level, _ = StockLevel.objects.get_or_create(warehouse=cd["warehouse"], item=cd["item"])
        level.min_quantity = cd["min_quantity"]
        level.reorder_quantity = cd["reorder_quantity"]
        level.save(update_fields=["min_quantity", "reorder_quantity", "updated_date"])
        messages.success(request, f"Minimum stock for {cd['item'].full_code} in {cd['warehouse'].name} set to {fmt_qty(cd['min_quantity'])}.")
        _warn_if_low(request, cd["warehouse"], cd["item"])
        return redirect("procurement:stock_list")
    return _form_page(request, form, "Set Minimum Stock")


@login_required
def stock_issue(request):
    if not _can_work_procurement(request.user):
        return _deny()
    initial = {}
    if request.GET.get("item", "").isdigit():
        initial["item"] = int(request.GET["item"])
    if request.GET.get("warehouse", "").isdigit():
        initial["warehouse"] = int(request.GET["warehouse"])

    form = StockIssueForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        try:
            record_movement(
                cd["warehouse"], cd["item"], "issue", -cd["quantity"], user=request.user,
                project=cd["project"], remarks=cd["remarks"],
            )
        except StockError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Issued {fmt_qty(cd['quantity'])} of {cd['item'].full_code} to {cd['project']}.")
            _warn_if_low(request, cd["warehouse"], cd["item"])
            return redirect("procurement:stock_list")
    return _form_page(request, form, "Issue Stock to Project")


@login_required
def stock_adjust(request):
    if not _can_work_procurement(request.user):
        return _deny()
    initial = {}
    if request.GET.get("item", "").isdigit():
        initial["item"] = int(request.GET["item"])
    if request.GET.get("warehouse", "").isdigit():
        initial["warehouse"] = int(request.GET["warehouse"])

    form = StockAdjustForm(request.POST or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        current = (
            StockLevel.objects.filter(warehouse=cd["warehouse"], item=cd["item"])
            .values_list("quantity", flat=True).first() or Decimal("0")
        )
        delta = cd["counted_quantity"] - current
        if delta == 0:
            messages.info(request, "The counted quantity equals what the system already shows -- nothing to change.")
            return redirect("procurement:stock_list")
        record_movement(
            cd["warehouse"], cd["item"], "adjustment", delta, user=request.user,
            remarks=cd["remarks"] or "Stock count",
        )
        messages.success(request, f"{cd['item'].full_code} in {cd['warehouse'].name} set to {fmt_qty(cd['counted_quantity'])} (was {fmt_qty(current)}).")
        _warn_if_low(request, cd["warehouse"], cd["item"])
        return redirect("procurement:stock_list")
    return _form_page(request, form, "Stock Count / Opening Balance")


# ---------------------------------------------------------------- ledger

@login_required
def stock_movements(request):
    qs = StockMovement.objects.select_related("item", "warehouse", "project", "created_by")
    warehouse_id = request.GET.get("warehouse", "")
    mtype = request.GET.get("type", "")
    item_id = request.GET.get("item", "")
    if warehouse_id.isdigit():
        qs = qs.filter(warehouse_id=int(warehouse_id))
    if mtype:
        qs = qs.filter(movement_type=mtype)
    item = None
    if item_id.isdigit():
        item = ItemMaster.objects.filter(pk=int(item_id)).first()
        qs = qs.filter(item_id=int(item_id))
    page = Paginator(qs, 100).get_page(request.GET.get("page"))
    return render(request, "procurement/warehouse/movements.html", {
        "page": page, "warehouses": Warehouse.objects.all(), "types": StockMovement.TYPES,
        "warehouse_id": warehouse_id, "type": mtype, "item": item,
    })


# ---------------------------------------------------------------- re-order

@login_required
def reorder_list(request):
    """Items at or below their minimum, and the button that turns them into a draft PR."""
    can_edit = _can_work_procurement(request.user)
    on_order = on_order_by_item()

    levels = list(low_stock_levels())
    for level in levels:
        level.on_order = on_order.get(level.item_id, Decimal("0"))
        # Already fully covered by an order/request in progress -> don't ask for it again by default.
        level.covered = level.on_order >= level.suggested_order_quantity
    form = ReorderForm(request.POST or None, initial={"required_date": timezone.localdate() + timedelta(days=7)})

    if request.method == "POST":
        if not can_edit:
            return _deny()
        selected = []
        by_id = {str(level.pk): level for level in levels}
        for pk in request.POST.getlist("sel"):
            level = by_id.get(pk)
            if not level:
                continue
            try:
                qty = Decimal(request.POST.get(f"qty_{pk}", "").strip())
            except (InvalidOperation, ValueError):
                continue
            if qty > 0:
                selected.append((level, qty))
        if not selected:
            messages.error(request, "Tick at least one item and give it a quantity above zero.")
        elif form.is_valid():
            pr = create_replenishment_pr(
                selected, form.cleaned_data["project"], request.user, form.cleaned_data["required_date"],
            )
            messages.success(
                request,
                f"Draft purchase requisition {pr.pr_number} created with {len(selected)} item(s). "
                f"Review it and submit it to send it through approval and the suppliers.",
            )
            return redirect("procurement:pr_detail", pk=pr.pk)

    return render(request, "procurement/warehouse/reorder.html", {
        "levels": levels, "form": form, "can_edit": can_edit,
    })


# ---------------------------------------------------------------- warehouses

@login_required
def warehouse_list(request):
    default_warehouse()
    return render(request, "procurement/warehouse/warehouse_list.html", {
        "warehouses": Warehouse.objects.select_related("project"),
        "can_edit": _can_work_procurement(request.user),
    })


@login_required
def warehouse_form(request, pk=None):
    if not _can_work_procurement(request.user):
        return _deny()
    instance = get_object_or_404(Warehouse, pk=pk) if pk else None
    form = WarehouseForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        wh = form.save()
        messages.success(request, f"Warehouse {wh.name} saved.")
        return redirect("procurement:warehouse_list")
    return _form_page(request, form, "Edit Warehouse" if instance else "New Warehouse")
