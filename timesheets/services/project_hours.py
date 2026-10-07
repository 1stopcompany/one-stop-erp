"""
How a salaried employee's hours (and overtime) are spread over projects, and what that costs each project.

Where the hours come from, per employee per day:
  1. the day's rows in `EmployeeProjectHours` -- typed by HR on the Daily Time Record ("Split"), when the daily reports are
     missing or not accurate. A day with such rows uses ONLY them;
  2. otherwise the daily reports' worker attendance (`DailyReportWorkerAttendance` linked to the employee): the report's
     project, `total_hours - overtime_hours` regular hours and `overtime_hours` overtime. Rejected reports do not count.

The salary does not change, and neither does a project's share of it when the month is incomplete. What is spread over the projects
is the month's regular pay (the payslip's base pay less an unpaid-leave deduction; salary / 240 hours x the paid hours): every project
gets its share in proportion to the regular hours recorded on it. So Fridays (paid rest days), paid holidays / leave and any shortfall in
the day's hours are counted as present and carried by the projects -- a shortfall never lowers the salary (it is settled through the
annual-leave balance: every 8 hours of accumulated undertime costs one leave day, see attendance_service). Overtime hours are charged on
top: overtime hours x hourly rate x the structure's multiplier.
"""
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Q

ZERO = Decimal('0')
CENT = Decimal('0.01')


def pay_rates(employee):
    """(hourly rate, overtime multiplier) exactly as the payslip computes them."""
    from .payroll_service import DEFAULT_MONTHLY_HOURS, DEFAULT_OVERTIME_MULTIPLIER, _effective_structure
    structure = _effective_structure(employee)
    monthly_hours = structure.monthly_working_hours if structure else DEFAULT_MONTHLY_HOURS
    multiplier = structure.overtime_multiplier if structure else DEFAULT_OVERTIME_MULTIPLIER
    return (Decimal(employee.salary) / Decimal(monthly_hours)), Decimal(multiplier)


def _auto_rows(employee, start, end):
    """{date: {project_id: [project, regular, overtime]}} from the daily reports' worker attendance."""
    from reports.daily_detail_models import DailyReportWorkerAttendance
    rows = (
        DailyReportWorkerAttendance.objects
        .filter(employee=employee, report__report_date__gte=start, report__report_date__lte=end)
        .exclude(report__status='rejected')
        .select_related('report__project')
    )
    days = {}
    for row in rows:
        project = row.report.project
        bucket = days.setdefault(row.report.report_date, {}).setdefault(project.pk, [project, ZERO, ZERO])
        overtime = row.overtime_hours or ZERO
        bucket[1] += max(row.total_hours - overtime, ZERO)
        bucket[2] += overtime
    return days


def _manual_rows(employee, start, end):
    from timesheets.models import EmployeeProjectHours
    days = {}
    for row in EmployeeProjectHours.objects.filter(employee=employee, date__gte=start, date__lte=end).select_related('project'):
        days.setdefault(row.date, {})[row.project_id] = [row.project, row.regular_hours, row.overtime_hours]
    return days


def day_allocations(employee, start, end):
    """
    {date: {'source': 'manual' | 'daily_report', 'rows': [{'project', 'regular', 'overtime'}]}} for every day that has hours.
    """
    manual = _manual_rows(employee, start, end)
    auto = _auto_rows(employee, start, end)
    result = {}
    for day in sorted(set(manual) | set(auto)):
        source, rows = ('manual', manual[day]) if day in manual else ('daily_report', auto[day])
        result[day] = {
            'source': source,
            'rows': [{'project': p, 'regular': reg, 'overtime': ot} for p, reg, ot in rows.values()],
        }
    return result


def month_pay(employee, start, end):
    """(regular pay to spread, hourly rate, overtime multiplier) for the month: the payslip's figures, else the automatic ones."""
    from timesheets.models import Payslip
    from .payroll_service import auto_base_pay, auto_unpaid_leave

    rate, multiplier = pay_rates(employee)
    payslip = Payslip.objects.filter(employee=employee, period_start=start, period_end=end).exclude(status='excluded').first()
    if payslip:
        base = Decimal(payslip.base_pay) - Decimal(payslip.unpaid_leave_deduction or 0)
        if payslip.hourly_rate:
            rate = Decimal(payslip.hourly_rate)
        if payslip.salary_structure_id:
            multiplier = Decimal(payslip.salary_structure.overtime_multiplier)
    else:
        base = Decimal(auto_base_pay(employee, start, end)) - Decimal(auto_unpaid_leave(employee, start, end)[1])
    return max(base, ZERO), rate, multiplier


def _rest_and_shortfall(employee, start, end, extra_hours, worked_days=()):
    """Splits the paid hours that no project recorded: Fridays, paid holidays / leave days, and what is left is the shortfall."""
    from datetime import timedelta
    from timesheets.models import DailyAttendanceRecord

    first = max(start, employee.hire_date) if employee.hire_date else start
    last = min(end, employee.termination_date) if employee.termination_date else end
    if worked_days:   # hours recorded outside the hire / termination dates still belong to the month's span
        first, last = min(first, min(worked_days)), max(last, max(worked_days))
    fridays, day = 0, first
    while day <= last:
        fridays += day.weekday() == 4
        day += timedelta(days=1)
    leave_days = (
        DailyAttendanceRecord.objects.filter(employee=employee, date__gte=start, date__lte=end, status__in=('holiday', 'on_leave'))
        .exclude(date__week_day=6).count()   # Django: Friday = 6; a Friday is already counted above
    )
    standard = Decimal('8')
    friday_hours = min(Decimal(fridays) * standard, extra_hours)
    leave_hours = min(Decimal(leave_days) * standard, extra_hours - friday_hours)
    return {'fridays': fridays, 'friday_hours': friday_hours, 'leave_days': leave_days, 'leave_hours': leave_hours,
            'shortfall_hours': extra_hours - friday_hours - leave_hours}


