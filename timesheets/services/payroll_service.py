"""
Two ways to compute a Payslip, matching how the company actually runs
payroll (verified against a real August-2026 salary sheet for permanent
staff):

  compute_payslip_salaried(employee, period_start, period_end, ...)
    For permanent staff. base_pay is their fixed monthly salary, prorated
    only for a genuine partial period (hire/termination date cutting into
    the period) -- ordinary attendance gaps are an HR review matter, not
    an automatic deduction. Friday and public holidays are paid days
    already included in the fixed salary (no separate premium). Overtime
    hours, other allowances, other deductions ("مقتطعات"), advances
    ("سلف") and tax are all entered by HR, not derived automatically --
    this function just applies the pay policy to numbers you give it.

  compute_payslip_hourly(employee, period_start, period_end, ...)
    For workers paid strictly by hours actually present (e.g. daily-wage
    workers) -- everything is derived automatically from real GPS
    check-in/out records (CheckInLocation), split into regular/overtime/
    weekend/holiday hours.

Shared policy, confirmed with the client:
  - Work week is Saturday-Thursday, Friday off (WEEKEND_WEEKDAYS = {4}).
  - A worked day is 8 real work hours plus a 1-hour unpaid break
    (SalaryStructure.break_hours) -- only relevant to the hourly path,
    since a salaried day's hours aren't tracked this way.
  - Overtime is 1.5x; a day worked on Friday is 1.5x (hourly path only);
    a day worked on a Holiday date is 2x, taking priority over weekend.
  - Income tax is tracked for information only and never reduces
    net_pay -- confirmed against the real sheet (net pay = gross minus
    other_deductions and advances; the tax figure is added into a
    separate "gross including tax" total and then backed back out,
    leaving take-home pay unaffected by it). Tax has its own calculation,
    handled separately, per the client.

CheckInLocation.timestamp is stored UTC (USE_TZ=True). Filtering by
`timestamp__date` would compile to `DATE(CONVERT_TZ(...))` on MySQL and
silently match nothing if the server's named-timezone tables were never
loaded (see api_views.local_day_range_utc's docstring for the same
footgun) -- so the hourly path filters by a plain UTC datetime range
instead, wide enough to cover every local day in the period, and converts
to local time in Python before grouping into calendar days.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from timesheets.models import CheckInLocation, Holiday, Payslip, SalaryStructure

WEEKEND_WEEKDAYS = {4}  # Monday=0 ... Friday=4 ... Sunday=6
PRORATION_REFERENCE_DAYS = 30  # fixed 30-day-month convention, matches the real sheet

DEFAULT_MONTHLY_HOURS = 240  # 30-day month x 8 hours/day -- confirmed against a real payroll sheet
DEFAULT_DAILY_HOURS = 8
DEFAULT_BREAK_HOURS = Decimal('1')
DEFAULT_OVERTIME_MULTIPLIER = Decimal('1.5')
DEFAULT_WEEKEND_MULTIPLIER = Decimal('1.5')
DEFAULT_HOLIDAY_MULTIPLIER = Decimal('2.0')


def _round2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _effective_structure(employee):
    """The employee's own salary structure, else the company default, else built-in fallbacks."""
    return employee.salary_structure or SalaryStructure.objects.filter(is_default=True, is_active=True).first()


def _save_payslip(employee, period_start, period_end, **fields):
    # A posted (ترحيل) payslip is finalized -- recomputing the run for that
    # month must not silently overwrite it. Return it untouched instead.
    # An excluded one was taken out of the run on purpose: leave it alone too.
    existing = Payslip.objects.filter(employee=employee, period_start=period_start, period_end=period_end).first()
    if existing and existing.status in ('posted', 'excluded'):
        return existing

    # gross_pay/net_pay are recomputed by Payslip.save() itself -- not set here.
    for key in ('manual_base_pay', 'manual_unpaid_leave_deduction'):
        if fields.get(key) is not None:
            fields[key] = _round2(fields[key])
    for key in ('hourly_rate', 'regular_hours', 'weekend_hours', 'holiday_hours', 'overtime_hours',
                'base_pay', 'overtime_pay', 'weekend_pay', 'holiday_pay',
                'other_allowances', 'other_deductions', 'advances', 'tax',
                'unpaid_leave_days', 'unpaid_leave_deduction'):
        fields[key] = _round2(fields.get(key, 0))
    payslip, _ = Payslip.objects.update_or_create(
        employee=employee, period_start=period_start, period_end=period_end, defaults=fields,
    )
    return payslip


