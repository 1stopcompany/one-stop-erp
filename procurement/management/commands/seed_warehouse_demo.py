"""
Seed demo warehouse stock so the Warehouse pages have something to show: a
separate "[DEMO] Store" warehouse holding real catalog items in every state the
page distinguishes (comfortably OK, exactly at the minimum, below it, and out
of stock), with an opening balance plus a few issues to a real project so the
Movements ledger isn't empty.

The demo warehouse is deliberately NOT linked to any project and is created
after the real "Main Warehouse", so goods received against real POs never land
in it. Everything is marked "[DEMO]" and removable.

Usage:
    python manage.py seed_warehouse_demo            # add (skips if already seeded)
    python manage.py seed_warehouse_demo --clear    # remove all demo stock again
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from procurement.models import ItemMaster, Warehouse, StockLevel, StockMovement
from procurement.services_warehouse import record_movement, default_warehouse
from projects.models import Project

DEMO_MARK = "[DEMO]"
DEMO_WAREHOUSE = "[DEMO] Store"

# full_code, opening balance, issued to a project, minimum, quantity to order when low
SCENARIOS = [
    ("OS.03.04.01.01.000", 500, 100, 100, 300),  # Cement            -> 400, OK
    ("OS.03.09.01.02.012", 20, 8, 10, 15),        # Rebar             -> 12, OK (close)
    ("OS.09.03.01.01.000", 60, 25, 40, 100),      # Ceramic tiles     -> 35, below minimum
    ("OS.09.04.02.01.000", 45, 25, 20, 60),       # Interior paint    -> 20, exactly at minimum
    ("OS.09.04.03.01.000", 30, 30, 30, 80),       # Exterior paint    -> 0, out of stock
    ("OS.05.02.11.01.002", 80, 20, 50, 40),       # Handrail pipe     -> 60, OK
    ("OS.03.08.01.01.004", 20, 12, 15, 25),       # Steel props       -> 8, below minimum
    ("OS.04.03.01.04.001", 600, 100, 200, 500),   # Pipe spacer       -> 500, OK
]


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) demo warehouse stock"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo warehouse and all its stock")

    @transaction.atomic
    def handle(self, *args, **options):
        warehouse = Warehouse.objects.filter(name=DEMO_WAREHOUSE).first()

        if options["clear"]:
            if not warehouse:
                self.stdout.write("No demo warehouse to remove.")
                return
            moves = StockMovement.objects.filter(warehouse=warehouse).delete()[0]
            levels = StockLevel.objects.filter(warehouse=warehouse).delete()[0]
            warehouse.delete()
            self.stdout.write(self.style.SUCCESS(f"Removed demo warehouse ({levels} stock rows, {moves} movements)."))
            return

        if warehouse and StockMovement.objects.filter(warehouse=warehouse).exists():
            self.stdout.write("Demo warehouse stock already present -- nothing to do (use --clear to reset).")
            return

        items = {i.full_code: i for i in ItemMaster.objects.filter(full_code__in=[s[0] for s in SCENARIOS])}
        if not items:
            self.stderr.write(self.style.ERROR("None of the demo catalog items exist -- run import_item_master first."))
            return

        default_warehouse()  # make sure the real general warehouse exists (and comes first) before the demo one
        warehouse = warehouse or Warehouse.objects.create(name=DEMO_WAREHOUSE, location="Demo data - safe to delete")
        project = Project.objects.order_by("id").first()
        user = get_user_model().objects.filter(is_superuser=True).order_by("id").first()

        seeded = 0
        for code, opening, issued, minimum, reorder in SCENARIOS:
            item = items.get(code)
            if not item:
                self.stdout.write(self.style.WARNING(f"Skipping {code}: not in the item catalog."))
                continue
            record_movement(warehouse, item, "adjustment", Decimal(opening), user=user,
                            remarks=f"{DEMO_MARK} opening balance")
            if issued:
                record_movement(warehouse, item, "issue", -Decimal(issued), user=user, project=project,
                                remarks=f"{DEMO_MARK} issued to site")
            StockLevel.objects.filter(warehouse=warehouse, item=item).update(
                min_quantity=Decimal(minimum), reorder_quantity=Decimal(reorder),
            )
            seeded += 1

        low = StockLevel.objects.filter(warehouse=warehouse, min_quantity__gt=0, quantity__lte=F("min_quantity")).count()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {seeded} items in '{DEMO_WAREHOUSE}' ({low} at or below minimum). Remove with: seed_warehouse_demo --clear"
        ))
