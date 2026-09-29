"""
Import the company's real item classification catalog ("FINAL_With_
Validation-R02.xlsx", sheet "ALL") into ItemMaster.

Source layout (row 1 = title, row 2 = header, data from row 3):
    A FullCode | B Family | C Family.1 | D Group | E Group.1 |
    F Classification | G Classification.1 | H Brand | I Brand.1 |
    J item | K item.1 | L AA | M (unused)

FullCode is an 11-digit string (aa=2, bb=2, cc=2, dd=2, eee=3) matching
ItemMaster's own aa_level/bb_category/cc_subcategory/dd_itemtype/
eee_attribute scheme exactly -- this file's own coding IS the company's
coding, not a separate one being mapped in.

Despite the source workbook's own "QA_Checks" sheet claiming "FullCode
duplicates in ALL: PASS", ~18 codes in the real file are in fact reused
across more than one distinct item (e.g. code 01020504001 covers 24
different items) -- apparently because Brand isn't part of the 11-digit
scheme, so two items that only differ by brand collide. Each such
collision is disambiguated with ItemMaster.variant_suffix (0 for the
first occurrence of a code, 1 for the second, ...) rather than inventing
a fake spec/eee_attribute value; every collision is reported at the end
of the import so they can be reviewed and given a real distinguishing
eee_attribute later if desired.

Usage:
    python manage.py import_item_master --file "C:\\path\\to\\FINAL_With_Validation-R02.xlsx"
    python manage.py import_item_master --file ... --dry-run
"""

import openpyxl

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from procurement.models import ItemMaster


class Command(BaseCommand):
    help = "Import ItemMaster rows from the company's item-classification Excel workbook (sheet 'ALL')"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx workbook")
        parser.add_argument("--sheet", default="ALL", help="Sheet name (default: ALL)")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the database")

    def handle(self, *args, **options):
        path = options["file"]
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        sheet_name = options["sheet"]
        if sheet_name not in wb.sheetnames:
            raise CommandError(f"Sheet '{sheet_name}' not found. Available: {wb.sheetnames}")
        ws = wb[sheet_name]

        seen_codes = {}  # 11-digit source code -> count of occurrences so far
        conflicts = {}   # source code -> list of descriptions seen
        rows_to_create = []
        skipped_no_code = 0

        for row in ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True):
            full_code = row[0]
            if full_code is None:
                skipped_no_code += 1
                continue
            code = str(full_code).strip().zfill(11)
            if len(code) != 11 or not code.isdigit():
                skipped_no_code += 1
                continue

            family_name = (row[2] or "").strip() if row[2] else ""
            group_name = (row[4] or "").strip() if row[4] else ""
            classification_name = (row[6] or "").strip() if row[6] else ""
            brand_name = (row[8] or "").strip() if row[8] else ""
            description = (row[10] or "").strip() if row[10] else ""
            if not description:
                description = classification_name or group_name or family_name or code

            occurrence = seen_codes.get(code, 0)
            seen_codes[code] = occurrence + 1
            if occurrence > 0:
                conflicts.setdefault(code, []).append(description)

            rows_to_create.append({
                "aa_level": code[0:2], "bb_category": code[2:4], "cc_subcategory": code[4:6],
                "dd_itemtype": code[6:8], "eee_attribute": code[8:11],
                "variant_suffix": occurrence,
                "source_code": code,
                "description": description,
                "brand": brand_name,
            })

        self.stdout.write(f"Parsed {len(rows_to_create)} item rows ({skipped_no_code} rows skipped: no valid code).")
        if conflicts:
            self.stdout.write(self.style.WARNING(f"{len(conflicts)} source code(s) cover more than one item (disambiguated via variant_suffix):"))
            for code, descs in list(conflicts.items())[:10]:
                self.stdout.write(f"  {code}: +{len(descs)} extra item(s) -- e.g. {descs[0]!r}")
            if len(conflicts) > 10:
                self.stdout.write(f"  ... and {len(conflicts) - 10} more")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        created = 0
        updated = 0
        with transaction.atomic():
            existing_by_source = {
                (im.source_code, im.variant_suffix): im
                for im in ItemMaster.objects.exclude(source_code="")
            }
            for data in rows_to_create:
                key = (data["source_code"], data["variant_suffix"])
                existing = existing_by_source.get(key)
                if existing:
                    existing.description = data["description"]
                    existing.brand = data["brand"]
                    existing.aa_level = data["aa_level"]
                    existing.bb_category = data["bb_category"]
                    existing.cc_subcategory = data["cc_subcategory"]
                    existing.dd_itemtype = data["dd_itemtype"]
                    existing.eee_attribute = data["eee_attribute"]
                    existing.save()
                    updated += 1
                else:
                    ItemMaster.objects.create(**data)
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Created: {created}, Updated: {updated}."))
