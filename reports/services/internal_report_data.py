"""
Shared computations for the "Internal Monthly Report" -- the RAG status
summary, the BOQ progress-vs-schedule-baseline overview, the project
milestones summary, the earned-value (BAC/PV/EV/SV) analysis, and the
imported critical-path schedule.

Extracted into its own service (rather than living inline in
reports.utils.generate_internal_monthly_report_pdf) so the exact same
real numbers can be shown both in the PDF export and in the live
Monthly Report Dashboard page, without the two ever drifting apart.

Every value returned here is a plain Python type (Decimal/date/str/bool)
-- no ReportLab or Django-template-specific formatting -- so each caller
renders it in its own way.
"""

from decimal import Decimal

from .monthly_report_generator import compute_dashboard_data
from ..progress_models import calculate_project_progress, ProjectMilestone
from ..schedule_models import ScheduleTask

RAG_GREEN, RAG_AMBER, RAG_RED, RAG_GREY = 'green', 'amber', 'red', 'grey'
_RAG_ORDER = {RAG_GREEN: 0, RAG_AMBER: 1, RAG_RED: 2}


def _phase_baseline_pct(phase, as_of):
    """
    Time-based expected completion (0-100, of the phase's own weight),
    derived from each sub-item's planned_start_date/planned_completion_date.
    Returns None if the phase has no sub-items or any of them is missing
    a planned date -- a partial schedule can't honestly produce a baseline.
    """
    sub_items = list(phase.sub_items.all())
    phase_weight = phase.weight_percentage or Decimal('0')
    if not sub_items or phase_weight == 0:
        return None
    if any(si.planned_start_date is None or si.planned_completion_date is None for si in sub_items):
        return None
    earned = Decimal('0')
    for si in sub_items:
        if as_of <= si.planned_start_date:
            frac = Decimal('0')
        elif as_of >= si.planned_completion_date:
            frac = Decimal('1')
        else:
            total_days = (si.planned_completion_date - si.planned_start_date).days
            elapsed_days = (as_of - si.planned_start_date).days
            frac = (Decimal(elapsed_days) / Decimal(total_days)) if total_days else Decimal('1')
        earned += si.weight_percentage * frac
    return (earned / phase_weight) * Decimal('100')


def _compute_rag(report, data):
    delayed_count = data['activity_status_counts'].get('delayed', 0)
    completed_count = data['activity_status_counts'].get('completed', 0)
    in_progress_count = data['activity_status_counts'].get('in_progress', 0)
    total_activities = delayed_count + completed_count + in_progress_count

    deliverables_color = RAG_RED if delayed_count > 2 else (RAG_AMBER if delayed_count > 0 else RAG_GREEN)
    deliverables_remark = f'{delayed_count} delayed activity(ies) out of {total_activities}' if total_activities else 'No activities recorded'

    hse_incidents = data['hse']['hse_incidents']
    hse_near_misses = data['hse']['near_misses']
    hse_color = RAG_RED if hse_incidents > 0 else (RAG_AMBER if hse_near_misses > 0 else RAG_GREEN)
    hse_remark = f'{hse_incidents} incident(s), {hse_near_misses} near-miss case(s)' if (hse_incidents or hse_near_misses) else 'No incidents or near-misses'

    pct_delta = data['pct_delta']
    schedule_color = RAG_GREEN if pct_delta >= 0 else (RAG_AMBER if pct_delta >= -2 else RAG_RED)
    schedule_remark = f'Progress this period: {pct_delta:+.1f} percentage points'

    issues_count = len(data['issues'])
    risks_color = RAG_RED if issues_count > 3 else (RAG_AMBER if issues_count > 0 else RAG_GREEN)
    risks_remark = f'{issues_count} issue(s)/risk(s) logged this period' if issues_count else 'No open risks'

    cost_remark = 'No link to an actual budget yet (pending Cost Control integration)'

    overall_color = max([deliverables_color, hse_color, schedule_color, risks_color], key=lambda c: _RAG_ORDER[c])

    return {
        'deliverables': {'color': deliverables_color, 'remark': deliverables_remark},
        'hse': {'color': hse_color, 'remark': hse_remark},
        'schedule': {'color': schedule_color, 'remark': schedule_remark},
        'cost': {'color': RAG_GREY, 'remark': cost_remark},
        'risks': {'color': risks_color, 'remark': risks_remark},
        'overall': {'color': overall_color, 'remark': 'Rating based on the highest alert level among the items above'},
    }


