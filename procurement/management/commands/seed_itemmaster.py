from django.core.management.base import BaseCommand
from django.db import transaction
from procurement.models import ItemMaster

SEED_ITEMS = [
    # --- PIPING & FITTINGS (AA = 10 مثال) ---
    dict(aa_level="10", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="050",
         description="HDPE Pipe PN10 DN50", unit="m", standard="ISO 4427", batch_reference=""),
    dict(aa_level="10", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="063",
         description="HDPE Pipe PN10 DN63", unit="m", standard="ISO 4427", batch_reference=""),
    dict(aa_level="10", bb_category="02", cc_subcategory="01", dd_itemtype="02", eee_attribute="050",
         description="Elbow 90° HDPE DN50", unit="pcs", standard="ISO 4427", batch_reference=""),
    dict(aa_level="10", bb_category="02", cc_subcategory="01", dd_itemtype="03", eee_attribute="050",
         description="Tee HDPE DN50", unit="pcs", standard="ISO 4427", batch_reference=""),

    # --- VALVES (AA = 20 مثال) ---
    dict(aa_level="20", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="050",
         description="Gate Valve DN50 PN16", unit="pcs", standard="EN 1074", batch_reference=""),
    dict(aa_level="20", bb_category="02", cc_subcategory="01", dd_itemtype="01", eee_attribute="050",
         description="Butterfly Valve DN50 PN16", unit="pcs", standard="EN 593", batch_reference=""),

    # --- ELECTRICAL (AA = 17 مثال) ---
    dict(aa_level="17", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="016",
         description="PVC Conduit 16mm", unit="m", standard="IEC", batch_reference=""),
    dict(aa_level="17", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="025",
         description="PVC Conduit 25mm", unit="m", standard="IEC", batch_reference=""),
    dict(aa_level="17", bb_category="02", cc_subcategory="01", dd_itemtype="01", eee_attribute="002",
         description="Electrical Cable 2mm", unit="m", standard="IEC", batch_reference=""),

    # --- CIVIL / CONCRETE (AA = 06 مثال) ---
    dict(aa_level="06", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="000",
         description="Cement 50kg Bag", unit="bag", standard="PS/EN", batch_reference=""),
    dict(aa_level="06", bb_category="02", cc_subcategory="01", dd_itemtype="01", eee_attribute="000",
         description="Rebar Steel Grade 60 - 12mm", unit="ton", standard="ASTM A615", batch_reference=""),
]

class Command(BaseCommand):
    help = "Seed ItemMaster with starter items"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Delete existing ItemMaster before seeding")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            ItemMaster.objects.all().delete()
            self.stdout.write(self.style.WARNING("ItemMaster cleared."))

        created = 0
        skipped = 0

        for data in SEED_ITEMS:
            obj, is_created = ItemMaster.objects.get_or_create(
                aa_level=data["aa_level"],
                bb_category=data["bb_category"],
                cc_subcategory=data["cc_subcategory"],
                dd_itemtype=data["dd_itemtype"],
                eee_attribute=data.get("eee_attribute", "000"),
                defaults=dict(
                    description=data["description"],
                    unit=data["unit"],
                    standard=data.get("standard", ""),
                    batch_reference=data.get("batch_reference", ""),
                    status="active",
                )
            )
            if is_created:
                created += 1
            else:
                # update description/unit if exists (optional)
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}, Skipped: {skipped}"))
