"""
Auto-generate a draft Monthly Report from a project's Daily Reports.

Pulls every Daily Report in a given calendar month (workforce, worker
attendance, equipment, activities/activity-progress, materials, QA/QC &
HSE, next-day plans) plus the project's BOQ progress and Site Events log,
aggregates them, and creates a MonthlyReport (status='draft') with its
narrative fields and child rows (MonthlyKeyActivity, MaterialSupply,
MonthlyProgressCategoryItem, MonthlyIssueRiskDelay) pre-filled from real
data. The result is a starting draft for the project manager to review,
adjust, and submit -- not a final report.
"""

import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from ..models import (
    DailyReport, DailyWorkForce, DailyEquipment, DailyActivity, DailyMaterial,
    MonthlyReport, MaterialSupply, MonthlyKeyActivity, MonthlyProgressCategoryItem,
    MonthlyIssueRiskDelay,
)
from ..daily_detail_models import (
    DailyReportWorkerAttendance, DailyReportActivityProgress, DailyReportQAQC,
    DailyReportNextDayPlan,
)
from ..site_event_models import SiteEvent
from ..progress_models import calculate_project_progress

# DailyReportActivityProgress.STATUS_CHOICES has an 'on_hold' option that
# MonthlyKeyActivity.STATUS_CHOICES doesn't -- map it to the closest
# equivalent so the generated row still saves with a valid choice.
_ACTIVITY_STATUS_MAP = {
    'not_started': 'not_started',
    'in_progress': 'in_progress',
    'completed': 'completed',
    'delayed': 'delayed',
    'on_hold': 'delayed',
}


class MonthlyReportGenerationError(ValueError):
    """Raised when there isn't enough real data to generate a report."""


def month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _most_common(values, default=None):
    values = [v for v in values if v]
    if not values:
        return default
    return Counter(values).most_common(1)[0][0]


def _fmt_qty(value):
    value = Decimal(value)
    normalized = value.normalize()
    return f'{normalized:f}' if normalized == normalized.to_integral() else f'{value}'


def generate_monthly_report(project, year, month, author):
    """
    Build and save a draft MonthlyReport (plus child rows) for `project`
    covering the given calendar month. Thin wrapper around
    generate_report_for_period() for the common "one full calendar month"
    case; see that function for what gets aggregated.
    """
    start_date, end_date = month_bounds(year, month)
    return generate_report_for_period(project, start_date, end_date, author)


