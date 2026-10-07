"""
Daily Time Record (DTR): one row per employee per calendar day, generated
from real data and then reviewable/editable by HR -- this is the record
timesheets.services.payroll_service actually reads to decide whether a
leave day was still within the employee's paid annual_leave_days balance
or has become an unpaid deduction on their payslip.

generate_daily_attendance(employee, period_start, period_end) classifies
each day, in priority order:
  1. Covered by an APPROVED LeaveRequest -> 'on_leave' (still within the
     employee's balance for the year) or 'unpaid_leave' (the balance was
     already used up by the time this day comes around, walking the
     employee's approved requests for the year in date order).
  2. A Holiday date -> 'holiday'.
  3. Friday (the weekly rest day, confirmed with the client) -> 'rest_day'.
  4. A real GPS check-in exists that day -> 'present' (clock_in/out
     pulled from the earliest 'in' and latest 'out' CheckInLocation rows).
  5. Otherwise -> 'absent' (an HR review matter, same principle as
     payroll_service.compute_payslip_salaried -- never auto-deducted;
     HR reclassifies it to 'unpaid_leave' by hand here if that's the
     call, and only then does it show up as a payroll deduction).

Existing rows are never overwritten on a re-run (get_or_create, not
update_or_create) -- once HR has corrected a day, regenerating the month
must not clobber that correction.
"""

from collections import defaultdict
from datetime import date, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from timesheets.models import CheckInLocation, DailyAttendanceRecord, Holiday, LeaveRequest

WEEKEND_WEEKDAYS = {4}  # Friday, matching payroll_service

# Annual leave allocation is tenure-based, confirmed with the client:
# under 5 years of service, 14 days/year; 5 years or more, 21 days/year.
# This supersedes Employee.annual_leave_days as the actual source of
# truth for balance calculations -- that field predates this rule and is
# no longer read here (still shown on the Add/Edit Employee form, but
# effectively vestigial; flag with the client whether to remove it).
LEAVE_TENURE_THRESHOLD_YEARS = 5
LEAVE_DAYS_UNDER_THRESHOLD = 14
LEAVE_DAYS_AT_THRESHOLD = 21

# Confirmed with the client: every full 8 hours of accumulated shortfall
# below a full workday (DailyAttendanceRecord.undertime_minutes, on
# 'present' days) deducts one day from the annual leave balance.
UNDERTIME_MINUTES_PER_DEDUCTED_DAY = 8 * 60


DEFAULT_CLOCK_IN = time(8, 0)
DEFAULT_CLOCK_OUT = time(17, 0)   # with the one-hour lunch break that is a standard 8-hour day
STANDARD_DAY_HOURS = Decimal('8')
DEFAULT_BREAK_HOURS = Decimal('1')


def day_overtime(clock_in, clock_out, break_hours=DEFAULT_BREAK_HOURS):
    """Overtime of a day: the hours worked (clock out - clock in - break) above the standard 8; 0 when a time is missing."""
    if not (clock_in and clock_out):
        return Decimal('0')
    minutes = (clock_out.hour * 60 + clock_out.minute) - (clock_in.hour * 60 + clock_in.minute)
    if minutes <= 0:
        return Decimal('0')
    worked = Decimal(minutes) / Decimal(60) - Decimal(break_hours)
    return max(worked - STANDARD_DAY_HOURS, Decimal('0')).quantize(Decimal('0.01'))


def day_undertime_minutes(clock_in, clock_out, break_hours=DEFAULT_BREAK_HOURS):
    """Minutes the day falls short of the standard 8 hours (clock out - clock in - break); 0 when a time is missing."""
    if not (clock_in and clock_out):
        return 0
    minutes = (clock_out.hour * 60 + clock_out.minute) - (clock_in.hour * 60 + clock_in.minute)
    if minutes <= 0:
        return 0
    worked = Decimal(minutes) - Decimal(break_hours) * 60
    return int(max(Decimal(STANDARD_DAY_HOURS) * 60 - worked, Decimal('0')))


def recalculate_undertime(employee, period_start, period_end):
    """The shortfall of every present day of the month becomes its Undertime minutes (what the annual-leave balance is charged for)."""
    changed = 0
    for record in generate_daily_attendance(employee, period_start, period_end):
        if record.status != 'present' or not (record.clock_in and record.clock_out):
            continue
        minutes = day_undertime_minutes(record.clock_in, record.clock_out, record.break_hours)
        if record.undertime_minutes != minutes:
            record.undertime_minutes = minutes
            record.save()
            changed += 1
    return changed


