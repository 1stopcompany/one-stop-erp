"""
Demo data for the Daily Site Report: a short run of real daily reports for the demo project ("[DEMO] Cost Control Tower",
symbol DEMOCC), one for every stage of the draft -> submitted -> engineering_approved -> approved / rejected workflow,
each fully populated with every section the report page shows: workforce, equipment, daily activities, materials,
visitors, photo attachments, BOQ-linked activity progress, named worker attendance, QA/QC & HSE, site events
(delay / RFI / site instruction / NCR / near-miss) and the next-day plan.

The story follows the project's own seeded schedule (reports.schedule_demo): ground floor columns/slab finishing,
ground floor blockwork wrapping up, first floor columns/slab starting -- so the activity-progress figures on today's
report line up with what reports.schedule_view shows for A3005 / A3010. Nothing here is sent to any AI; photos are
placeholder images generated on the fly.
"""
from datetime import date, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .daily_detail_models import DailyReportActivityProgress, DailyReportNextDayPlan, DailyReportQAQC, DailyReportWorkerAttendance
from .master_data_models import LaborClassification
from .models import DailyActivity, DailyEquipment, DailyMaterial, DailyReport, DailyVisitor, DailyWorkForce, ReportAttachment
from .progress_models import ProjectPhaseProgressEntry, ProjectPhaseSubItem
from .site_event_models import SiteEvent

NUMBER_PREFIX = "DCR-DEMO-"
EVENT_TAG = "DEMO-"