KEEP = object()   # "carry over what the existing payslip already has" for the manual overrides below


def auto_base_pay(employee, period_start, period_end):
    """The salary-based base pay for the period: the fixed salary, prorated only for a genuine partial month."""
    employed_from = max(period_start, employee.hire_date)
    employed_until = min(period_end, employee.termination_date) if employee.termination_date else period_end
    if employed_from > employed_until:
        proration = Decimal('0')
    elif employed_from <= period_start and employed_until >= period_end:
        proration = Decimal('1')  # employed for the whole period -- full salary, no calendar-length distortion
    else:
        days_employed = (employed_until - employed_from).days + 1
        proration = min(Decimal(days_employed) / Decimal(PRORATION_REFERENCE_DAYS), Decimal('1'))
    return employee.salary * proration


def auto_unpaid_leave(employee, period_start, period_end):
    """(days, deduction) for leave taken beyond the annual balance, from the Daily Time Record."""
    from timesheets.services.attendance_service import count_unpaid_leave_days
    days = Decimal(count_unpaid_leave_days(employee, period_start, period_end))
    return days, (employee.salary / Decimal(PRORATION_REFERENCE_DAYS)) * days


def compute_payslip_salaried(
    employee, period_start, period_end, *,
    overtime_hours=Decimal('0'), other_allowances=Decimal('0'), other_deductions=Decimal('0'),
    advances=Decimal('0'), tax=Decimal('0'), generated_by=None,
    manual_base_pay=KEEP, manual_unpaid_leave_deduction=KEEP, note=KEEP,
) -> Payslip:
    """
    Fixed-salary payslip for a permanent employee. overtime_hours,
    other_allowances, other_deductions, advances and tax are figures HR
    supplies (e.g. from timesheet review or a signed leave/loan form) --
    this only applies the pay policy to them, it doesn't invent them.
    """
    structure = _effective_structure(employee)
    monthly_hours = structure.monthly_working_hours if structure else DEFAULT_MONTHLY_HOURS
    overtime_multiplier = structure.overtime_multiplier if structure else DEFAULT_OVERTIME_MULTIPLIER
    hourly_rate = employee.salary / Decimal(monthly_hours)

    existing = Payslip.objects.filter(employee=employee, period_start=period_start, period_end=period_end).first()
    if manual_base_pay is KEEP:
        manual_base_pay = existing.manual_base_pay if existing else None
    if manual_unpaid_leave_deduction is KEEP:
        manual_unpaid_leave_deduction = existing.manual_unpaid_leave_deduction if existing else None
    if note is KEEP:
        note = existing.note if existing else ''

    base_pay = auto_base_pay(employee, period_start, period_end) if manual_base_pay is None else Decimal(manual_base_pay)
    overtime_hours = Decimal(overtime_hours)
    overtime_pay = hourly_rate * overtime_multiplier * overtime_hours

    # Days marked 'unpaid_leave' on the employee's Daily Time Record for
    # this period -- i.e. leave taken after their annual_leave_days
    # balance was already used up (see attendance_service) -- are docked
    # automatically, at the same 30-day-month daily rate used everywhere
    # else in this module. This is the one deduction that isn't manually
    # typed in: it comes straight from the DTR the client asked to be
    # "the real basis payroll is prepared from."
    unpaid_leave_days, unpaid_leave_deduction = auto_unpaid_leave(employee, period_start, period_end)
    if manual_unpaid_leave_deduction is not None:
        unpaid_leave_deduction = Decimal(manual_unpaid_leave_deduction)

    return _save_payslip(
        employee, period_start, period_end,
        pay_basis='salaried', salary_structure=structure, hourly_rate=hourly_rate,
        regular_hours=Decimal('0'), weekend_hours=Decimal('0'), holiday_hours=Decimal('0'),
        weekend_pay=Decimal('0'), holiday_pay=Decimal('0'),
        overtime_hours=overtime_hours, overtime_pay=overtime_pay, base_pay=base_pay,
        other_allowances=Decimal(other_allowances), other_deductions=Decimal(other_deductions),
        advances=Decimal(advances), tax=Decimal(tax),
        unpaid_leave_days=unpaid_leave_days, unpaid_leave_deduction=unpaid_leave_deduction,
        manual_base_pay=manual_base_pay, manual_unpaid_leave_deduction=manual_unpaid_leave_deduction, note=note,
        generated_by=generated_by,
    )