@transaction.atomic
def generate_report_for_period(project, start_date, end_date, author):
    """
    Build and save a draft MonthlyReport (plus child rows) for `project`
    covering an arbitrary [start_date, end_date] period, aggregated from
    that period's real Daily Reports. The period doesn't have to be a full
    calendar month -- a partial-month "how are we doing so far" check is a
    valid use too. Returns the created MonthlyReport. Raises
    MonthlyReportGenerationError if there is nothing to generate from, or
    if a report already exists for that exact project/period.
    """
    if MonthlyReport.objects.filter(
        project=project, reporting_period_from=start_date, reporting_period_to=end_date,
    ).exclude(status='rejected').exists():
        raise MonthlyReportGenerationError(
            'A monthly report already exists for this project and period. '
            'Edit it directly, or use "New Revision" instead of generating a new one.'
        )

    daily_reports = list(
        DailyReport.objects.filter(
            project=project, report_date__gte=start_date, report_date__lte=end_date,
        ).exclude(status='rejected').order_by('report_date')
    )

    if not daily_reports:
        raise MonthlyReportGenerationError(
            f'No daily reports found for {project.name} between {start_date:%d/%m/%Y} and {end_date:%d/%m/%Y}.'
        )

    report_count = len(daily_reports)

    # ---- Weather: whichever condition shows up most across the period ----
    weather = _most_common(
        (dr.weather_conditions for dr in daily_reports), default='sunny',
    )
    if weather not in dict(MonthlyReport.WEATHER_CHOICES):
        weather = 'mixed'

    # ---- Workforce / man-hours (legacy headcount model + named-worker attendance) ----
    workforce_total = DailyWorkForce.objects.filter(report__in=daily_reports).aggregate(
        total=Sum('count')
    )['total'] or 0
    attendance_qs = DailyReportWorkerAttendance.objects.filter(report__in=daily_reports)
    total_man_hours = attendance_qs.aggregate(total=Sum('total_hours'))['total'] or Decimal('0')
    distinct_workers = attendance_qs.values('worker_name').distinct().count()

    # ---- Equipment ----
    equipment_hours = DailyEquipment.objects.filter(report__in=daily_reports).aggregate(
        total=Sum('hours_worked')
    )['total'] or 0

    # ---- Activities: legacy free-text log + BOQ-linked activity progress ----
    legacy_activity_descriptions = list(
        DailyActivity.objects.filter(report__in=daily_reports)
        .order_by('created_at').values_list('activity_description', flat=True)
    )

    latest_progress_by_activity = {}
    for row in DailyReportActivityProgress.objects.filter(report__in=daily_reports).order_by(
        'report__report_date', 'id'
    ):
        latest_progress_by_activity[row.activity_description] = row  # last write wins -> latest date

    # ---- Materials: aggregate delivered quantity per (description, unit) ----
    material_totals = defaultdict(lambda: Decimal('0'))
    material_display = {}
    material_counts = Counter()
    for m in DailyMaterial.objects.filter(report__in=daily_reports):
        key = (m.material_description.strip().lower(), m.unit.strip())
        material_totals[key] += m.quantity
        material_display[key] = (m.material_description.strip(), m.unit.strip())
        material_counts[key] += 1

    # ---- QA/QC & HSE ----
    qaqc_qs = DailyReportQAQC.objects.filter(report__in=daily_reports)
    qaqc_count = qaqc_qs.count()
    inspection_counts = Counter(qaqc_qs.values_list('inspection_status', flat=True))
    toolbox_talks = DailyReportQAQC.toolbox_talks_conducted_for_period(project, start_date, end_date)
    site_inspections = qaqc_qs.exclude(inspection_status='not_applicable').count()
    hse = SiteEvent.hse_summary_for_period(project, start_date, end_date)

    # ---- Non-HSE site events (delays, site instructions, RFIs, NCRs) ----
    other_events = list(
        SiteEvent.for_period(project, start_date, end_date)
        .exclude(event_type__in=['hse_incident', 'near_miss'])
        .order_by('event_date')
    )
    ncr_events = [e for e in other_events if e.event_type == 'ncr']

    # ---- BOQ progress: cumulative as of period end, and delta over the period ----
    progress_end = calculate_project_progress(project, as_of_date=end_date)
    progress_before = calculate_project_progress(project, as_of_date=start_date - timedelta(days=1))
    overall_pct = progress_end['overall_percentage']
    pct_delta = overall_pct - progress_before['overall_percentage']

    # ---- Next month plan: the most recent daily report's "next day plan" rows ----
    next_plan_lines = []
    for dr in reversed(daily_reports):
        plans = list(DailyReportNextDayPlan.objects.filter(report=dr))
        if plans:
            next_plan_lines = [f'- {p.planned_activity}' + (f' ({p.location})' if p.location else '') for p in plans]
            break

    key_activity_names = legacy_activity_descriptions + list(latest_progress_by_activity.keys())

    executive_summary = _build_executive_summary(
        project, start_date, end_date, report_count, overall_pct, pct_delta,
        total_man_hours, distinct_workers, workforce_total, equipment_hours,
        key_activity_names, hse,
    )

    general_description = (
        f'Automatically compiled from {report_count} daily site report(s) submitted for '
        f'{project.project_symbol} between {start_date:%d/%m/%Y} and {end_date:%d/%m/%Y}.'
    )

    report = MonthlyReport.objects.create(
        project=project,
        site_engineer=author,
        weather_conditions=weather,
        general_description=general_description,
        executive_summary=executive_summary,
        hse_lti_note=str(hse['hse_incidents']),
        hse_near_misses_note=str(hse['near_misses']),
        hse_toolbox_talks_note=str(toolbox_talks),
        hse_site_inspections_note=str(site_inspections),
        hse_corrective_actions_note=f"{hse['corrective_actions_open']} Open / {hse['corrective_actions_closed']} Closed",
        qc_inspections_note=_build_qc_inspections_note(inspection_counts, qaqc_count),
        qc_nonconformances_note=_build_ncr_note(ncr_events),
        next_month_plan='\n'.join(next_plan_lines),
        reporting_period_from=start_date,
        reporting_period_to=end_date,
    )

    _create_key_activities(report, legacy_activity_descriptions, latest_progress_by_activity)
    _create_material_supplies(report, material_totals, material_display, material_counts)
    _create_progress_category_items(report, progress_end)
    _create_issues_risks_delays(report, other_events)

    return report


