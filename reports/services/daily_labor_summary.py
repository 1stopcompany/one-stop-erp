"""
Daily labor productivity-vs-cost summary for the Daily Report's Worker Attendance section.

Groups today's worker-attendance rows by their crew (not by activity directly) -- a crew is the
real unit of work organization on site, and grouping by activity alone would lose a crew's own
identity whenever that crew wasn't linked to one (or would silently merge two different crews
that happen to share an activity). Each crew's row still carries its own linked activity (if any)
so its quantity_today/unit can be paired against the crew's cost for a cost-per-unit figure.
Workers not part of any crew (solo HR staff marking their own presence, day laborers entered
without a crew) fall into their own "No Crew" bucket, last, rather than being dropped.

Cost here is an on-the-spot estimate for this page, not a payslip: a day laborer's cost is
daily_rate/8 (timesheets.DailyWorker.hourly_rate) times hours worked; an HR employee's is their
monthly salary divided by their salary structure's monthly_working_hours (the same formula
timesheets.services.payroll_service uses), times hours worked -- it does not apply the overtime/
weekend/holiday multipliers a real payslip would, since this is meant to give a same-day cost
signal, not to be reconciled against payroll.
"""

from decimal import Decimal

from timesheets.services.payroll_service import DEFAULT_MONTHLY_HOURS


def _attendance_cost(attendance) -> Decimal:
    hours = attendance.total_hours or Decimal('0')
    if attendance.daily_worker_id:
        return attendance.daily_worker.hourly_rate * hours
    if attendance.employee_id:
        structure = attendance.employee.salary_structure
        monthly_hours = structure.monthly_working_hours if structure else DEFAULT_MONTHLY_HOURS
        return (attendance.employee.salary / Decimal(monthly_hours)) * hours
    return Decimal('0')


def daily_labor_productivity_summary(report):
    """
    Returns a list of rows, each: {crew, activity, hours, cost, quantity_today, unit,
    cost_per_unit}, sorted with the "No Crew" bucket (crew=None) last. cost_per_unit is None when
    the crew has no linked activity, or that activity has no quantity_today to divide by.
    """
    attendance_qs = report.worker_attendance.select_related(
        'daily_worker', 'employee__salary_structure', 'crew__activity',
    )

    buckets = {}
    for attendance in attendance_qs:
        crew = attendance.crew
        key = crew.id if crew else None
        bucket = buckets.setdefault(key, {'crew': crew, 'hours': Decimal('0'), 'cost': Decimal('0')})
        bucket['hours'] += attendance.total_hours or Decimal('0')
        bucket['cost'] += _attendance_cost(attendance)

    rows = []
    for key, bucket in buckets.items():
        crew = bucket['crew']
        activity = crew.activity if (crew and crew.activity_id) else None
        quantity_today = activity.quantity_today if activity else None
        unit = activity.unit if activity else ''
        cost_per_unit = (bucket['cost'] / quantity_today) if quantity_today else None
        rows.append({
            'crew': crew,
            'activity': activity,
            'hours': bucket['hours'],
            'cost': bucket['cost'],
            'quantity_today': quantity_today,
            'unit': unit,
            'cost_per_unit': cost_per_unit,
        })

    rows.sort(key=lambda r: (r['crew'] is None, r['crew'].name if r['crew'] else ''))
    return rows