def _local_day_range_utc(period_start, period_end):
    """(start, end) aware-UTC datetimes spanning local midnight-to-midnight for the whole period."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(period_start, time.min), tz)
    end = timezone.make_aware(datetime.combine(period_end + timedelta(days=1), time.min), tz)
    return start, end


def _daily_raw_hours(employee, period_start, period_end):
    """{date: hours_worked} raw span (before break deduction) for every day with a paired in/out."""
    range_start, range_end = _local_day_range_utc(period_start, period_end)
    records = list(
        CheckInLocation.objects.filter(
            employee=employee, timestamp__gte=range_start, timestamp__lt=range_end,
        ).order_by('timestamp')
    )

    by_day = defaultdict(Decimal)
    last_check_in = None
    for record in records:
        local_ts = timezone.localtime(record.timestamp)
        if record.check_type == 'in':
            last_check_in = local_ts
        elif record.check_type == 'out' and last_check_in is not None:
            duration_hours = Decimal((local_ts - last_check_in).total_seconds()) / Decimal(3600)
            if duration_hours > 0:
                by_day[last_check_in.date()] += duration_hours
            last_check_in = None

    return by_day


def compute_payslip_hourly(employee, period_start, period_end, generated_by=None) -> Payslip:
    """Fully automatic payslip from real GPS check-in/out records -- for workers paid by hours present."""
    structure = _effective_structure(employee)
    monthly_hours = structure.monthly_working_hours if structure else DEFAULT_MONTHLY_HOURS
    daily_hours_cap = Decimal(structure.daily_working_hours if structure else DEFAULT_DAILY_HOURS)
    break_hours = structure.break_hours if structure else DEFAULT_BREAK_HOURS
    overtime_multiplier = structure.overtime_multiplier if structure else DEFAULT_OVERTIME_MULTIPLIER
    weekend_multiplier = structure.weekend_multiplier if structure else DEFAULT_WEEKEND_MULTIPLIER
    holiday_multiplier = structure.holiday_multiplier if structure else DEFAULT_HOLIDAY_MULTIPLIER

    hourly_rate = employee.salary / Decimal(monthly_hours)

    holiday_dates = set(
        Holiday.objects.filter(date__gte=period_start, date__lte=period_end).values_list('date', flat=True)
    )

    regular_hours = Decimal('0')
    overtime_hours = Decimal('0')
    weekend_hours = Decimal('0')
    holiday_hours = Decimal('0')

    for day, raw_hours in _daily_raw_hours(employee, period_start, period_end).items():
        worked_hours = max(Decimal('0'), raw_hours - break_hours)

        if day in holiday_dates:
            holiday_hours += worked_hours
        elif day.weekday() in WEEKEND_WEEKDAYS:
            weekend_hours += worked_hours
        else:
            regular_hours += min(worked_hours, daily_hours_cap)
            overtime_hours += max(Decimal('0'), worked_hours - daily_hours_cap)

    base_pay = hourly_rate * regular_hours
    overtime_pay = hourly_rate * overtime_multiplier * overtime_hours
    weekend_pay = hourly_rate * weekend_multiplier * weekend_hours
    holiday_pay = hourly_rate * holiday_multiplier * holiday_hours

    return _save_payslip(
        employee, period_start, period_end,
        pay_basis='hourly', salary_structure=structure, hourly_rate=hourly_rate,
        regular_hours=regular_hours, weekend_hours=weekend_hours, holiday_hours=holiday_hours,
        weekend_pay=weekend_pay, holiday_pay=holiday_pay,
        overtime_hours=overtime_hours, overtime_pay=overtime_pay, base_pay=base_pay,
        other_allowances=Decimal('0'), other_deductions=Decimal('0'),
        advances=Decimal('0'), tax=Decimal('0'), generated_by=generated_by,
    )
