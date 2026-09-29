"""
Import the item classification hierarchy (Family -> Group ->
Classification -> ItemType) from the company's own workbook ("FINAL_With_
Validation-R02.xlsx"), sheets "FAMILY", "Group", "Classification",
"Brand" -- so the Add/Edit Item form can offer a real cascading "pick by
name" list instead of asking someone to already know the raw digit code
for each level (see procurement.models.ItemFamily and friends).

Sheet "Brand" is the source workbook's own (misleading) name for the
dd_itemtype tier -- its actual values are subcategory-like names ("Nails",
"Cutting Discs", "General"), never a manufacturer brand.

Code layout in each lookup sheet (column A = Code, column B = Name):
    FAMILY:         "FAM0000{aa}"           -> aa (2 digits)
    Group:          "G{aa}{bb}"             -> aa, bb (2 digits each)
    Classification: "C{aa}{bb}{cc}"         -> aa, bb, cc
    Brand:          "B{aa}{bb}{cc}{dd}"     -> aa, bb, cc, dd
Each level's own code column is only used to derive its position in the
hierarchy; the FK chain (not a copy of the source code string) is what
ItemFamily/ItemGroup/ItemClassification/ItemBrand actually store.

The FAMILY sheet in the real workbook has a second, differently-formatted
duplicate block appended below the real one (same 18 rows, "FAM00001"
instead of "FAM000001") -- only the first block (18 rows) is used here;
parsing stops as soon as a row's Code column reads "Code" again.

Usage:
    python manage.py import_item_classification_tree --file "C:\\path\\to\\FINAL_With_Validation-R02.xlsx"
    python manage.py import_item_classification_tree --file ... --dry-run
"""

import re

import openpyxl

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from procurement.models import ItemFamily, ItemGroup, ItemClassification, ItemBrand


def _rows(ws):
    """(code, name) pairs from column A/B, starting row 2, stopping at a repeated header row or blank code."""
    for r in range(2, ws.max_row + 1):
        code = ws.cell(row=r, column=1).value
        name = ws.cell(row=r, column=2).value
        if code is None or str(code).strip() == "":
            continue
        code = str(code).strip()
        if code == "Code":
            break
        yield code, (str(name).strip() if name else "")


class Command(BaseCommand):
    help = "Import the Family/Group/Classification/Brand lookup tables from the item classification workbook"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx workbook")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the database")

    def handle(self, *args, **options):
        path = options["file"]
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        for sheet in ("FAMILY", "Group", "Classification", "Brand"):
            if sheet not in wb.sheetnames:
                raise CommandError(f"Sheet '{sheet}' not found. Available: {wb.sheetnames}")

        families = {}  # aa -> name
        for code, name in _rows(wb["FAMILY"]):
            m = re.fullmatch(r"FAM0*(\d+)", code)
            if not m:
                continue
            aa = m.group(1).zfill(2)
            families.setdefault(aa, name)  # first occurrence wins (skips the duplicate trailing block)

        groups = {}  # (aa,bb) -> name
        for code, name in _rows(wb["Group"]):
            m = re.fullmatch(r"G(\d{2})(\d{2})", code)
            if not m:
                continue
            groups[(m.group(1), m.group(2))] = name

        classifications = {}  # (aa,bb,cc) -> name
        for code, name in _rows(wb["Classification"]):
            m = re.fullmatch(r"C(\d{2})(\d{2})(\d{2})", code)
            if not m:
                continue
            classifications[(m.group(1), m.group(2), m.group(3))] = name

        brands = {}  # (aa,bb,cc,dd) -> name
        for code, name in _rows(wb["Brand"]):
            m = re.fullmatch(r"B(\d{2})(\d{2})(\d{2})(\d{2})", code)
            if not m:
                continue
            brands[(m.group(1), m.group(2), m.group(3), m.group(4))] = name

        self.stdout.write(
            f"Parsed {len(families)} families, {len(groups)} groups, "
            f"{len(classifications)} classifications, {len(brands)} brands."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        with transaction.atomic():
            family_objs = {}
            for aa, name in families.items():
                obj, _ = ItemFamily.objects.update_or_create(code=aa, defaults={"name": name})
                family_objs[aa] = obj

            group_objs = {}
            skipped_groups = 0
            for (aa, bb), name in groups.items():
                family = family_objs.get(aa)
                if not family:
                    skipped_groups += 1
                    continue
                obj, _ = ItemGroup.objects.update_or_create(family=family, code=bb, defaults={"name": name})
                group_objs[(aa, bb)] = obj

            classification_objs = {}
            skipped_classifications = 0
            for (aa, bb, cc), name in classifications.items():
                group = group_objs.get((aa, bb))
                if not group:
                    skipped_classifications += 1
                    continue
                obj, _ = ItemClassification.objects.update_or_create(group=group, code=cc, defaults={"name": name})
                classification_objs[(aa, bb, cc)] = obj

            skipped_brands = 0
            for (aa, bb, cc, dd), name in brands.items():
                classification = classification_objs.get((aa, bb, cc))
                if not classification:
                    skipped_brands += 1
                    continue
                ItemBrand.objects.update_or_create(classification=classification, code=dd, defaults={"name": name})

        if skipped_groups or skipped_classifications or skipped_brands:
            self.stdout.write(self.style.WARNING(
                f"Skipped (no parent found): {skipped_groups} group(s), "
                f"{skipped_classifications} classification(s), {skipped_brands} brand(s)."
            ))
        self.stdout.write(self.style.SUCCESS(
            f"Done. Families: {ItemFamily.objects.count()}, Groups: {ItemGroup.objects.count()}, "
            f"Classifications: {ItemClassification.objects.count()}, Brands: {ItemBrand.objects.count()}."
        ))
