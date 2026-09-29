"""
Seed a demo project that shows every state of the pricing / cost-control pages: a priced BOQ
(phases and sub-items, budget and contract prices), measured progress, and purchase orders
charged to BOQ items in different states, with site receipts -- so the Budget vs Actual
numbers and colours can be seen, not imagined.

Everything lives in ONE new project, "[DEMO] Cost Control Tower", with its own supplier and its
own site store, so no real project, order or warehouse stock is touched. Remove it all with --clear.

Usage:
    python manage.py seed_costing_demo            # add (skips if already seeded)
    python manage.py seed_costing_demo --clear    # remove the demo project and everything under it
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from procurement.models import (
    ItemMaster, POReceipt, PurchaseOrder, PurchaseOrderLine, StockLevel, StockMovement, Vendor, Warehouse,
)
from projects.models import Project
from reports.progress_models import (
    ProjectPhase, ProjectPhaseProgressEntry, ProjectPhaseSubItem, recalculate_weights_from_contract,
)

SYMBOL = "DEMOCC"
PROJECT_NAME = "[DEMO] Cost Control Tower"
VENDOR_NAME = "[DEMO] Supplier"
STORE_NAME = "[DEMO] Cost Control Tower store"
CIVIL, ELEC, EXT = "Civil Works", "Electrical Works", "External Works"

# phase code, section, Arabic, English, [(sub code, Arabic, English, unit, qty, budget price, contract price, progress %)]
#   or, for a phase priced as a whole:  (unit, qty, budget price, contract price, progress %)
PHASES = [
    ("1", CIVIL, "الأساسات", "Foundations", [
        ("1.1", "أعمال الحفر", "Excavation", "m3", 300, 40, 55, 100),
        ("1.2", "أعمال الخرسانة", "Concrete works", "m3", 120, 420, 560, 100)]),
    ("2", CIVIL, "الهيكل الإنشائي", "Structure", [
        ("2.1", "أعمدة وأسقف", "Columns and slabs", "m3", 250, 480, 640, 55),
        ("2.2", "بناء الطوب", "Blockwork", "m2", 800, 55, 75, 40)]),
    ("3", CIVIL, "التشطيبات", "Finishes", [
        ("3.1", "أعمال البلاط", "Tiling", "m2", 600, 75, 105, 10),
        ("3.2", "الدهانات", "Painting", "m2", 1200, 14, 22, 0)]),
    ("4", ELEC, "نقاط كهرباء", "Electrical points", ("No.", 80, 150, 210, 30)),
    ("5", EXT, "تبليط خارجي", "Paving", ("m2", 300, 90, 130, 0)),
]

# item code, BOQ item code it is charged to (None = not assigned), qty ordered, unit price, PO status, qty received
PURCHASES = [
    ("OS.03.08.01.01.004", "1.1", 100, 45, "confirmed", 100),   # Excavation       -> under cost
    ("OS.03.09.01.02.012", "1.2", 20, 2450, "confirmed", 20),   # Concrete works   -> on track
    ("OS.03.04.01.01.000", "2.1", 3000, 25, "confirmed", 3000), # Columns & slabs  -> over cost
    ("OS.05.02.11.01.002", "2.2", 700, 25, "confirmed", 700),   # Blockwork        -> on track
    ("OS.09.03.01.01.000", "3.1", 500, 60, "sent", 0),          # Tiling           -> ordered, not received
    ("OS.09.04.03.01.000", "4", 260, 60, "confirmed", 40),      # Electrical pts   -> ordered more than budget
    ("OS.04.03.01.04.001", "5", 500, 8, "confirmed", 500),      # Paving           -> spent, no progress recorded
    ("OS.09.04.02.01.000", None, 50, 22, "confirmed", 20),      # (unassigned)     -> shown in the warning
]


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) a demo project for the pricing / cost-control pages"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo project and everything under it")

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=SYMBOL).first()

        if options["clear"]:
            self._clear(project)
            return
        if project:
            self.stdout.write("Demo project already present -- nothing to do (use --clear to reset).")
            return

        codes = [p[0] for p in PURCHASES]
        items = {i.full_code: i for i in ItemMaster.objects.filter(full_code__in=codes)}
        missing = sorted(set(codes) - set(items))
        if missing:
            self.stderr.write(self.style.ERROR(f"Catalog items missing: {', '.join(missing)} -- run import_item_master first."))
            return

        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).order_by("id").first()
        project = Project.objects.create(
            name=PROJECT_NAME, project_symbol=SYMBOL, contract_number="DEMO-CC-1", client_name="[DEMO] Client",
            start_date=date.today() - timedelta(days=120), status="active",
            manager=User.objects.filter(role="project_manager").order_by("id").first(),
            site_engineer=User.objects.filter(role="site_engineer").order_by("id").first(), created_by=admin,
            description="Demo data for the pricing and cost-control pages. Safe to delete: seed_costing_demo --clear",
        )
        # A site store of its own, so demo receipts never land in a real warehouse.
        Warehouse.objects.create(name=STORE_NAME, project=project, location="Demo data - safe to delete")
        vendor = Vendor.objects.create(name=VENDOR_NAME, is_active=True)

        # ---- the priced BOQ
        by_code = {}
        for order, (code, section, name_ar, name_en, body) in enumerate(PHASES, start=1):
            if isinstance(body, tuple):  # priced as a whole
                unit, qty, budget_price, contract_price, progress = body
                phase = ProjectPhase.objects.create(
                    project=project, code=code, section=section, name_ar=name_ar, name_en=name_en, order=order,
                    weight_percentage=0, unit=unit, quantity=Decimal(qty),
                    budget_unit_price=Decimal(budget_price), contract_unit_price=Decimal(contract_price),
                )
                phase.sync_whole_item()
                sub = phase.sub_items.get(is_whole=True)
                self._progress(sub, progress, admin)
                by_code[code] = sub
                continue
            phase = ProjectPhase.objects.create(
                project=project, code=code, section=section, name_ar=name_ar, name_en=name_en, order=order,
                weight_percentage=0,
            )
            for i, (sub_code, sub_ar, sub_en, unit, qty, budget_price, contract_price, progress) in enumerate(body, start=1):
                sub = ProjectPhaseSubItem.objects.create(
                    phase=phase, code=sub_code, name_ar=sub_ar, name_en=sub_en, weight_percentage=0, order=i,
                    unit=unit, quantity=Decimal(qty), budget_unit_price=Decimal(budget_price),
                    contract_unit_price=Decimal(contract_price),
                )
                self._progress(sub, progress, admin)
                by_code[sub_code] = sub
        recalculate_weights_from_contract(project)

        # ---- purchases charged to BOQ items
        for item_code, boq_code, ordered, price, status, received in PURCHASES:
            item = items[item_code]
            po = PurchaseOrder.objects.create(
                project=project, vendor=vendor, delivery_date=date.today() + timedelta(days=14),
                status=status, remarks="[DEMO]", created_by=admin,
            )
            line = PurchaseOrderLine.objects.create(
                po=po, item=item, sub_item=by_code.get(boq_code), quantity_ordered=ordered,
                unit=item.unit or "pcs", unit_price=price,
            )
            if received:
                POReceipt.objects.create(po_line=line, quantity_received=received, received_by=admin, remarks="[DEMO]")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{PROJECT_NAME}': {len(PHASES)} phases, {len(by_code)} priced BOQ items, purchase orders and receipts. "
            f"Open Cost Control > Budget vs Actual > {PROJECT_NAME}. Remove with: seed_costing_demo --clear"
        ))

    @staticmethod
    def _progress(sub_item, percentage, user):
        ProjectPhaseProgressEntry.objects.create(
            sub_item=sub_item, report_date=date.today(), execution_percentage=percentage, recorded_by=user, notes="[DEMO]",
        )

    def _clear(self, project):
        if not project:
            self.stdout.write("No demo project to remove.")
            return
        from blueprints.demo import clear as clear_drawings_demo
        clear_drawings_demo(project)   # its drawing / insurance / document files too, before the rows cascade away
        store = Warehouse.objects.filter(name=STORE_NAME).first()
        if store:
            # Ledger rows protect their warehouse, so they go first.
            StockMovement.objects.filter(warehouse=store).delete()
            StockLevel.objects.filter(warehouse=store).delete()
            store.delete()
        project.delete()  # cascades: BOQ phases, progress, purchase orders, receipts
        Vendor.objects.filter(name=VENDOR_NAME).delete()
        self.stdout.write(self.style.SUCCESS("Removed the demo project, its supplier and its site store."))
