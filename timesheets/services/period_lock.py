"""
Locking of an employee's monthly attendance sheet (the Daily Time Record).

A month of one employee's DTR is LOCKED in two cases:
  * 'approved' -- HR approved the sheet (MonthlyTimesheetApproval). From then on nothing on it can be changed; only an administrator can
    reopen it, and only while the payroll of that month has not been posted.
  * 'posted'   -- the employee's payslip for that month is posted (ترحيل الرواتب). The sheet is then frozen for good: nobody can change it,
    not even an administrator (the payroll would no longer match it).

The rule is enforced where the data is written (DailyAttendanceRecord / EmployeeProjectHours .save() and .delete()), so no page, command or
admin screen can bypass it by accident; the DTR pages also check first, to answer with a clear message. `QuerySet.update()` / `.delete()`
and bulk_create do not go through .save(), so those paths check explicitly. `suspended()` is for deliberate repair scripts only.
"""
from contextlib import contextmanager

from django.core.exceptions import ValidationError

_state = {'suspended': 0}


class PeriodLocked(ValidationError):
    pass


@contextmanager
def suspended():
    """Run repair code that must be allowed to touch a locked month (never used by the pages)."""
    _state['suspended'] += 1
    try:
        yield
    finally:
        _state['suspended'] -= 1


def lock_state(employee, day):
    """None, 'approved' or 'posted' for the month that contains `day`."""
    from .. import models
    employee_id = getattr(employee, 'pk', employee)
    if models.Payslip.objects.filter(employee_id=employee_id, status='posted', period_start__lte=day, period_end__gte=day).exists():
        return 'posted'
    if models.MonthlyTimesheetApproval.objects.filter(employee_id=employee_id, year=day.year, month=day.month).exists():
        return 'approved'
    return None


def lock_message(state, day):
    month = f'{day:%m/%Y}'
    if state == 'posted':
        return f'The attendance sheet of {month} is closed for good: its payroll was posted.'
    return f'The attendance sheet of {month} was approved and is locked. An administrator can reopen it (before the payroll is posted).'


def assert_unlocked(employee, day):
    if _state['suspended']:
        return
    state = lock_state(employee, day)
    if state:
        raise PeriodLocked(lock_message(state, day))


# ------------------------------------------------------------------ approve / reopen
def _audit(user, employee, year, month, text):
    from accounts.models import UserAuditLog
    UserAuditLog.objects.create(user=user, action='update', content_type='timesheets.MonthlyTimesheetApproval', object_id=employee.pk,
                                description=f'Attendance sheet {employee.employee_id} {month:02d}/{year}: {text}')


def approve_month(employee, year, month, user, note=''):
    """HR approves one employee's sheet for a month: it is locked from now on."""
    from datetime import date
    from .. import models
    first = date(year, month, 1)
    state = lock_state(employee, first)
    if state == 'posted':
        raise PeriodLocked(lock_message(state, first))
    approval, created = models.MonthlyTimesheetApproval.objects.get_or_create(
        employee=employee, year=year, month=month, defaults={'approved_by': user, 'note': note[:200]})
    if created:
        _audit(user, employee, year, month, 'approved and locked')
    return approval, created


def reopen_month(employee, year, month, user):
    """An administrator reopens an approved sheet -- impossible once the payroll of that month is posted."""
    from datetime import date
    from .. import models
    if not user.is_admin():
        raise PeriodLocked('Only an administrator can reopen an approved attendance sheet.')
    first = date(year, month, 1)
    if lock_state(employee, first) == 'posted':
        raise PeriodLocked(lock_message('posted', first))
    deleted, _ = models.MonthlyTimesheetApproval.objects.filter(employee=employee, year=year, month=month).delete()
    if deleted:
        _audit(user, employee, year, month, 'reopened by the administrator')
    return bool(deleted)