def month_breakdown(employee, start, end):
    """
    The month's hours per project with what each project is charged:
        [{'project', 'regular_hours', 'extra_hours', 'overtime_hours', 'regular_cost', 'overtime_cost', 'cost', 'days'}], totals
    `regular_hours` are the hours recorded on the project; `extra_hours` its share of the paid hours nobody recorded (Fridays, paid
    holidays / leave, shortfall). The regular costs add up to the month's regular pay exactly. `totals` also carries `recorded_hours`,
    `paid_hours` and the split of the unrecorded hours (`fridays`, `friday_hours`, `leave_days`, `leave_hours`, `shortfall_hours`).
    Returns ([], totals) when the employee has no hours recorded in the period.
    """
    base, rate, multiplier = month_pay(employee, start, end)
    per_project = OrderedDict()
    allocations = day_allocations(employee, start, end)
    for day, info in allocations.items():
        for row in info['rows']:
            item = per_project.setdefault(row['project'].pk, {
                'project': row['project'], 'regular_hours': ZERO, 'overtime_hours': ZERO, 'days': 0,
            })
            item['regular_hours'] += row['regular']
            item['overtime_hours'] += row['overtime']
            item['days'] += 1
    rows = sorted(per_project.values(), key=lambda i: i['project'].name)
    recorded = sum((r['regular_hours'] for r in rows), ZERO)
    paid_hours = (base / rate) if rate else ZERO
    extra = max(paid_hours - recorded, ZERO) if recorded else ZERO
    detail = _rest_and_shortfall(employee, start, end, extra, list(allocations)) if rows else {
        'fridays': 0, 'friday_hours': ZERO, 'leave_days': 0, 'leave_hours': ZERO, 'shortfall_hours': ZERO}

    spread = ZERO
    for item in rows:
        share = (item['regular_hours'] / recorded) if recorded else ZERO
        item['extra_hours'] = (extra * share).quantize(CENT)
        item['regular_cost'] = (base * share).quantize(CENT) if recorded else ZERO
        spread += item['regular_cost']
        item['overtime_cost'] = (item['overtime_hours'] * rate * multiplier).quantize(CENT)
    if recorded and rows:
        # the cents lost to rounding go to the project with the largest share, so the pieces add up to the pay exactly
        biggest = max(rows, key=lambda i: i['regular_hours'])
        biggest['regular_cost'] += (base.quantize(CENT) - spread)
    for item in rows:
        item['cost'] = item['regular_cost'] + item['overtime_cost']
    totals = {key: sum((r[key] for r in rows), ZERO) for key in
              ('regular_hours', 'extra_hours', 'overtime_hours', 'regular_cost', 'overtime_cost', 'cost')}
    totals.update(detail)
    totals.update({'recorded_hours': recorded, 'paid_hours': paid_hours})
    return rows, totals


def project_labor_cost(project, as_of=None):
    """
    What the project has been charged for employees' hours so far, month by month (each month's share as in month_breakdown):
        {'cost', 'regular_hours', 'overtime_hours', 'employees': [{'employee', 'hours', 'overtime_hours', 'cost'}]}
    """
    import calendar
    from datetime import date

    from reports.daily_detail_models import DailyReportWorkerAttendance
    from timesheets.models import Employee, EmployeeProjectHours

    pairs = set()
    manual = EmployeeProjectHours.objects.filter(project=project)
    auto = DailyReportWorkerAttendance.objects.filter(report__project=project, employee__isnull=False).exclude(report__status='rejected')
    if as_of:
        manual = manual.filter(date__lte=as_of)
        auto = auto.filter(report__report_date__lte=as_of)
    for emp_id, day in manual.values_list('employee_id', 'date'):
        pairs.add((emp_id, day.year, day.month))
    for emp_id, day in auto.values_list('employee_id', 'report__report_date'):
        pairs.add((emp_id, day.year, day.month))

    employees_by_id = {e.pk: e for e in Employee.objects.filter(pk__in={p[0] for p in pairs})}
    per_employee = {}
    for emp_id, year, month in sorted(pairs):
        employee = employees_by_id[emp_id]
        start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        rows, _ = month_breakdown(employee, start, end)
        for row in rows:
            if row['project'].pk != project.pk:
                continue
            item = per_employee.setdefault(emp_id, [ZERO, ZERO, ZERO])
            item[0] += row['regular_hours']
            item[1] += row['overtime_hours']
            item[2] += row['cost']
    employees, total_cost, total_regular, total_overtime = [], ZERO, ZERO, ZERO
    for employee in sorted((employees_by_id[i] for i in per_employee), key=lambda e: (e.first_name, e.last_name)):
        regular, overtime, cost = per_employee[employee.pk]
        employees.append({'employee': employee, 'hours': regular, 'overtime_hours': overtime, 'cost': cost})
        total_cost += cost
        total_regular += regular
        total_overtime += overtime
    return {'cost': total_cost, 'regular_hours': total_regular, 'overtime_hours': total_overtime, 'employees': employees}
