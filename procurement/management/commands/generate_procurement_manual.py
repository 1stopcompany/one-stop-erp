"""
Generate the "How to use the Procurement System" PDF manual, illustrated
with real data from the demo procurement activity seeded by
seed_procurement_demo (or any real PRs/RFQs/POs already in the system).

Usage:
    python manage.py generate_procurement_manual --out "C:\\path\\to\\manual.pdf"
    python manage.py generate_procurement_manual --project TAB --out ...
"""

from django.core.management.base import BaseCommand, CommandError

from procurement.models import PurchaseRequisition, RequestForQuotation, PurchaseOrder
from procurement.manual_pdf import generate_procurement_manual_pdf
from procurement.barcode_utils import render_barcode_png


def _line_dict(line):
    return {
        "code": line.item.full_code, "desc": line.item.description,
        "qty": float(line.quantity_requested), "unit": line.get_unit_display(),
        "barcode_value": line.item.barcode_value,
    }


def build_demo_data(project):
    prs = list(PurchaseRequisition.objects.filter(project=project, remarks__startswith="[DEMO]").order_by("id"))
    draft_pr = next((p for p in prs if p.status == "draft"), None)
    submitted_pr = next((p for p in prs if p.status == "submitted"), None)
    full_pr = next((p for p in prs if p.status == "completed"), None)
    if not (draft_pr and submitted_pr and full_pr):
        raise CommandError(f"Project {project.project_symbol} is missing one of the demo PR stages (draft/submitted/completed).")

    rfq = RequestForQuotation.objects.filter(pr=full_pr).first()
    pos = list(PurchaseOrder.objects.filter(pr=full_pr).order_by("id"))
    if not (rfq and pos):
        raise CommandError(f"Project {project.project_symbol}'s completed demo PR is missing its RFQ/PO.")

    pr_lines_full = list(full_pr.lines.select_related("item").all())

    quotes = []
    for q in rfq.quotes.select_related("vendor").prefetch_related("lines__pr_line"):
        by_line = {ql.pr_line_id: ql for ql in q.lines.all()}
        lead_times = [ql.lead_time_days for ql in q.lines.all() if ql.lead_time_days]
        quotes.append({
            "vendor": q.vendor.name,
            "total": float(q.total_price()),
            "lead_time": max(lead_times) if lead_times else 0,
            "prices": [float(by_line[pl.id].unit_price) if pl.id in by_line else None for pl in pr_lines_full],
            "selected": [bool(by_line[pl.id].is_selected) if pl.id in by_line else False for pl in pr_lines_full],
        })

    pos_data = []
    for po in pos:
        po_lines = [{
            "code": l.item.full_code, "desc": l.item.description, "unit": l.get_unit_display(),
            "ordered": float(l.quantity_ordered), "received": float(l.quantity_received),
            "price": float(l.unit_price), "total": float(l.total_price),
            "barcode_value": l.item.barcode_value,
        } for l in po.lines.select_related("item").all()]
        pos_data.append({
            "po_number": po.po_number, "vendor": po.vendor.name, "total": float(po.total_price),
            "lines": po_lines,
        })

    demo_data = {
        "project_name": project.name,
        "draft_pr": {"pr_number": draft_pr.pr_number, "lines": [_line_dict(l) for l in draft_pr.lines.select_related("item").all()]},
        "submitted_pr": {"pr_number": submitted_pr.pr_number, "lines": [_line_dict(l) for l in submitted_pr.lines.select_related("item").all()]},
        "full_pr": {"pr_number": full_pr.pr_number},
        "rfq": {
            "rfq_number": rfq.rfq_number,
            "vendor_names": [iv.vendor.name for iv in rfq.invited_vendors.select_related("vendor").all()],
            "pr_lines": [_line_dict(l) for l in pr_lines_full],
            "quotes": quotes,
        },
        "pos": pos_data,
    }

    barcode_item = pos[0].lines.select_related("item").first().item if pos[0].lines.exists() else None
    if barcode_item:
        demo_data["barcode"] = {
            "full_code": barcode_item.full_code,
            "description": barcode_item.description,
            "png_bytes": render_barcode_png(barcode_item.barcode_value),
        }
    return demo_data


class Command(BaseCommand):
    help = "Generate the illustrated procurement-system user manual PDF from real demo data"

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Output PDF path")
        parser.add_argument("--project", default=None, help="Project symbol to draw examples from (default: first project with demo data)")

    def handle(self, *args, **options):
        qs = PurchaseRequisition.objects.filter(remarks__startswith="[DEMO]").select_related("project")
        if options["project"]:
            qs = qs.filter(project__project_symbol=options["project"])
        if not qs.exists():
            raise CommandError("No demo purchase requisitions found -- run seed_procurement_demo first.")

        project = qs.first().project
        demo_data = build_demo_data(project)

        pdf_bytes = generate_procurement_manual_pdf(demo_data)
        with open(options["out"], "wb") as f:
            f.write(pdf_bytes)
        self.stdout.write(self.style.SUCCESS(f"Manual written to {options['out']} ({len(pdf_bytes)} bytes), using project {project.project_symbol}."))