def _compute_progress_overview(project, report, data, progress_now):
    as_of = report.reporting_period_to
    rows = []
    total_phase_weight = Decimal('0')
    covered_weight = Decimal('0')
    covered_baseline_weighted = Decimal('0')
    covered_actual_weighted = Decimal('0')

    for row in progress_now['phases']:
        phase = row['phase']
        actual = row['execution_percentage']
        total_phase_weight += phase.weight_percentage or Decimal('0')
        baseline = _phase_baseline_pct(phase, as_of)
        if baseline is None:
            rows.append({
                'phase_name': phase.name_en or phase.name_ar,
                'baseline_pct': None, 'actual_pct': actual, 'variance_pct': None,
                'remark': 'No planned dates set for this phase',
            })
        else:
            variance = actual - baseline
            rows.append({
                'phase_name': phase.name_en or phase.name_ar,
                'baseline_pct': baseline, 'actual_pct': actual, 'variance_pct': variance,
                'remark': 'On or ahead of plan' if variance >= 0 else 'Behind planned schedule',
            })
            covered_weight += phase.weight_percentage
            covered_baseline_weighted += baseline * phase.weight_percentage
            covered_actual_weighted += actual * phase.weight_percentage

    complete = bool(progress_now['phases']) and covered_weight == total_phase_weight and total_phase_weight > 0
    if complete:
        overall_baseline = covered_baseline_weighted / covered_weight
        overall_actual = covered_actual_weighted / covered_weight
        overall = {
            'baseline_pct': overall_baseline, 'actual_pct': overall_actual,
            'variance_pct': overall_actual - overall_baseline, 'complete': True,
        }
    else:
        overall = {'baseline_pct': None, 'actual_pct': data['overall_pct'], 'variance_pct': None, 'complete': False}

    return {'rows': rows, 'overall': overall}


def _compute_milestones(project, report):
    milestones = list(
        ProjectMilestone.objects.filter(phase__project=project)
        .select_related('phase')
        .order_by('phase__order', 'phase__code', 'order', 'baseline_date')
    )
    if not milestones:
        return {'summary': [], 'list': []}

    period_from, period_to = report.reporting_period_from, report.reporting_period_to
    by_phase = {}
    for m in milestones:
        by_phase.setdefault(m.phase, []).append(m)

    summary = []
    for phase, items in by_phase.items():
        total = len(items)
        scheduled_period = sum(1 for m in items if period_from <= m.baseline_date <= period_to)
        completed_period = sum(1 for m in items if m.actual_date and period_from <= m.actual_date <= period_to)
        scheduled_to_date = sum(1 for m in items if m.baseline_date <= period_to)
        completed_to_date = sum(1 for m in items if m.actual_date and m.actual_date <= period_to)
        summary.append({
            'phase_name': phase.name_en or phase.name_ar,
            'total': total, 'scheduled_period': scheduled_period, 'completed_period': completed_period,
            'scheduled_to_date': scheduled_to_date, 'completed_to_date': completed_to_date,
            'variance': completed_to_date - scheduled_to_date,
        })

    milestone_list = [{
        'name': m.name_en or m.name_ar,
        'phase_name': m.phase.name_en or m.phase.name_ar,
        'baseline_date': m.baseline_date, 'forecast_date': m.forecast_date, 'actual_date': m.actual_date,
        'status': m.status,
    } for m in milestones]

    return {'summary': summary, 'list': milestone_list}