def fill_default_hours(employee, period_start, period_end, today=None):
    """
    The standard day (08:00-17:00, one hour of lunch) for every day HR left empty: a working day (not Friday, holiday or leave -- those have their own
    status) with no GPS check-in at all, that is not in the future, becomes 'present' with the default times. Nothing that already has
    a time, a status other than 'absent', or an HR note is touched, so real check-ins and manual corrections are never overwritten.
    Returns the number of days filled.
    """
    today = today or timezone.localdate()
    records = generate_daily_attendance(employee, period_start, period_end)
    filled = 0
    for record in records:
        if record.date > today or record.status != 'absent' or record.clock_in or record.clock_out or record.notes:
            continue
        record.status = 'present'
        record.clock_in, record.clock_out = DEFAULT_CLOCK_IN, DEFAULT_CLOCK_OUT
        record.notes = 'Default hours'
        record.save()
        filled += 1
    return filled


def _annual_leave_allocation(employee, year):
    """Tenure-based entitlement for `year`, measured as of that year's last day (see module-level constants)."""
    years_of_service = (date(year, 12, 31) - employee.hire_date).days // 365
    return LEAVE_DAYS_AT_THRESHOLD if years_of_service >= LEAVE_TENURE_THRESHOLD_YEARS else LEAVE_DAYS_UNDER_THRESHOLD


def _local_day_range_utc(period_start, period_end):
    from datetime import datetime, time
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(period_start, time.min), tz)
    end = timezone.make_aware(datetime.combine(period_end + timedelta(days=1), time.min), tz)
    return start, end


def _checkins_by_day(employee, period_start, period_end):
    """{date: (first_clock_in_time, last_clock_out_time)} from real GPS check-ins."""
    range_start, range_end = _local_day_range_utc(period_start, period_end)
    records = CheckInLocation.objects.filter(
        employee=employee, timestamp__gte=range_start, timestamp__lt=range_end,
    ).order_by('timestamp')

    ins = {}
    outs = {}
    for record in records:
        local_ts = timezone.localtime(record.timestamp)
        day = local_ts.date()
        if record.check_type == 'in' and day not in ins:
            ins[day] = local_ts.time()
        elif record.check_type == 'out':
            outs[day] = local_ts.time()

    return {day: (ins.get(day), outs.get(day)) for day in set(ins) | set(outs)}


def _days_used_in_year(employee, year):
    """Approved leave days actually falling within `year` (clipped at the year's edges), Friday excluded."""
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    total = 0
    requests = LeaveRequest.objects.filter(
        employee=employee, status='approved', start_date__lte=year_end, end_date__gte=year_start,
    )
    for req in requests:
        day = max(req.start_date, year_start)
        last = min(req.end_date, year_end)
        while day <= last:
            if day.weekday() not in WEEKEND_WEEKDAYS:
                total += 1
            day += timedelta(days=1)
    return total


def _carried_over_days(employee, year):
    """
    Whatever balance was left unused at the end of the previous year
    rolls forward onto this year -- confirmed with the client: a leave
    day is usable for 2 years total -- the year it's granted, plus one
    carried-forward year -- then it expires.
    So this is deliberately a single lookback (based on the previous
    year's OWN tenure-based allocation and usage only, not further
    compounding whatever that previous year might itself have carried in
    from the year before it) -- a day earned two years ago is already
    gone by now, not still being re-carried. Shared by
    compute_leave_summary (the HR-facing annual summary) and
    _leave_status_by_date (the payroll-facing on_leave/unpaid_leave split
    below), so both always agree on the same effective balance for a
    given year.
    """
    if year <= employee.hire_date.year:
        return 0
    allocation_last_year = _annual_leave_allocation(employee, year - 1)
    used_last_year = _days_used_in_year(employee, year - 1)
    return max(0, allocation_last_year - used_last_year)


def compute_undertime_deduction(employee, year):
    """
    Accumulated shortfall below a full 8-hour workday, on days marked
    'present', for `year` -- confirmed with the client: every full 8
    hours (480 minutes) of accumulated undertime deducts one day from
    the annual leave balance (see UNDERTIME_MINUTES_PER_DEDUCTED_DAY).
    Resets each calendar year, matching how the rest of the annual leave
    balance is tracked -- flag with the client if undertime should
    instead accumulate without ever resetting on January 1st.
    """
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    total_minutes = DailyAttendanceRecord.objects.filter(
        employee=employee, date__gte=year_start, date__lte=year_end, status='present',
    ).aggregate(total=Sum('undertime_minutes'))['total'] or 0
    return {
        'total_minutes': total_minutes,
        'deducted_days': total_minutes // UNDERTIME_MINUTES_PER_DEDUCTED_DAY,
        'remainder_minutes': total_minutes % UNDERTIME_MINUTES_PER_DEDUCTED_DAY,
    }


