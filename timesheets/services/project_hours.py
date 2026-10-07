"""
How a salaried employee's hours (and overtime) are spread over projects, and what that costs each project.

Where the hours come from, per employee per day:
  1. the day's rows in `EmployeeProjectHours` -- typed by HR on the Daily Time Record ("Split"), when the daily reports are
     missing or not accurate. A day with such rows uses ONLY them;
  2. otherwise the daily reports' worker attendance (`DailyReportWorkerAttendance` linked to the employee): the report's
     project, `total_hours - overtime_hours` regular hours and `overtime_hours` overtime. Rejected reports do not count.

The salary does not change. What a project is charged is only its share: hours x hourly rate (monthly salary / the salary
structure's monthly working hours) and overtime hours x hourly rate x the structure's overtime multiplier -- the same rate and
multiplier the payslip itself uses.
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


def month_breakdown(employee, start, end):
    """
    The month's hours per project with what each costs:
        [{'project', 'regular_hours', 'overtime_hours', 'regular_cost', 'overtime_cost', 'cost', 'days'}], plus the totals.
    Returns (rows, totals) -- rows empty when the employee has no hours recorded in the period.
    """
    rate, multiplier = pay_rates(employee)
    per_project = OrderedDict()
    for day, info in day_allocations(employee, start, end).items():
        for row in info['rows']:
            item = per_project.setdefault(row['project'].pk, {
                'project': row['project'], 'regular_hours': ZERO, 'overtime_hours': ZERO, 'days': 0,
            })
            item['regular_hours'] += row['regular']
            item['overtime_hours'] += row['overtime']
            item['days'] += 1
    rows = []
    for item in sorted(per_project.values(), key=lambda i: i['project'].name):
        item['regular_cost'] = (item['regular_hours'] * rate).quantize(CENT)
        item['overtime_cost'] = (item['overtime_hours'] * rate * multiplier).quantize(CENT)
        item['cost'] = item['regular_cost'] + item['overtime_cost']
        rows.append(item)
    totals = {key: sum((r[key] for r in rows), ZERO) for key in ('regular_hours', 'overtime_hours', 'regular_cost', 'overtime_cost', 'cost')}
    return rows, totals


def project_labor_cost(project, as_of=None):
    """
    What the project has been charged for employees' hours so far (all time, up to `as_of` if given):
        {'cost', 'regular_hours', 'overtime_hours', 'employees': [{'employee', 'hours', 'overtime_hours', 'cost'}]}
    """
    from reports.daily_detail_models import DailyReportWorkerAttendance
    from timesheets.models import Employee, EmployeeProjectHours

    manual_filter = Q(project=project)
    auto_filter = Q(report__project=project, employee__isnull=False)
    if as_of:
        manual_filter &= Q(date__lte=as_of)
        auto_filter &= Q(report__report_date__lte=as_of)
    # the days an employee has typed rows for -- on those days the daily reports of ANY project are replaced by them
    manual_days = {}
    for emp_id, day in EmployeeProjectHours.objects.values_list('employee_id', 'date'):
        manual_days.setdefault(emp_id, set()).add(day)

    per_employee = {}
    for row in EmployeeProjectHours.objects.filter(manual_filter):
        item = per_employee.setdefault(row.employee_id, [ZERO, ZERO])
        item[0] += row.regular_hours
        item[1] += row.overtime_hours
    for row in DailyReportWorkerAttendance.objects.filter(auto_filter).exclude(report__status='rejected').select_related('report'):
        if row.report.report_date in manual_days.get(row.employee_id, ()):
            continue
        item = per_employee.setdefault(row.employee_id, [ZERO, ZERO])
        overtime = row.overtime_hours or ZERO
        item[0] += max(row.total_hours - overtime, ZERO)
        item[1] += overtime

    employees, total_cost, total_regular, total_overtime = [], ZERO, ZERO, ZERO
    for employee in Employee.objects.filter(pk__in=per_employee).order_by('first_name', 'last_name'):
        regular, overtime = per_employee[employee.pk]
        rate, multiplier = pay_rates(employee)
        cost = (regular * rate + overtime * rate * multiplier).quantize(CENT)
        employees.append({'employee': employee, 'hours': regular, 'overtime_hours': overtime, 'cost': cost})
        total_cost += cost
        total_regular += regular
        total_overtime += overtime
    return {'cost': total_cost, 'regular_hours': total_regular, 'overtime_hours': total_overtime, 'employees': employees}
