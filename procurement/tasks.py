from __future__ import annotations

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count

from .models import PurchaseOrder, PurchaseRequisition


@shared_task
def procurement_kpi_snapshot():
    """
    Example background KPI task (safe).
    """
    last_30 = timezone.now() - timedelta(days=30)
    prs = PurchaseRequisition.objects.filter(created_date__gte=last_30).count()
    pos = PurchaseOrder.objects.filter(created_date__gte=last_30).count()
    by_status = list(PurchaseOrder.objects.values("status").annotate(c=Count("id")).order_by("-c"))
    return {"prs_last_30": prs, "pos_last_30": pos, "po_by_status": by_status}
