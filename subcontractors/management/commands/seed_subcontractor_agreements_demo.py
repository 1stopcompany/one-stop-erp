"""
Seed demo Musana'a subcontractor agreements against the existing "[DEMO] Cost Control Tower"
project (seed_costing_demo), one in each real-world state, so the page and its effect on Cost
Control can be seen, not imagined:
    - Draft       -- not committed yet, doesn't show in Cost Control
    - Active       -- committed, partially paid
    - Completed    -- committed, fully paid
    - Terminated   -- no longer committed, even though it once had lines

Requires seed_costing_demo to have been run first (same project, same priced BOQ). Safe to
delete with --clear (removes only the agreements/vendor this command created).

Usage:
    python manage.py seed_subcontractor_agreements_demo
    python manage.py seed_subcontractor_agreements_demo --clear
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from procurement.models import Vendor
from projects.models import Project
from reports.progress_models import ProjectPhaseSubItem
from subcontractors.models import SubcontractorAgreement, SubcontractorAgreementLine, SubcontractorAgreementPayment

SYMBOL = "DEMOCC"
VENDOR_NAME = "[DEMO] ABC Specialized Contracting"

# BOQ item code, scope description, unit price, quantity (None = the sub-item's own quantity), status, paid so far
AGREEMENTS = [
    ("2.2", "Blockwork labour -- supply of skilled masons for all blockwork", 62, None, "active", 20000),
    ("1.1", "Bulk excavation subcontract -- completed and closed out", 42, None, "completed", None),  # paid in full below
    ("5", "External paving subcontract -- awaiting signature", 95, None, "draft", None),
    ("3.1", "Tiling subcontract -- terminated, replaced by direct procurement", 68, 200, "terminated", 3000),
]


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) demo subcontractor (Musana'a) agreements on the demo Cost Control project"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo agreements and their vendor")

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=SYMBOL).first()
        if options["clear"]:
            self._clear(project)
            return
        if not project:
            self.stderr.write(self.style.ERROR("Demo project 'DEMOCC' not found -- run seed_costing_demo first."))
            return
        if SubcontractorAgreement.objects.filter(project=project, vendor__name=VENDOR_NAME).exists():
            self.stdout.write("Demo agreements already present -- nothing to do (use --clear to reset).")
            return

        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).order_by("id").first()
        vendor, _ = Vendor.objects.get_or_create(name=VENDOR_NAME, defaults={"is_active": True})

        sub_items = {s.code: s for s in ProjectPhaseSubItem.objects.filter(phase__project=project)}

        for boq_code, scope, unit_price, qty, status, paid in AGREEMENTS:
            sub = sub_items.get(boq_code)
            if not sub:
                self.stderr.write(self.style.WARNING(f"BOQ item '{boq_code}' not found on the demo project -- skipped."))
                continue
            agreement = SubcontractorAgreement.objects.create(
                project=project, vendor=vendor, scope_description=f"[DEMO] {scope}",
                start_date=date.today() - timedelta(days=60), end_date=date.today() + timedelta(days=30),
                created_by=admin,
            )
            SubcontractorAgreementLine.objects.create(
                agreement=agreement, sub_item=sub, description=sub.name_en or sub.name_ar,
                unit=sub.unit, quantity=qty or sub.quantity, unit_price=unit_price,
            )
            agreement.refresh_from_db()
            if status != "draft":
                agreement.status = status
                agreement.save(update_fields=["status"])
            amount_paid = agreement.total_value if status == "completed" else paid
            if amount_paid:
                SubcontractorAgreementPayment.objects.create(
                    agreement=agreement, amount=amount_paid, payment_date=date.today() - timedelta(days=5),
                    notes="[DEMO] Final payment on close-out" if status == "completed" else "[DEMO] Progress payment",
                    created_by=admin,
                )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(AGREEMENTS)} demo subcontractor agreements (draft / active / completed / terminated) on "
            f"'{project.name}'. Open BOQ & Cost > Subcontractor Agreements, or Cost Control > Budget vs Actual to "
            f"see their effect. Remove with: seed_subcontractor_agreements_demo --clear"
        ))

    def _clear(self, project):
        if not project:
            self.stdout.write("No demo project found -- nothing to remove.")
            return
        deleted, _ = SubcontractorAgreement.objects.filter(project=project, vendor__name=VENDOR_NAME).delete()
        Vendor.objects.filter(name=VENDOR_NAME).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed the demo subcontractor agreements ({deleted} rows) and their vendor."))
