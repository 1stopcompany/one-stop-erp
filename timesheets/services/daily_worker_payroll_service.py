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
    by_project = defaultdict(lambda: {'regular_hours': Decimal('0'), 'overtime_hours': Decimal('0')})

    for entry in entries:
        overtime_hours = entry.overtime_hours or Decimal('0')
        regular_hours = max(Decimal('0'), (entry.total_hours or Decimal('0')) - overtime_hours)
        bucket = by_project[entry.report.project]
        bucket['regular_hours'] += regular_hours
        bucket['overtime_hours'] += overtime_hours

    breakdown = []
    total_pay = Decimal('0')
    for project, hours in by_project.items():
        days = hours['regular_hours'] / Decimal(8)
        base_pay = _round2(days * worker.daily_rate)
        overtime_pay = _round2(hours['overtime_hours'] * hourly_rate * Decimal('1.5'))
        pay = base_pay + overtime_pay
        breakdown.append({
            'project': project,
            'days': _round2(days),
            'overtime_hours': _round2(hours['overtime_hours']),
            'base_pay': base_pay,
            'overtime_pay': overtime_pay,
            'pay': pay,
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
        advances=_round2(advances), generated_by=generated_by,
    )
    payslip, _ = DailyWorkerPayslip.objects.update_or_create(
        worker=worker, period_start=period_start, period_end=period_end, defaults=fields,
    )
    return payslip