def _compute_eva(project, progress_now):
    contract_value = project.contract_value
    if not contract_value:
        return {'contract_value': None, 'rows': [], 'overall': None}

    rows = []
    overall_bac = contract_value
    overall_ev = Decimal('0')
    overall_pv_weighted = Decimal('0')
    overall_pv_weight = Decimal('0')
    total_phase_weight = Decimal('0')

    for row in progress_now['phases']:
        phase = row['phase']
        actual_pct = row['execution_percentage']
        phase_weight = phase.weight_percentage or Decimal('0')
        total_phase_weight += phase_weight
        bac = contract_value * phase_weight / Decimal('100')
        ev = bac * actual_pct / Decimal('100')
        overall_ev += ev
        baseline_pct = _phase_baseline_pct(phase, progress_now['_report_period_to'])
        phase_name = phase.name_en or phase.name_ar
        if baseline_pct is None:
            rows.append({'phase_name': phase_name, 'bac': bac, 'pv': None, 'ev': ev, 'sv': None,
                         'remark': 'No schedule baseline to compute PV'})
        else:
            pv = bac * baseline_pct / Decimal('100')
            sv = ev - pv
            overall_pv_weighted += pv
            overall_pv_weight += phase_weight
            rows.append({'phase_name': phase_name, 'bac': bac, 'pv': pv, 'ev': ev, 'sv': sv,
                         'remark': 'Ahead of plan' if sv >= 0 else 'Behind plan'})

    complete = overall_pv_weight == total_phase_weight and total_phase_weight > 0
    if complete:
        overall = {
            'bac': overall_bac, 'pv': overall_pv_weighted, 'ev': overall_ev,
            'sv': overall_ev - overall_pv_weighted, 'complete': True,
        }
    else:
        overall = {'bac': overall_bac, 'pv': None, 'ev': overall_ev, 'sv': None, 'complete': False}

    return {'contract_value': contract_value, 'rows': rows, 'overall': overall}


def _compute_critical_path(project, report):
    tasks = list(ScheduleTask.objects.filter(project=project).order_by('source_task_id'))
    if not tasks:
        return {'schedule_start': None, 'schedule_finish': None, 'remaining_days': None,
                'source_file_name': '', 'tasks': []}

    all_starts = [t.start_date for t in tasks if t.start_date]
    all_finishes = [t.finish_date for t in tasks if t.finish_date]
    schedule_start = min(all_starts) if all_starts else None
    schedule_finish = max(all_finishes) if all_finishes else None
    remaining_days = (schedule_finish - report.reporting_period_to).days if schedule_finish else None

    critical_tasks = [{
        'name': t.name, 'start': t.start_date, 'finish': t.finish_date,
        'duration_text': t.duration_text, 'total_slack_days': t.total_slack_days,
    } for t in tasks if t.is_critical]

    return {
        'schedule_start': schedule_start, 'schedule_finish': schedule_finish,
        'remaining_days': remaining_days, 'source_file_name': tasks[0].source_file_name,
        'tasks': critical_tasks,
    }


def compute_internal_report_data(report):
    """
    Returns a dict with keys: dashboard, rag, progress_overview,
    milestones, eva, critical_path -- everything the internal monthly
    report PDF and the Monthly Report Dashboard page both need, computed
    once from the same real data. `dashboard` is compute_dashboard_data's
    own return value (key_activities, issues, hse, ...), included here so
    callers don't need to call it a second time.
    """
    project = report.project
    data = compute_dashboard_data(report)
    progress_now = calculate_project_progress(project, as_of_date=report.reporting_period_to)
    progress_now['_report_period_to'] = report.reporting_period_to  # internal, used by _compute_eva

    return {
        'dashboard': data,
        'rag': _compute_rag(report, data),
        'progress_overview': _compute_progress_overview(project, report, data, progress_now),
        'milestones': _compute_milestones(project, report),
        'eva': _compute_eva(project, progress_now),
        'critical_path': _compute_critical_path(project, report),
    }
