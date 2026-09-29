"""Helpers for tests that need a project the readiness rule lets work on (see projects.readiness)."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from reports.progress_models import ProjectPhase


def add_insurance(project, days=200, document="insurance/test-policy.pdf"):
    """A valid policy. The document is only a stored file name: no file is written to disk."""
    return project.insurances.create(
        policy_type="car", insurer="Test Insurer", policy_number=f"POL-{project.pk}-{project.insurances.count() + 1}",
        start_date=timezone.localdate() - timedelta(days=30), end_date=timezone.localdate() + timedelta(days=days), document=document,
    )


def price_boq(project, code="READY-1"):
    """One phase priced as a whole (quantity, cost price and contract price all set)."""
    phase = ProjectPhase.objects.create(
        project=project, code=code, name_ar="بند جاهز", weight_percentage=100, order=1,
        unit="m2", quantity=Decimal("10"), budget_unit_price=Decimal("5"), contract_unit_price=Decimal("8"),
    )
    phase.sync_whole_item()
    return phase


def make_ready(project):
    """Valid insurance and a fully priced BOQ, on a project that is not in Planning."""
    add_insurance(project)
    price_boq(project)
    return project