def compute_dashboard_data(report):
    """
    Re-derive the numeric figures behind a MonthlyReport's narrative
    fields, straight from the underlying Daily Reports/BOQ progress --
    for rendering an executive dashboard (charts, KPI cards) rather than
    parsing the free-text notes generate_report_for_period() wrote into
    the report itself.
    """
    project = report.project
    start_date, end_date = report.reporting_period_from, report.reporting_period_to

    daily_reports = list(
        DailyReport.objects.filter(
            project=project, report_date__gte=start_date, report_date__lte=end_date,
        ).exclude(status='rejected').order_by('report_date')
    )

    attendance_qs = DailyReportWorkerAttendance.objects.filter(report__in=daily_reports)
    total_man_hours = attendance_qs.aggregate(total=Sum('total_hours'))['total'] or Decimal('0')
    distinct_workers = attendance_qs.values('worker_name').distinct().count()

    manhours_by_date = defaultdict(Decimal)
    for row in attendance_qs.select_related('report'):
        manhours_by_date[row.report.report_date] += row.total_hours or Decimal('0')
    manhours_series = [
        {'date': d.strftime('%d/%m'), 'hours': float(manhours_by_date.get(d, Decimal('0')))}
        for d in sorted({dr.report_date for dr in daily_reports})
    ]

    equipment_hours = DailyEquipment.objects.filter(report__in=daily_reports).aggregate(
        total=Sum('hours_worked')
    )['total'] or 0

    qaqc_qs = DailyReportQAQC.objects.filter(report__in=daily_reports)
    inspection_counts = Counter(qaqc_qs.values_list('inspection_status', flat=True))

    hse = SiteEvent.hse_summary_for_period(project, start_date, end_date)

    progress_end = calculate_project_progress(project, as_of_date=end_date)
    progress_before = calculate_project_progress(project, as_of_date=start_date - timedelta(days=1))
    overall_pct = progress_end['overall_percentage']
    pct_delta = overall_pct - progress_before['overall_percentage']

    phase_progress = [
        {
            'name': row['phase'].name_en or row['phase'].name_ar,
            'pct': float(row['execution_percentage']),
        }
        for row in progress_end['phases']
    ]

    activity_status_counts = Counter(report.key_activities.values_list('status', flat=True))

    return {
        'report_count': len(daily_reports),
        'total_man_hours': total_man_hours,
        'distinct_workers': distinct_workers,
        'manhours_series': manhours_series,
        'equipment_hours': equipment_hours,
        'qc_passed': inspection_counts.get('passed', 0),
        'qc_failed': inspection_counts.get('failed', 0),
        'qc_pending': inspection_counts.get('pending', 0),
        'qc_total': qaqc_qs.count(),
        'hse': hse,
        'overall_pct': overall_pct,
        'pct_delta': pct_delta,
        'phase_progress': phase_progress,
        'activity_status_counts': dict(activity_status_counts),
        'materials': list(report.material_supplies.all()),
        'issues': list(report.issues_risks_delays.all()),
        'key_activities': list(report.key_activities.all()),
    }


def _build_qc_inspections_note(inspection_counts, qaqc_count):
    if not qaqc_count:
        return ''
    passed = inspection_counts.get('passed', 0)
    failed = inspection_counts.get('failed', 0)
    pending = inspection_counts.get('pending', 0)
    return (
        f'{passed} passed, {failed} failed, {pending} pending '
        f'(based on {qaqc_count} daily QA/QC record(s) this period).'
    )


def _build_ncr_note(ncr_events):
    if not ncr_events:
        return ''
    open_count = sum(1 for e in ncr_events if e.status != 'closed')
    closed_count = sum(1 for e in ncr_events if e.status == 'closed')
    return f'{len(ncr_events)} NCR(s) raised this period ({open_count} open, {closed_count} closed).'


