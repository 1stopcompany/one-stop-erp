"""
Seed realistic demo procurement activity (purchase requisitions, RFQs,
vendor quotes, purchase orders, and site receipts) across every real
project, so the procurement module has something to look at/demo/train
from instead of being empty. Uses real ItemMaster catalog items and each
project's own real site_engineer/manager for requested_by/approved_by,
so permission-scoped views show this data to the right people.

For every project, creates three PRs covering the workflow's three
common resting states:
  1. A draft PR (not submitted yet)
  2. A submitted PR awaiting the project manager's approval
  3. A fully completed PR: approved -> RFQ sent to 2 vendors -> both
     vendors quoted -> one quote selected -> PO issued -> partially
     received on site

Safe to re-run: skips a project if it already has a PR whose remarks
start with "[DEMO]".

Usage: python manage.py seed_procurement_demo
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from projects.models import Project
from procurement.models import (
    ItemMaster, Vendor,
    PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, RFQVendor, VendorQuote, VendorQuoteLine,
    PurchaseOrder, PurchaseOrderLine, POReceipt,
)

DEMO_MARK = "[DEMO]"

VENDOR_SEED = [
    {"name": "شركة النور للمواد الإنشائية", "contact_person": "أبو خالد", "phone": "0599123456", "email": "sales@alnoor-materials.example", "city": "رام الله"},
    {"name": "مؤسسة الأمانة للمقاولات والتوريدات", "contact_person": "سامر عودة", "phone": "0598765432", "email": "info@amana-supplies.example", "city": "نابلس"},
    {"name": "شركة الإعمار للتجهيزات الهندسية", "contact_person": "ريم حماد", "phone": "0597112233", "email": "sales@iemar-eng.example", "city": "الخليل"},
    {"name": "مصنع الجودة للحديد والإسمنت", "contact_person": "محمود نمر", "phone": "0596445566", "email": "orders@quality-factory.example", "city": "طولكرم"},
]

ITEM_CODE_POOL = [
    "OS.03.04.01.01.000",  # Cement OPC 50kg
    "OS.03.09.01.02.012",  # Reinforcement Steel - Deformed Bars
    "OS.09.03.01.01.000",  # Ceramic floor tiles
    "OS.09.04.02.01.000",  # Internal emulsion paint
    "OS.09.04.03.01.000",  # Exterior paint
    "OS.05.02.11.01.002",  # Handrail pipe
    "OS.03.08.01.01.004",  # Steel props / shoring
    "OS.04.03.01.04.001",  # Pipe Spacer
]

UNIT_BY_CODE_HINT = {
    "cement": "bag", "steel": "ton", "reinforcement": "ton", "tile": "m2",
    "paint": "liter", "pipe": "m", "props": "pcs", "spacer": "pcs",
}


def _guess_unit(item):
    if item.unit:
        return item.unit
    desc = item.description.lower()
    for hint, unit in UNIT_BY_CODE_HINT.items():
        if hint in desc:
            return unit
    return "pcs"


class Command(BaseCommand):
    help = "Seed demo purchase requisitions/RFQs/quotes/POs/receipts across all real projects"

    def handle(self, *args, **options):
        items = list(ItemMaster.objects.filter(full_code__in=ITEM_CODE_POOL))
        if len(items) < 4:
            items = list(ItemMaster.objects.filter(status="active").order_by("?")[:8])
        if not items:
            self.stderr.write(self.style.ERROR("No ItemMaster rows found -- run import_item_master first."))
            return

        vendors = []
        for v in VENDOR_SEED:
            vendor, _ = Vendor.objects.get_or_create(name=v["name"], defaults={**{k: val for k, val in v.items() if k != "name"}, "is_active": True})
            vendors.append(vendor)

        today = timezone.localdate()
        projects = list(Project.objects.all())
        if not projects:
            self.stderr.write(self.style.ERROR("No projects found."))
            return

        created_summary = []
        for project in projects:
            if PurchaseRequisition.objects.filter(project=project, remarks__startswith=DEMO_MARK).exists():
                self.stdout.write(f"Skipping {project.project_symbol}: demo data already present.")
                continue

            site_eng = project.site_engineer
            pm = project.manager
            if not site_eng or not pm:
                self.stdout.write(self.style.WARNING(f"Skipping {project.project_symbol}: missing site_engineer or manager."))
                continue

            with transaction.atomic():
                # ---- PR 1: draft ----
                pr_draft = PurchaseRequisition.objects.create(
                    project=project, required_date=today + timedelta(days=14),
                    remarks=f"{DEMO_MARK} طلب مواد تشطيبات - قيد الإعداد", requested_by=site_eng,
                )
                for item in random.sample(items, 2):
                    PurchaseRequisitionLine.objects.create(
                        pr=pr_draft, item=item, quantity_requested=random.choice([10, 20, 50]),
                        unit=_guess_unit(item),
                    )

                # ---- PR 2: submitted, awaiting PM approval ----
                pr_submitted = PurchaseRequisition.objects.create(
                    project=project, required_date=today + timedelta(days=7),
                    remarks=f"{DEMO_MARK} طلب مواد عاجل للموقع", requested_by=site_eng,
                    status="submitted", submitted_date=timezone.now() - timedelta(days=1),
                )
                for item in random.sample(items, 3):
                    PurchaseRequisitionLine.objects.create(
                        pr=pr_submitted, item=item, quantity_requested=random.choice([5, 15, 30]),
                        unit=_guess_unit(item),
                    )

                # ---- PR 3: full lifecycle -> approved -> RFQ -> quotes -> PO -> partial receipt ----
                submitted_at = timezone.now() - timedelta(days=10)
                pr_full = PurchaseRequisition.objects.create(
                    project=project, required_date=today - timedelta(days=2),
                    remarks=f"{DEMO_MARK} طلب مواد أساسية للمرحلة الحالية", requested_by=site_eng,
                    status="approved", submitted_date=submitted_at,
                    approved_by=pm, approved_date=submitted_at + timedelta(days=1),
                    assigned_to=None,
                )
                pr_items = random.sample(items, 3)
                pr_lines = []
                for item in pr_items:
                    line = PurchaseRequisitionLine.objects.create(
                        pr=pr_full, item=item, quantity_requested=random.choice([20, 40, 100]),
                        unit=_guess_unit(item),
                    )
                    pr_lines.append(line)

                chosen_vendors = random.sample(vendors, 2)
                rfq = RequestForQuotation.objects.create(
                    pr=pr_full, status="sent", due_date=today + timedelta(days=3),
                    notes=f"{DEMO_MARK} طلب عروض أسعار", created_by=pm,
                    sent_date=submitted_at + timedelta(days=2),
                )
                pr_full.status = "in_procurement"
                pr_full.assigned_to = pm
                pr_full.save(update_fields=["status", "assigned_to"])

                for v in chosen_vendors:
                    RFQVendor.objects.create(rfq=rfq, vendor=v, sent_at=rfq.sent_date)

                quotes = []
                for v in chosen_vendors:
                    quote = VendorQuote.objects.create(
                        rfq=rfq, vendor=v, received_date=today - timedelta(days=6),
                        notes=f"{DEMO_MARK} عرض سعر مستلم", entered_by=pm,
                    )
                    for line in pr_lines:
                        base_price = {"bag": 28, "ton": 3200, "m2": 45, "liter": 22, "m": 18, "pcs": 12}.get(line.unit, 15)
                        jitter = random.uniform(0.9, 1.15)
                        VendorQuoteLine.objects.create(
                            quote=quote, pr_line=line,
                            unit_price=round(base_price * jitter, 2),
                            lead_time_days=random.choice([3, 5, 7, 10]),
                        )
                    quotes.append(quote)

                # Award each line to whichever vendor quoted it cheapest -- demonstrates
                # split sourcing (some items from one vendor, some from another) rather
                # than always giving the whole RFQ to a single "winning" quote.
                by_vendor_lines = {}
                for line in pr_lines:
                    candidates = [ql for q in quotes for ql in q.lines.all() if ql.pr_line_id == line.id]
                    cheapest = min(candidates, key=lambda ql: ql.unit_price)
                    cheapest.is_selected = True
                    cheapest.save(update_fields=["is_selected"])
                    by_vendor_lines.setdefault(cheapest.quote, []).append(cheapest)

                created_pos = []
                for quote, qlines in by_vendor_lines.items():
                    po = PurchaseOrder.objects.create(
                        project=project, vendor=quote.vendor, pr=pr_full, source_quote=quote,
                        delivery_date=today + timedelta(days=5), status="confirmed",
                        remarks=f"{DEMO_MARK} أمر شراء", created_by=pm,
                    )
                    for qline in qlines:
                        po_line = PurchaseOrderLine.objects.create(
                            po=po, item=qline.pr_line.item, pr_line=qline.pr_line,
                            quantity_ordered=qline.pr_line.quantity_requested, unit=qline.pr_line.unit,
                            unit_price=qline.unit_price,
                        )
                        # Partially receive the first PO's first line only, to demo a mixed-status PO
                        if not created_pos and po_line == po.lines.first():
                            POReceipt.objects.create(
                                po_line=po_line, quantity_received=round(float(po_line.quantity_ordered) * 0.6, 2),
                                received_by=site_eng, remarks=f"{DEMO_MARK} استلام جزئي بالموقع",
                            )
                    po.refresh_from_db()
                    created_pos.append(po)

                pr_full.status = "completed"
                pr_full.save(update_fields=["status"])

                created_summary.append((
                    project.project_symbol, pr_draft.pr_number, pr_submitted.pr_number, pr_full.pr_number,
                    ", ".join(po.po_number for po in created_pos),
                ))

        self.stdout.write(self.style.SUCCESS(f"Seeded demo procurement data for {len(created_summary)} project(s):"))
        for symbol, d, s, f, po_nums in created_summary:
            self.stdout.write(f"  {symbol}: draft={d}, submitted={s}, completed={f} -> {po_nums}")