def _leave_status_by_date(employee, year):
    """
    {date: 'on_leave' | 'unpaid_leave'} for every day an approved leave
    request covers that year. Friday is skipped entirely -- confirmed
    with the client that it never counts against the balance even when
    it falls inside the requested range, matching
    LeaveRequest.days -- so a Friday inside a leave request is left out
    of this dict and falls through to its normal 'rest_day' status in
    generate_daily_attendance instead.
    """
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    result = {}
    running_used = Decimal('0')
    effective_balance = (
        _annual_leave_allocation(employee, year) + _carried_over_days(employee, year)
        - compute_undertime_deduction(employee, year)['deducted_days']
    )

    requests = LeaveRequest.objects.filter(
        employee=employee, status='approved', start_date__lte=year_end, end_date__gte=year_start,
    ).order_by('start_date')

    for req in requests:
        day = max(req.start_date, year_start)
        last = min(req.end_date, year_end)
        while day <= last:
            if day.weekday() in WEEKEND_WEEKDAYS:
                day += timedelta(days=1)
                continue
            running_used += 1
            status = 'unpaid_leave' if running_used > effective_balance else 'on_leave'
            result[day] = status
            day += timedelta(days=1)

    return result


def generate_daily_attendance(employee, period_start, period_end):
    """Ensure a DailyAttendanceRecord exists for every day in the period; return them all, oldest first."""
    holidays = set(
        Holiday.objects.filter(date__gte=period_start, date__lte=period_end).values_list('date', flat=True)
    )
    leave_status = _leave_status_by_date(employee, period_start.year)
    if period_end.year != period_start.year:
        leave_status.update(_leave_status_by_date(employee, period_end.year))
    checkins = _checkins_by_day(employee, period_start, period_end)

    records = []
    day = period_start
    while day <= period_end:
        if day in leave_status:
            defaults = {'status': leave_status[day]}
        elif day in holidays:
            defaults = {'status': 'holiday'}
        elif day.weekday() in WEEKEND_WEEKDAYS:
            defaults = {'status': 'rest_day'}
        elif day in checkins:
            clock_in, clock_out = checkins[day]
            defaults = {'status': 'present', 'clock_in': clock_in, 'clock_out': clock_out, 'overtime_hours': day_overtime(clock_in, clock_out),
                        'undertime_minutes': day_undertime_minutes(clock_in, clock_out)}
        else:
            defaults = {'status': 'absent'}

        record, _ = DailyAttendanceRecord.objects.get_or_create(employee=employee, date=day, defaults=defaults)
        records.append(record)
        day += timedelta(days=1)

    return records


def count_actual_days(employee, period_start, period_end):
    """How many days of the period the employee really clocked in (a GPS clock-in on that day), Fridays included."""
    return sum(1 for clock_in, _ in _checkins_by_day(employee, period_start, period_end).values() if clock_in is not None)


def count_unpaid_leave_days(employee, period_start, period_end):
    return DailyAttendanceRecord.objects.filter(
        employee=employee, date__gte=period_start, date__lte=period_end, status='unpaid_leave',
    ).count()


def compute_leave_summary(employee, year):
    """
    An employee's annual leave summary for `year`: balance/used/remaining,
    plus how many days were taken in each calendar month -- Friday is
    excluded from every count, same rule as LeaveRequest.days and
    _leave_status_by_date (a Friday inside an approved request's range
    never counts against the balance, whichever month it falls in).

    annual_leave_days is now the tenure-based allocation (see
    _annual_leave_allocation), not the raw Employee.annual_leave_days
    field. carried_over rolls forward for one extra year -- a day is
    usable for 2 years total (see _carried_over_days). undertime_deducted_days is docked
    from the total allowance -- every full 8 hours of accumulated
    shortfall on 'present' days this year costs one day (see
    compute_undertime_deduction).
    """
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    by_month = {m: 0 for m in range(1, 13)}

    requests = list(
        LeaveRequest.objects.filter(
            employee=employee, status='approved', start_date__lte=year_end, end_date__gte=year_start,
        ).order_by('start_date')
    )
    for req in requests:
        day = max(req.start_date, year_start)
        last = min(req.end_date, year_end)
        while day <= last:
            if day.weekday() not in WEEKEND_WEEKDAYS:
                by_month[day.month] += 1
            day += timedelta(days=1)

    total_used = sum(by_month.values())
    annual_leave_days = _annual_leave_allocation(employee, year)
    carried_over = _carried_over_days(employee, year)
    undertime = compute_undertime_deduction(employee, year)
    total_allowance = annual_leave_days + carried_over - undertime['deducted_days']
    return {
        'employee': employee,
        'year': year,
        'by_month': by_month,
        'requests': requests,
        'annual_leave_days': annual_leave_days,
        'carried_over': carried_over,
        'undertime_minutes': undertime['total_minutes'],
        'undertime_deducted_days': undertime['deducted_days'],
        'undertime_remainder_minutes': undertime['remainder_minutes'],
        'total_allowance': total_allowance,
        'total_used': total_used,
        'remaining': total_allowance - total_used,
    }