def _build_executive_summary(
    project, start_date, end_date, report_count, overall_pct, pct_delta,
    total_man_hours, distinct_workers, workforce_total, equipment_hours,
    key_activity_names, hse,
):
    # project.project_symbol (a Latin code, e.g. "TAB") is used here rather
    # than project.name (usually Arabic) -- embedding Arabic mid-sentence
    # inside an otherwise English paragraph makes bidi/PDF rendering of
    # this narrative unreliable (see generate_monthly_dashboard_pdf).
    paragraphs = [
        (
            f'This report covers {project.project_symbol} site activities for the period '
            f'{start_date:%d/%m/%Y} to {end_date:%d/%m/%Y}, compiled from {report_count} '
            f'daily site report(s) submitted during this period.'
        ),
        (
            f'Cumulative project progress stands at {overall_pct:.1f}% as of {end_date:%d/%m/%Y}'
            + (
                f', an increase of {pct_delta:.1f} percentage point(s) during this period.'
                if pct_delta > 0 else '.'
            )
        ),
    ]

    if distinct_workers or workforce_total:
        labor_bits = []
        if distinct_workers:
            labor_bits.append(f'{distinct_workers} named worker(s) logging {total_man_hours:.1f} man-hours')
        if workforce_total:
            labor_bits.append(f'{workforce_total} workforce headcount-day(s) recorded')
        paragraphs.append('Labor on site: ' + '; '.join(labor_bits) + '.')

    if equipment_hours:
        paragraphs.append(f'Equipment logged {equipment_hours} operating hour(s) during this period.')

    distinct_key_activities = list(dict.fromkeys(key_activity_names))
    if distinct_key_activities:
        # Each activity name on its own line rather than semicolon-joined
        # into the lead-in sentence -- these are often Arabic free text,
        # and a line that mixes an English clause with several Arabic
        # phrases renders unreliably in bidi/PDF contexts (see
        # generate_monthly_dashboard_pdf). One name per line keeps every
        # line either purely English or purely Arabic.
        activity_lines = '\n'.join(f'- {name}' for name in distinct_key_activities[:6])
        paragraphs.append(f'Key activities carried out this period:\n{activity_lines}')

    if hse['hse_incidents'] or hse['near_misses']:
        paragraphs.append(
            f"{hse['hse_incidents']} HSE incident(s) and {hse['near_misses']} near-miss event(s) "
            f'were recorded during this period; see Issues, Risks & Delays below.'
        )
    else:
        paragraphs.append('No HSE incidents or near-misses were recorded during this period.')

    return '\n\n'.join(paragraphs)


def _create_key_activities(report, legacy_activity_descriptions, latest_progress_by_activity):
    order = 0
    seen = set()
    for description in legacy_activity_descriptions:
        if description in seen:
            continue
        seen.add(description)
        MonthlyKeyActivity.objects.create(
            report=report, activity=description, status='in_progress', order=order,
        )
        order += 1

    for description, row in latest_progress_by_activity.items():
        if description in seen:
            continue
        seen.add(description)
        remarks = f'{row.completion_percentage}% complete as of {row.report.report_date:%d/%m/%Y}'
        if row.quantity_cumulative:
            remarks += f' ({_fmt_qty(row.quantity_cumulative)} {row.unit or ""} cumulative)'.replace('  ', ' ')
        MonthlyKeyActivity.objects.create(
            report=report,
            activity=description,
            status=_ACTIVITY_STATUS_MAP.get(row.status, 'in_progress'),
            remarks=remarks.strip(),
            order=order,
        )
        order += 1


def _create_material_supplies(report, material_totals, material_display, material_counts):
    for order, (key, total) in enumerate(material_totals.items()):
        description, unit = material_display[key]
        count = material_counts[key]
        MaterialSupply.objects.create(
            report=report,
            material_type='material',
            material_description=description,
            quantity=total,
            unit=unit,
            delivered_quantity=total,
            remaining_notes=f'Aggregated from {count} daily material record(s).',
        )


def _create_progress_category_items(report, progress_end):
    for order, phase_row in enumerate(progress_end['phases']):
        phase = phase_row['phase']
        MonthlyProgressCategoryItem.objects.create(
            report=report,
            item_name=phase.name_en or phase.name_ar,
            actual_value=f"{phase_row['execution_percentage']:.1f}%",
            order=order,
        )


def _create_issues_risks_delays(report, other_events):
    for order, event in enumerate(other_events):
        impact = event.get_event_type_display()
        if event.time_impact_hours:
            impact += f' — {event.time_impact_hours} hour(s) schedule impact'
        MonthlyIssueRiskDelay.objects.create(
            report=report,
            description=event.description,
            impact=impact,
            mitigation=event.required_action,
            order=order,
        )
