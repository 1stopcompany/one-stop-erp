from __future__ import annotations

from decimal import Decimal
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.db.models import Sum

from .models import POReceipt


@receiver([post_save, post_delete], sender=POReceipt)
def sync_po_line_received_qty(sender, instance: POReceipt, **kwargs):
    po_line = instance.po_line
    total = po_line.receipts.aggregate(s=Sum("quantity_received"))["s"] or Decimal("0")
    po_line.quantity_received = total
    po_line.save(update_fields=["quantity_received"])
    po_line.po.refresh_status_from_lines()


@receiver(post_save, sender=POReceipt)
def add_receipt_to_stock(sender, instance: POReceipt, raw=False, **kwargs):
    """Goods received against a PO go into warehouse stock (edits adjust it by the difference)."""
    if raw:
        return
    from .services_warehouse import sync_receipt
    sync_receipt(instance)


@receiver(pre_delete, sender=POReceipt)
def remove_receipt_from_stock(sender, instance: POReceipt, **kwargs):
    # pre_delete, not post_delete: StockMovement.po_receipt is SET_NULL, so by post_delete
    # the link back to this receipt's stock movements is already gone.
    from .services_warehouse import reverse_receipt
    reverse_receipt(instance.pk, instance.po_line)
