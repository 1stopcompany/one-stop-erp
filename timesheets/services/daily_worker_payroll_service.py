"""
Monthly pay for a DailyWorker (day-labor paid per day worked, who
commonly moves between several open projects within one month).

Source of truth: reports.DailyReportWorkerAttendance rows linked to this
worker via the `daily_worker` FK -- one row per worker per daily report,
each report already scoped to one project, so a worker's hours across
every project they touched that month can be pulled together correctly
just by querying "every attendance row for this worker in this date
range" and grouping by report.project.

Pay math (verified against a real August-2026 daily-wage sheet, matching
exactly on every row checked):
  regular_hours = total_hours - overtime_hours  (total_hours already has
    overtime folded in -- see DailyReportWorkerAttendance.save())
  days = regular_hours / 8
  pay = days * daily_worker.daily_rate + overtime_hours * (daily_worker.daily_rate / 8) * 1.5

The real sheet also books a fractional "Friday/rest-day" accrual (1 paid
day per 6 days worked) at a discounted "6/7" daily rate -- that bookkeeping
is mathematically self-cancelling (accrued_days * discounted_rate reduces
to exactly days_worked * full daily_rate), so it's deliberately not
reproduced here: this gives the identical total with a simpler formula.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP


def _round2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def compute_daily_worker_statement(worker, period_start, period_end):
    """
    One worker's monthly statement: total days/overtime/pay, broken down
    per project they worked at during [period_start, period_end].
    """
    from reports.daily_detail_models import DailyReportWorkerAttendance

    entries = DailyReportWorkerAttendance.objects.filter(
        daily_worker=worker,
        report__report_date__gte=period_start,
        report__report_date__lte=period_end,
    ).select_related('report', 'report__project')

    hourly_rate = worker.daily_rate / Decimal(8)
    zero = lambda: {'days': Decimal('0'), 'overtime_hours': Decimal('0'), 'advances': Decimal('0'),
                    'base_pay': Decimal('0'), 'overtime_pay': Decimal('0')}
    # project -> sub-group name ('' = the project itself) -> the figures of that sub-group
    parts = defaultdict(dict)

    # Attendance from the daily reports: hours per project and, when the site engineer named one, per sub-group (متفرقة).
    hours_by = defaultdict(lambda: {'regular_hours': Decimal('0'), 'overtime_hours': Decimal('0')})
    for entry in entries:
        overtime_hours = entry.overtime_hours or Decimal('0')
        regular_hours = max(Decimal('0'), (entry.total_hours or Decimal('0')) - overtime_hours)
        bucket = hours_by[(entry.report.project, entry.sub_name)]
        bucket['regular_hours'] += regular_hours
        bucket['overtime_hours'] += overtime_hours
    for (project, sub_name), hours in hours_by.items():
        part = parts[project].setdefault(sub_name, zero())
        part['days'] += hours['regular_hours'] / Decimal(8)
        part['overtime_hours'] += hours['overtime_hours']
        part['base_pay'] += _round2(hours['regular_hours'] / Decimal(8) * worker.daily_rate)
        part['overtime_pay'] += _round2(hours['overtime_hours'] * hourly_rate * Decimal('1.5'))

    # Admin-typed entries from the Wages Run's Manual Entry tab: total days, the daily rate typed with them (اليومية)
    # and overtime hours; priced at that rate, on top of whatever the daily reports already gave this project.
    # A worker can have several lines on one project (one per sub-group): they add up on the project.
    for entry in worker.manual_entries.filter(period_start=period_start).select_related('project'):
        part = parts[entry.project].setdefault(entry.sub_name, zero())
        part['days'] += entry.days
        part['overtime_hours'] += entry.overtime_hours
        part['advances'] += entry.advances
        part['base_pay'] += _round2(entry.days * entry.daily_rate)
        part['overtime_pay'] += _round2(entry.overtime_hours * (entry.daily_rate / Decimal(8)) * Decimal('1.5'))

    breakdown = []
    total_pay = Decimal('0')
    for project, subs in parts.items():
        days = sum((p['days'] for p in subs.values()), Decimal('0'))
        base_pay = sum((p['base_pay'] for p in subs.values()), Decimal('0'))
        overtime_pay = sum((p['overtime_pay'] for p in subs.values()), Decimal('0'))
        pay = base_pay + overtime_pay
        breakdown.append({
            'project': project,
            'days': _round2(days),
            'overtime_hours': _round2(sum((p['overtime_hours'] for p in subs.values()), Decimal('0'))),
            'base_pay': base_pay,
            'overtime_pay': overtime_pay,
            'pay': pay,
            'advances': sum((p['advances'] for p in subs.values()), Decimal('0')),
            'subs': subs,
        })
        total_pay += pay

    for row in breakdown:
        row['pay_share_pct'] = _round2(row['pay'] / total_pay * 100) if total_pay else Decimal('0')

    breakdown.sort(key=lambda r: r['pay'], reverse=True)

    return {
        'worker': worker,
        'period_start': period_start,
        'period_end': period_end,
        'by_project': breakdown,
        'total_days': _round2(sum((row['days'] for row in breakdown), Decimal('0'))),
        'total_overtime_hours': _round2(sum((row['overtime_hours'] for row in breakdown), Decimal('0'))),
        'total_pay': _round2(total_pay),
        'total_advances': _round2(sum((row['advances'] for row in breakdown), Decimal('0'))),
    }


def compute_all_daily_workers_summary(period_start, period_end):
    """One statement per active DailyWorker who has at least one attendance row in the period."""
    from timesheets.models import DailyWorker

    statements = []
    for worker in DailyWorker.objects.filter(is_active=True):
        statement = compute_daily_worker_statement(worker, period_start, period_end)
        if statement['by_project']:
            statements.append(statement)

    statements.sort(key=lambda s: s['total_pay'], reverse=True)
    return statements


def prune_empty_draft_slips(period_start, period_end):
    """
    Delete the draft wage slips of a month that have nothing left behind them: no attendance, no manual entry
    and no allowance/deduction/advance typed on the row. They are left over after the entries that created them
    were cleared or removed, and would otherwise keep showing as all-zero rows in the Wages Run. Posted slips and
    drafts that still carry HR-typed figures are never touched. Returns how many were deleted.
    """
    from timesheets.models import DailyWorkerPayslip

    removed = 0
    for slip in DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end, status='draft').select_related('worker'):
        if slip.other_allowances or slip.other_deductions or slip.advances:
            continue
        if compute_daily_worker_statement(slip.worker, period_start, period_end)['by_project']:
            continue
        slip.delete()
        removed += 1
    return removed


def project_totals(statements):
    """
    Flip the per-worker statements around: one row per project with the
    total across every day-labor worker who worked there in the period
    (worker count, days, overtime hours, base/overtime/total pay), biggest
    cost first. `project` is None for attendance not tied to a project.
    """
    totals = {}
    for statement in statements:
        for row in statement['by_project']:
            key = row['project'].pk if row['project'] else None
            bucket = totals.setdefault(key, {
                'project': row['project'], 'workers': 0, 'days': Decimal('0'), 'overtime_hours': Decimal('0'),
                'base_pay': Decimal('0'), 'overtime_pay': Decimal('0'), 'pay': Decimal('0'),
            })
            bucket['workers'] += 1
            bucket['days'] += row['days']
            bucket['overtime_hours'] += row['overtime_hours']
            bucket['base_pay'] += row['base_pay']
            bucket['overtime_pay'] += row['overtime_pay']
            bucket['pay'] += row['pay']
    return sorted(totals.values(), key=lambda r: r['pay'], reverse=True)


def compute_daily_worker_payslip(
    worker, period_start, period_end, *,
    other_allowances=Decimal('0'), other_deductions=Decimal('0'), advances=Decimal('0'), generated_by=None,
):
    """
    Persisted, reviewable/editable "كشف الصرف" for one worker/month -- the
    DailyWorker equivalent of payroll_service.compute_payslip_salaried,
    same posted-guard and same update_or_create pattern (see
    timesheets.models.DailyWorkerPayslip and timesheets.views.wages_run).
    """
    from timesheets.models import DailyWorkerPayslip

    existing = DailyWorkerPayslip.objects.filter(worker=worker, period_start=period_start, period_end=period_end).first()
    if existing and existing.status == 'posted':
        return existing

    statement = compute_daily_worker_statement(worker, period_start, period_end)
    base_pay = sum((row['base_pay'] for row in statement['by_project']), Decimal('0'))
    overtime_pay = sum((row['overtime_pay'] for row in statement['by_project']), Decimal('0'))

    fields = dict(
        total_days=statement['total_days'], overtime_hours=statement['total_overtime_hours'],
        base_pay=_round2(base_pay), overtime_pay=_round2(overtime_pay),
        other_allowances=_round2(other_allowances), other_deductions=_round2(other_deductions),
        advances=_round2(advances), line_advances=statement['total_advances'], generated_by=generated_by,
    )
    payslip, _ = DailyWorkerPayslip.objects.update_or_create(
        worker=worker, period_start=period_start, period_end=period_end, defaults=fields,
    )
    return payslip


def wages_sheet(period_start, period_end):
    """
    The month laid out like the company's own "كشف اجور عمال" sheet: one section per
    project, each with a line per worker carrying every column of that sheet --
    days worked, Friday days (days / 6), total days incl. Fridays, daily wage
    (paid rate x 6 / 7), paid rate, total (paid rate x days), overtime hours, hour
    rate (paid rate / 8 x 1.5), overtime value, amount due, advances and net --
    plus a per-section total and a grand total.

    Anything entered on the Wages Run row itself (allowances, deductions, advances
    that belong to the worker rather than to one project) has no column in that
    sheet, so it is listed in `adjustments` and counted in `grand_total`, which
    therefore always equals the sum of the workers' net pay.
    """
    from timesheets.models import DailyWorkerPayslip

    statements = compute_all_daily_workers_summary(period_start, period_end)
    sections = {}
    for statement in statements:
        worker = statement['worker']
        for row in statement['by_project']:
            key = row['project'].pk if row['project'] else None
            section = sections.setdefault(key, {'project': row['project'], 'rows': []})
            # a project with sub-groups (متفرقات) gets one line per worker and sub-group, otherwise one line per worker
            if any(row['subs']):
                parts = [(name, figures) for name, figures in row['subs'].items()]
            else:
                parts = [('', row)]
            for sub_name, part in parts:
                days = _round2(part['days'])
                paid_rate = _round2(part['base_pay'] / days) if days else worker.daily_rate
                friday = days / Decimal(6)
                due = part['base_pay'] + part['overtime_pay']
                section['rows'].append({
                    'worker': worker, 'trade': worker.trade, 'national_id': worker.national_id or '', 'sub': sub_name,
                    'days': days, 'friday_days': friday, 'total_days': days + friday,
                    'daily_wage': paid_rate * Decimal(6) / Decimal(7), 'paid_rate': paid_rate,
                    'total': part['base_pay'], 'overtime_hours': _round2(part['overtime_hours']),
                    'hour_rate': paid_rate / Decimal(8) * Decimal('1.5'), 'overtime_value': part['overtime_pay'],
                    'due': due, 'advances': part['advances'], 'net': due - part['advances'],
                })

    ordered = sorted(sections.values(), key=lambda sec: (sec['project'].name if sec['project'] else '￿'))
    for section in ordered:
        names = sorted({r['sub'] for r in section['rows']}, key=lambda n: (n != '', n))   # the project itself first
        section['has_subs'] = any(names)
        section['groups'] = []
        flat = []
        for name in names:
            lines = sorted((r for r in section['rows'] if r['sub'] == name), key=lambda r: r['worker'].full_name)
            for n, line in enumerate(lines, start=1):
                line['n'] = n
            section['groups'].append({
                'name': name, 'rows': lines,
                'total_due': sum((r['due'] for r in lines), Decimal('0')),
                'total_net': sum((r['net'] for r in lines), Decimal('0')),
            })
            flat += lines
        section['rows'] = flat
        section['total_due'] = sum((r['due'] for r in section['rows']), Decimal('0'))
        section['total_net'] = sum((r['net'] for r in section['rows']), Decimal('0'))

    adjustments = []
    slips = DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end).select_related('worker')
    for slip in slips:
        effect = slip.other_allowances - slip.other_deductions - slip.advances
        if effect or slip.other_allowances or slip.other_deductions or slip.advances:
            adjustments.append({
                'worker': slip.worker, 'allowances': slip.other_allowances, 'deductions': slip.other_deductions,
                'advances': slip.advances, 'effect': effect,
            })
    adjustments.sort(key=lambda a: a['worker'].full_name)

    grand_total = sum((sec['total_net'] for sec in ordered), Decimal('0')) + sum((a['effect'] for a in adjustments), Decimal('0'))
    return {'period_start': period_start, 'period_end': period_end, 'sections': ordered,
            'adjustments': adjustments, 'grand_total': grand_total}