def _photo(caption, color):
    """A small placeholder JPEG (no external image needed) captioned with the given text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 620, 460], outline=(255, 255, 255), width=4)
    words = caption.split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if len(candidate) > 28:
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    y = 200
    for line in lines:
        draw.text((40, y), line, fill=(255, 255, 255))
        y += 20
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=70)
    return ContentFile(buffer.getvalue(), name="site_photo.jpg")


# (days before today, status, weather, remarks) -- the six reports, oldest first
REPORTS = [
    (10, "rejected", "cloudy",
     "Ground floor columns and slab nearing completion; blockwork progressing on grid A-D. "
     "See QA/QC note below -- rejected pending more detail on the near-miss."),
    (8, "approved", "sunny",
     "Ground floor columns and slab substantially complete. Blockwork continuing on upper grids."),
    (6, "approved", "sunny",
     "First floor columns and slab works started on grid A-C. Ground floor blockwork ongoing."),
    (4, "engineering_approved", "windy",
     "First floor columns/slab formwork and reinforcement in progress. Cube test requested for yesterday's pour."),
    (2, "submitted", "mixed",
     "Blockwork on ground floor nearing completion. First floor column reinforcement continuing."),
    (0, "draft", "sunny",
     "First floor columns and slab in progress per schedule; ground floor blockwork close to finishing."),
]

# Cumulative progress against the project's own BOQ (sub-item code -> [(days_before_today, cumulative_qty, today_qty, status), ...])
PROGRESS = {
    "2.1": [  # Columns and slabs, total 250 m3
        (10, Decimal("165"), Decimal("12"), "in_progress"),
        (8, Decimal("190"), Decimal("14"), "in_progress"),
        (6, Decimal("210"), Decimal("10"), "in_progress"),
        (4, Decimal("225"), Decimal("8"), "in_progress"),
        (2, Decimal("235"), Decimal("6"), "in_progress"),
        (0, Decimal("240"), Decimal("5"), "in_progress"),
    ],
    "2.2": [  # Blockwork, total 800 m2
        (10, Decimal("300"), Decimal("35"), "in_progress"),
        (8, Decimal("400"), Decimal("45"), "in_progress"),
        (6, Decimal("480"), Decimal("40"), "in_progress"),
        (4, Decimal("560"), Decimal("42"), "in_progress"),
        (2, Decimal("620"), Decimal("38"), "in_progress"),
        (0, Decimal("680"), Decimal("30"), "in_progress"),
    ],
}
# Foundations were finished before this window: logged once, on the oldest report, as completed.
FOUNDATIONS_DONE = [("1.1", Decimal("300"), "completed"), ("1.2", Decimal("120"), "completed")]

WORKFORCE = {
    10: [("management", "Site Engineer", 1), ("skilled", "Steel Fixers", 6), ("skilled", "Masons", 6), ("unskilled", "General Helpers", 8)],
    8: [("management", "Site Engineer", 1), ("skilled", "Steel Fixers", 6), ("skilled", "Masons", 7), ("unskilled", "General Helpers", 9),
        ("contractor", "Concrete Pump Crew", 4)],
    6: [("management", "Site Engineer", 1), ("management", "Project Manager", 1), ("skilled", "Steel Fixers", 5), ("skilled", "Masons", 7),
        ("unskilled", "General Helpers", 9)],
    4: [("management", "Site Engineer", 1), ("skilled", "Steel Fixers", 7), ("skilled", "Masons", 6), ("skilled", "Carpenters", 4),
        ("unskilled", "General Helpers", 10)],
    2: [("management", "Site Engineer", 1), ("skilled", "Steel Fixers", 6), ("skilled", "Masons", 8), ("unskilled", "General Helpers", 9),
        ("contractor", "Concrete Pump Crew", 3)],
    0: [("management", "Site Engineer", 1), ("skilled", "Steel Fixers", 7), ("skilled", "Masons", 8), ("skilled", "Carpenters", 3),
        ("unskilled", "General Helpers", 10)],
}

EQUIPMENT = {
    10: [("Tower Crane", 8, 0), ("Concrete Mixer", 6, 1), ("Bar Bending Machine", 5, 0), ("Generator", 10, 0)],
    8: [("Tower Crane", 9, 0), ("Concrete Mixer", 7, 0), ("Concrete Pump", 4, 0), ("Generator", 10, 0)],
    6: [("Tower Crane", 8, 0), ("Bar Bending Machine", 6, 0), ("Scaffolding Hoist", 5, 1), ("Generator", 10, 0)],
    4: [("Tower Crane", 8, 0), ("Concrete Mixer", 6, 1), ("Bar Bending Machine", 6, 0), ("Generator", 10, 0)],
    2: [("Tower Crane", 9, 0), ("Concrete Mixer", 7, 0), ("Concrete Pump", 4, 0), ("Generator", 10, 0)],
    0: [("Tower Crane", 8, 0), ("Bar Bending Machine", 6, 0), ("Scaffolding Hoist", 6, 0), ("Generator", 10, 0)],
}

ACTIVITIES = {
    10: [("structure", "Grid A-D, ground floor", "Reinforcement fixing for ground floor columns."),
         ("other", "Grid A-D, ground floor", "Blockwork on grid A-B, ground floor external walls.")],
    8: [("structure", "Grid A-D, ground floor", "Concrete pour for the last ground floor column strip."),
        ("other", "Grid B-D, ground floor", "Blockwork continuing on internal partitions, ground floor.")],
    6: [("structure", "Grid A-C, first floor", "Formwork erection for first floor columns."),
        ("other", "Grid C-D, ground floor", "Blockwork finishing on ground floor, remaining bays.")],
    4: [("structure", "Grid A-C, first floor", "Reinforcement fixing for first floor columns and slab."),
        ("inspection", "First floor", "Consultant inspection of column reinforcement before pour.")],
    2: [("structure", "Grid A-C, first floor", "Formwork and reinforcement continuing for first floor slab."),
        ("other", "Ground floor", "Final blockwork bay closed out, ground floor.")],
    0: [("structure", "Grid A-C, first floor", "Column and slab works continuing per schedule (A3010)."),
        ("other", "Ground floor", "Punch-list touch-ups on finished ground floor blockwork (A3005).")],
}

MATERIALS = {
    10: [("Ready-mix concrete C30", Decimal("28"), "m3"), ("Reinforcement steel B500", Decimal("3.2"), "ton"), ("Concrete blocks 20cm", Decimal("1400"), "pcs")],
    8: [("Ready-mix concrete C30", Decimal("32"), "m3"), ("Cement (bags)", Decimal("180"), "bags"), ("Concrete blocks 20cm", Decimal("1500"), "pcs")],
    6: [("Reinforcement steel B500", Decimal("4.0"), "ton"), ("Timber formwork panels", Decimal("60"), "pcs"), ("Sand", Decimal("14"), "m3")],
    4: [("Reinforcement steel B500", Decimal("3.6"), "ton"), ("Cement (bags)", Decimal("150"), "bags")],
    2: [("Ready-mix concrete C30", Decimal("18"), "m3"), ("Concrete blocks 20cm", Decimal("600"), "pcs"), ("Sand", Decimal("10"), "m3")],
    0: [("Reinforcement steel B500", Decimal("3.0"), "ton"), ("Timber formwork panels", Decimal("40"), "pcs")],
}

VISITORS = {
    10: [(time(10, 30), "Eng. Firas Odeh", "Structural consultant")],
    8: [(time(9, 0), "Nabil Hamdan", "Owner representative")],
    6: [(time(11, 0), "Eng. Firas Odeh", "Structural consultant"), (time(14, 0), "Municipality inspector", "Municipality")],
    4: [(time(9, 30), "Eng. Firas Odeh", "Structural consultant, reinforcement inspection")],
    2: [(time(10, 0), "Safety auditor", "Insurer's HSE audit")],
    0: [(time(9, 15), "Nabil Hamdan", "Owner representative, site walk-through")],
}

PHOTOS = {
    10: [("Ground floor column reinforcement, grid A-D", "Ground floor", (90, 110, 140)), ("Blockwork progress, grid A-B", "Ground floor", (120, 130, 90))],
    8: [("Last ground floor column pour", "Ground floor", (90, 110, 140)), ("Blockwork, internal partitions", "Ground floor", (120, 130, 90))],
    6: [("First floor column formwork", "First floor", (90, 110, 140)), ("Ground floor blockwork, finishing bays", "Ground floor", (120, 130, 90))],
    4: [("First floor column reinforcement", "First floor", (90, 110, 140)), ("Consultant inspection", "First floor", (100, 100, 100))],
    2: [("First floor slab formwork", "First floor", (90, 110, 140)), ("Ground floor blockwork, final bay", "Ground floor", (120, 130, 90))],
    0: [("First floor columns and slab, in progress", "First floor", (90, 110, 140)), ("Ground floor blockwork, near complete", "Ground floor", (120, 130, 90))],
}

ATTENDANCE = {
    10: [("Yousef Hasan", "Block Mason", "One Stop", "Ground floor, grid A-B", time(7, 0), time(15, 0)),
         ("Ahmad Salem", "Skilled Labor", "One Stop", "Ground floor, reinforcement", time(7, 0), time(15, 30)),
         ("Khalil Nasser", "Skilled Labor", "One Stop", "Ground floor, reinforcement", time(7, 0), time(15, 0)),
         ("Mousa Freij", "Unskilled Labor", "One Stop", "Site cleanup", time(7, 0), time(14, 30))],
    8: [("Yousef Hasan", "Block Mason", "One Stop", "Ground floor, grid B-D", time(7, 0), time(15, 0)),
        ("Samir Awad", "Masonry", "One Stop", "Ground floor blockwork", time(7, 0), time(15, 0)),
        ("Ahmad Salem", "Skilled Labor", "One Stop", "Column pour crew", time(6, 30), time(16, 0)),
        ("Mousa Freij", "Unskilled Labor", "One Stop", "Concrete curing / cleanup", time(7, 0), time(15, 0))],
    6: [("Karam Zeidan", "Carpenter", "One Stop", "First floor, formwork", time(7, 0), time(15, 0)),
        ("Yousef Hasan", "Block Mason", "One Stop", "Ground floor, grid C-D", time(7, 0), time(15, 0)),
        ("Ahmad Salem", "Skilled Labor", "One Stop", "First floor, formwork", time(7, 0), time(15, 30)),
        ("Mousa Freij", "Unskilled Labor", "One Stop", "Material handling", time(7, 0), time(14, 30))],
    4: [("Karam Zeidan", "Carpenter", "One Stop", "First floor, reinforcement support", time(7, 0), time(15, 0)),
        ("Khalil Nasser", "Skilled Labor", "One Stop", "First floor, reinforcement", time(7, 0), time(16, 0)),
        ("Ahmad Salem", "Skilled Labor", "One Stop", "First floor, reinforcement", time(7, 0), time(15, 30)),
        ("Mousa Freij", "Unskilled Labor", "One Stop", "Material handling", time(7, 0), time(14, 30))],
    2: [("Yousef Hasan", "Block Mason", "One Stop", "Ground floor, final bay", time(7, 0), time(14, 0)),
        ("Ahmad Salem", "Skilled Labor", "One Stop", "First floor, slab formwork", time(7, 0), time(15, 30)),
        ("Karam Zeidan", "Carpenter", "One Stop", "First floor, slab formwork", time(7, 0), time(15, 0)),
        ("Mousa Freij", "Unskilled Labor", "One Stop", "Site cleanup", time(7, 0), time(14, 30))],
    0: [("Ahmad Salem", "Skilled Labor", "One Stop", "First floor, columns", time(7, 0), time(15, 30)),
        ("Khalil Nasser", "Skilled Labor", "One Stop", "First floor, columns", time(7, 0), time(15, 0)),
        ("Karam Zeidan", "Carpenter", "One Stop", "First floor, formwork", time(7, 0), time(15, 0)),
        ("Yousef Hasan", "Block Mason", "One Stop", "Ground floor, punch-list", time(7, 0), time(13, 0))],
}

QAQC = {
    10: dict(inspection_status="failed", toolbox_talk_conducted=True, toolbox_talk_topic="Working at height",
             incident_occurred=False, near_miss_occurred=True, ppe_site_cleanliness_status="2 workers found without harness near the edge; corrected on site",
             ncr_hse_reference="NM-DEMO-01", notes="Near-miss only briefly logged -- needs more detail before this report can be approved."),
    8: dict(inspection_status="passed", toolbox_talk_conducted=True, toolbox_talk_topic="Concrete pour safety",
            ppe_site_cleanliness_status="Good", notes="No issues."),
    6: dict(inspection_status="passed", ir_mir_test_reference="IR-DEMO-014", toolbox_talk_conducted=True, toolbox_talk_topic="Manual handling",
            ppe_site_cleanliness_status="Good", notes="Cube test IR-DEMO-014 raised for yesterday's pour."),
    4: dict(inspection_status="pending", ir_mir_test_reference="IR-DEMO-014", toolbox_talk_conducted=True, toolbox_talk_topic="Scaffolding safety",
            ppe_site_cleanliness_status="Good", notes="Awaiting cube test result (IR-DEMO-014)."),
    2: dict(inspection_status="passed", toolbox_talk_conducted=True, toolbox_talk_topic="Housekeeping", ppe_site_cleanliness_status="Good",
            notes="Site tidy, no issues."),
    0: dict(inspection_status="not_applicable", toolbox_talk_conducted=True, toolbox_talk_topic="Blockwork mortar curing",
            ppe_site_cleanliness_status="Good", notes="Routine day, no inspection scheduled."),
}

SITE_EVENTS = {
    10: ("near_miss", "NM-DEMO-01", "Two workers observed near the ground floor edge without fall-arrest harnesses.",
         "Toolbox talk repeated; harnesses issued and checked at the start of each shift.", "open", None),
    8: ("rfi", "RFI-DEMO-07", "Confirm mortar mix ratio for external blockwork (1:4 vs 1:5) against the specification.",
        "Awaiting consultant response.", "open", None),
    6: ("site_instruction", "SI-DEMO-03", "Change lobby floor tile specification per the architect's revised finishes schedule.",
        "Procurement to update the material order.", "closed", None),
    4: ("delay", "", "Half-day delay on first floor reinforcement due to late rebar delivery.",
        "Supplier contacted; delivery rescheduled for the same afternoon.", "closed", Decimal("4")),
    2: ("ncr", "NCR-DEMO-02", "Blockwork plumb tolerance exceeded on grid C, ground floor.",
        "Affected courses to be taken down and rebuilt before proceeding.", "in_progress", None),
    0: ("rfi", "RFI-DEMO-08", "Confirm reinforcement cover for first floor columns against the structural drawings.",
        "Submitted to the structural consultant.", "open", None),
}

NEXT_DAY_PLAN = {
    10: [("Continue ground floor blockwork, grid B-D", "Ground floor", 8, "Blocks, mortar, scaffolding", "Site foreman", "medium", "ready")],
    8: [("Start first floor column formwork, grid A-C", "First floor", 6, "Formwork panels, props", "Site foreman", "high", "ready")],
    6: [("Continue first floor column formwork; finish ground floor blockwork", "First floor / Ground floor", 10,
         "Formwork panels, blocks, mortar", "Site foreman", "high", "ready")],
    4: [("Pour first floor columns, grid A-C (pending cube test result)", "First floor", 8, "Ready-mix concrete, pump", "Site foreman", "high", "pending")],
    2: [("Continue first floor slab formwork", "First floor", 8, "Formwork panels, props", "Site foreman", "medium", "ready")],
    0: [("Continue first floor columns and slab per schedule (A3010)", "First floor", 8, "Reinforcement, formwork", "Site foreman", "high", "ready"),
        ("Close out ground floor blockwork punch-list", "Ground floor", 3, "Blocks, mortar", "Site foreman", "low", "ready")],
}


def is_seeded(project) -> bool:
    return DailyReport.objects.filter(project=project, report_number__startswith=NUMBER_PREFIX).exists()


def seed(project, engineering_manager, general_manager) -> dict:
    """Create the demo daily reports for `project`. Returns section counts."""
    today = timezone.localdate()
    site_engineer = project.site_engineer
    subitems = {s.code: s for s in ProjectPhaseSubItem.objects.filter(phase__project=project)}
    labor = {lc.name: lc for lc in LaborClassification.objects.all()}
    counts = dict(reports=0, workforce=0, equipment=0, activities=0, materials=0, visitors=0, attachments=0,
                  activity_progress=0, worker_attendance=0, site_events=0, next_day_plan=0)

    with transaction.atomic():
        for days_before, status, weather, remarks in REPORTS:
            report_date = today - timedelta(days=days_before)
            report = DailyReport.objects.create(
                project=project, site_engineer=site_engineer, weather_conditions=weather, remarks=remarks,
                status="draft", report_number=f"{NUMBER_PREFIX}{project.project_symbol}-{report_date:%Y%m%d}",
            )
            DailyReport.objects.filter(pk=report.pk).update(report_date=report_date)
            report.report_date = report_date
            counts["reports"] += 1

            for category, designation, count in WORKFORCE[days_before]:
                DailyWorkForce.objects.create(report=report, category=category, designation=designation, count=count)
                counts["workforce"] += 1

            for name, hours, idle in EQUIPMENT[days_before]:
                DailyEquipment.objects.create(report=report, equipment_name=name, hours_worked=hours, quantity_idle=idle)
                counts["equipment"] += 1

            for activity_type, location, description in ACTIVITIES[days_before]:
                DailyActivity.objects.create(report=report, activity_type=activity_type, location=location, activity_description=description)
                counts["activities"] += 1

            for description, quantity, unit in MATERIALS[days_before]:
                DailyMaterial.objects.create(report=report, material_description=description, quantity=quantity, unit=unit)
                counts["materials"] += 1

            for visit_time, visitor_name, representing in VISITORS[days_before]:
                DailyVisitor.objects.create(report=report, visit_time=visit_time, visitor_name=visitor_name, representing=representing)
                counts["visitors"] += 1

            for order, (caption, location, color) in enumerate(PHOTOS[days_before], start=1):
                attachment = ReportAttachment(
                    report_type="daily", report_id=report.id, attachment_type="photo",
                    description=caption, location=location, order=order, uploaded_by=site_engineer,
                )
                attachment.file = _photo(f"{caption} [DEMO]", color)
                attachment.save()
                counts["attachments"] += 1

            progress_rows = [(subitems[code], cum, qty, st, "Ground / first floor") for code, rows in PROGRESS.items()
                              for d, cum, qty, st in rows if d == days_before]
            if days_before == max(d for d, *_ in REPORTS):
                progress_rows += [(subitems[code], total, Decimal("0"), status, "Foundations") for code, total, status in FOUNDATIONS_DONE]
            for sub_item, cumulative, today_qty, entry_status, location in progress_rows:
                pct = (cumulative / sub_item.quantity * 100).quantize(Decimal("0.01")) if sub_item.quantity else Decimal("0")
                DailyReportActivityProgress.objects.create(
                    report=report, sub_item=sub_item, activity_description=f"{sub_item.name_en or sub_item.name_ar} ({sub_item.phase.name_en or sub_item.phase.name_ar})",
                    location=location, unit=sub_item.unit, total_quantity=sub_item.quantity, quantity_today=today_qty,
                    quantity_cumulative=cumulative, completion_percentage=min(pct, Decimal("100")), status=entry_status,
                )
                counts["activity_progress"] += 1

            for worker_name, classification_name, contractor, location, time_in, time_out in ATTENDANCE[days_before]:
                DailyReportWorkerAttendance.objects.create(
                    report=report, worker_name=worker_name, labor_classification=labor.get(classification_name),
                    contractor_name=contractor, activity_location=location, time_in=time_in, time_out=time_out,
                )
                counts["worker_attendance"] += 1

            DailyReportQAQC.objects.create(report=report, **QAQC[days_before])

            event_type, reference, description, required_action, event_status, time_impact = SITE_EVENTS[days_before]
            SiteEvent.objects.create(
                project=project, daily_report=report, event_type=event_type, reference=f"{EVENT_TAG}{reference}" if reference else EVENT_TAG.rstrip("-"),
                event_date=report_date, description=description, required_action=required_action, status=event_status,
                time_impact_hours=time_impact, responsible_party="Site team", created_by=site_engineer,
            )
            counts["site_events"] += 1

            for planned_activity, location, manpower, resources, responsible, priority, readiness in NEXT_DAY_PLAN[days_before]:
                DailyReportNextDayPlan.objects.create(
                    report=report, planned_activity=planned_activity, location=location, manpower_required=manpower,
                    resources_required=resources, responsible_party=responsible, priority=priority, readiness=readiness,
                )
                counts["next_day_plan"] += 1

            # ---- drive the report through the same status transitions the review views perform
            if status in ("submitted", "engineering_approved", "approved", "rejected"):
                report.status = "submitted"
                report.save()
            if status in ("engineering_approved", "approved") or (status == "rejected" and days_before == 10):
                report.reviewed_by = engineering_manager
                report.review_date = timezone.make_aware(timezone.datetime.combine(report_date, time(17, 0)))
                report.status = "engineering_approved" if status != "rejected" else "rejected"
                if status == "rejected":
                    report.rejection_reason = "Please add more detail on the near-miss (root cause, corrective action, photos) in the QA/QC section before resubmitting."
                report.save()
            if status == "approved":
                report.approved_by = general_manager
                report.approval_date = timezone.make_aware(timezone.datetime.combine(report_date, time(18, 0)))
                report.status = "approved"
                report.save()

    return counts


def clear(project) -> None:
    """Remove everything `seed` made for the project, including stored files."""
    if project is None:
        return
    report_ids = list(DailyReport.objects.filter(project=project, report_number__startswith=NUMBER_PREFIX).values_list("id", flat=True))
    if not report_ids:
        return
    ProjectPhaseProgressEntry.objects.filter(daily_report_id__in=report_ids).delete()
    SiteEvent.objects.filter(daily_report_id__in=report_ids).delete()
    for attachment in ReportAttachment.objects.filter(report_type="daily", report_id__in=report_ids):
        attachment.file.delete(save=False)
    ReportAttachment.objects.filter(report_type="daily", report_id__in=report_ids).delete()
    DailyReport.objects.filter(id__in=report_ids).delete()
