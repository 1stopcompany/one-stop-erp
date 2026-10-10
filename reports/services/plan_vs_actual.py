"""
The plan (MS Project) against the actual progress, phase by phase.

Each BOQ phase is linked to the plan tasks that carry its work (PhaseScheduleLink). For a date D:
  * a plan task is planned to be (D - start + 1) / (finish - start + 1) done between its start and finish (0 before, 1 after);
  * a phase's planned fraction is the duration-weighted average of its tasks;
  * the project's planned % is the sum of weight x planned fraction. A phase with no link has no plan to compare with: it is
    counted at its actual progress, so it neither helps nor hurts the comparison;
  * "Project management" style phases that run the whole job use the plan's whole span (link to task 0).
The actual % comes from the BOQ progress entries (calculate_project_progress), exactly what the owner's report uses.
"""
from datetime import date
from decimal import Decimal

from reports.progress_models import ProjectPhase, calculate_project_progress
from reports.schedule_models import PhaseScheduleLink, ScheduleTask

ZERO = Decimal('0')
WHOLE_PROJECT = 0          # link value meaning "the whole plan span"
TOLERANCE = Decimal('2')   # percentage points around "on track"


def _fraction(start, finish, day):
    if day < start:
        return ZERO
    if day >= finish:
        return Decimal('1')
    return Decimal((day - start).days + 1) / Decimal((finish - start).days + 1)


def phase_plan(project, as_of):
    """{phase id: {'planned': Decimal fraction 0..1, 'start', 'finish', 'tasks': n}} for every phase that has links."""
    tasks = {t.unique_id: t for t in ScheduleTask.objects.filter(project=project)}
    all_start = min((t.start_date for t in tasks.values() if t.start_date), default=None)
    all_finish = max((t.finish_date for t in tasks.values() if t.finish_date), default=None)
    links = {}
    for link in PhaseScheduleLink.objects.filter(phase__project=project):
        links.setdefault(link.phase_id, []).append(link.task_unique_id)
    plan = {}
    for phase_id, uids in links.items():
        parts = []   # (weight, start, finish)
        for uid in uids:
            if uid == WHOLE_PROJECT and all_start and all_finish:
                parts.append(((all_finish - all_start).days + 1, all_start, all_finish))
            elif uid in tasks and tasks[uid].start_date and tasks[uid].finish_date:
                task = tasks[uid]
                weight = task.duration_days if task.duration_days else (task.finish_date - task.start_date).days + 1
                parts.append((Decimal(weight), task.start_date, task.finish_date))
        if not parts:
            continue
        total = sum((Decimal(w) for w, _, _ in parts), ZERO)
        planned = sum((Decimal(w) * _fraction(s, f, as_of) for w, s, f in parts), ZERO) / total if total else ZERO
        plan[phase_id] = {'planned': planned, 'start': min(s for _, s, _ in parts), 'finish': max(f for _, _, f in parts), 'tasks': len(parts)}
    return plan


def plan_vs_actual(project, as_of=None):
    """
    {'as_of', 'rows': [{'phase', 'weight', 'planned', 'actual', 'variance', 'status', 'start', 'finish', 'linked'}],
     'planned_total', 'actual_total', 'variance_total', 'status_total'} -- percentages as Decimals 0..100.
    """
    as_of = as_of or date.today()
    progress = calculate_project_progress(project, as_of_date=as_of)
    actual_by_phase = {row['phase'].pk: row['execution_percentage'] for row in progress['phases']}
    plan = phase_plan(project, as_of)
    rows, planned_total, actual_total = [], ZERO, ZERO
    for phase in ProjectPhase.objects.filter(project=project).order_by('order', 'code'):
        weight = phase.weight_percentage or ZERO
        actual = Decimal(actual_by_phase.get(phase.pk, ZERO))
        info = plan.get(phase.pk)
        planned = (info['planned'] * 100) if info else actual     # no plan link: neutral
        variance = actual - planned
        rows.append({
            'phase': phase, 'weight': weight, 'planned': planned, 'actual': actual, 'variance': variance, 'linked': bool(info),
            'start': info['start'] if info else None, 'finish': info['finish'] if info else None,
            'status': _status(variance) if info else 'none',
        })
        planned_total += weight * planned / 100
        actual_total += weight * actual / 100
    variance_total = actual_total - planned_total
    return {'as_of': as_of, 'rows': rows, 'planned_total': planned_total, 'actual_total': actual_total, 'variance_total': variance_total,
            'status_total': _status(variance_total)}


def _status(variance):
    if variance < -TOLERANCE:
        return 'behind'
    if variance > TOLERANCE:
        return 'ahead'
    return 'on_track'


def sync_task_progress(project, as_of=None, apply=False, phase_codes=None):
    """
    Writes each linked plan task's % complete from the phase's actual progress: the phase's done share of its total duration is
    filled task by task in plan order (earliest first), so a phase that is 45% done shows its first tasks complete and the next
    one partly. Returns [(task, old %, new %)]; nothing is written unless apply=True. The whole-project
    link is skipped; `phase_codes` limits it to those BOQ phases (None = every linked phase).
    """
    as_of = as_of or date.today()
    progress = calculate_project_progress(project, as_of_date=as_of)
    actual_by_phase = {row['phase'].pk: Decimal(row['execution_percentage']) for row in progress['phases']}
    tasks = {t.unique_id: t for t in ScheduleTask.objects.filter(project=project)}
    changes = []
    for phase in ProjectPhase.objects.filter(project=project):
        if phase_codes is not None and phase.code not in phase_codes:
            continue
        uids = [l.task_unique_id for l in PhaseScheduleLink.objects.filter(phase=phase) if l.task_unique_id in tasks]
        linked = sorted((tasks[u] for u in uids), key=lambda t: (t.start_date or date.max, t.source_task_id))
        if not linked:
            continue
        durations = [Decimal(t.duration_days or 1) for t in linked]
        remaining = sum(durations, ZERO) * actual_by_phase.get(phase.pk, ZERO) / 100
        for task, duration in zip(linked, durations):
            filled = min(remaining, duration)
            remaining -= filled
            new = (filled / duration * 100).quantize(Decimal('0.01'))
            if new != task.percent_complete:
                changes.append((task, task.percent_complete, new))
    if apply:
        for task, _, new in changes:
            task.percent_complete = new
            task.save(update_fields=['percent_complete', 'imported_at'])
    return changes
