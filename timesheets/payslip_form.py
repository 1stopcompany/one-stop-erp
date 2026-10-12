"""
Data behind the monthly payslip form (قسيمة الراتب الشهرية): every figure printed on it, worked out from the Payslip, plus the
amount in words. The admin can still change what is PRINTED before it goes to the printer (Payslip.print_overrides): the form
here returns the computed values, and `effective()` lays the admin's own entries over them. Overrides never touch the real payroll
figures (gross / net / the posted run).
"""
import calendar
from datetime import date
from decimal import Decimal

ZERO = Decimal('0')

# the printed fields the admin may change before printing: key -> (Arabic label, kind)
OVERRIDE_FIELDS = [
    ('job_title', 'الوصف الوظيفي', 'text'), ('department', 'القسم / الدائرة', 'text'),
    ('working_days', 'ايام العمل', 'number'), ('friday_days', 'ايام الجمعة', 'number'),
    ('leave_entitled', 'الاجازات المرصدة', 'number'), ('official_holidays', 'العطل الرسمية', 'number'),
    ('leave_used', 'الاجازات المستنفذة', 'number'), ('paid_days', 'الايام المدفوعة', 'number'),
    ('leave_balance', 'الرصيد الاجازات المتبقي', 'number'),
    ('bank_name', 'اسم البنك', 'text'), ('bank_account', 'رقم الحساب', 'text'), ('bank_branch', 'الفرع', 'text'),
    ('currency', 'العملة', 'text'),
    ('previous_total', 'كشف حساب للدفعات السابقة - الراتب', 'number'), ('previous_bonus', 'كشف حساب للدفعات السابقة - بونص', 'number'),
    ('gross', 'الراتب الاجمالي', 'number'), ('base', 'الراتب الاساسي', 'number'),
    ('transport', 'مواصلات', 'number'), ('overtime', 'بدل اضافي', 'number'), ('other_allowances', 'بدلات اخرى', 'number'),
    ('income_tax', 'ضريبة الدخل - للعلم', 'number'), ('advances', 'سلف', 'number'),
    ('unpaid_leave', 'خصم الاجازات غير المدفوعة', 'number'), ('other_deductions', 'خصومات اخرى', 'number'),
    ('extra_benefits', 'امتيازات اضافية', 'number'), ('bonus', 'بونص', 'number'),
    ('net', 'الراتب للدفع', 'number'), ('words', 'المبلغ بالكلمات', 'text'),
]
NUMBER_KEYS = {key for key, _, kind in OVERRIDE_FIELDS if kind == 'number'}


# ------------------------------------------------------------------ the amount in words
_UNITS = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة']
_TEENS = {10: 'عشرة', 11: 'أحد عشر', 12: 'اثنا عشر', 13: 'ثلاثة عشر', 14: 'أربعة عشر', 15: 'خمسة عشر', 16: 'ستة عشر',
          17: 'سبعة عشر', 18: 'ثمانية عشر', 19: 'تسعة عشر'}
_TENS = {2: 'عشرون', 3: 'ثلاثون', 4: 'أربعون', 5: 'خمسون', 6: 'ستون', 7: 'سبعون', 8: 'ثمانون', 9: 'تسعون'}
_HUNDREDS = {1: 'مئة', 2: 'مئتان', 3: 'ثلاثمئة', 4: 'أربعمئة', 5: 'خمسمئة', 6: 'ستمئة', 7: 'سبعمئة', 8: 'ثمانمئة', 9: 'تسعمئة'}


def _below_thousand(n):
    """1..999 in words (masculine)."""
    parts = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest < 10:
            parts.append(_UNITS[rest])
        elif rest < 20:
            parts.append(_TEENS[rest])
        else:
            tens, unit = divmod(rest, 10)
            parts.append((_UNITS[unit] + ' و' if unit else '') + _TENS[tens])
    return ' و'.join(parts)


def _scaled(n, one, two, few, many):
    """n units of a scale word (thousand / million): 'ألف', 'ألفان', 'ثلاثة آلاف', 'أحد عشر ألفًا', 'مئة ألف'."""
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f'{_below_thousand(n)} {few}'
    if n % 100 == 0:   # a round hundred takes the plain singular: خمسمئة ألف, مئة مليون
        return f'{_below_thousand(n)} {one}'
    return f'{_below_thousand(n)} {many}'


def number_words(n):
    """A whole number 0..999,999,999 in Arabic words."""
    n = int(n)
    if n == 0:
        return 'صفر'
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    parts = []
    if millions:
        parts.append(_scaled(millions, 'مليون', 'مليونان', 'ملايين', 'مليونًا'))
    if thousands:
        parts.append(_scaled(thousands, 'ألف', 'ألفان', 'آلاف', 'ألفًا'))
    if units:
        parts.append(_below_thousand(units))
    return ' و'.join(parts)


def _counted(n, single, plural, accusative):
    """The noun after a counted number: 3-10 plural, 11-99 singular accusative, a round hundred plain singular."""
    last = n % 100
    if 3 <= last <= 10:
        return plural
    if last == 0:
        return single
    return accusative


def amount_in_words(amount, currency='شيكل'):
    """e.g. 5000 -> 'خمسة آلاف شيكل فقط لا غير'; 3217.50 -> '... شيكلًا وخمسون أغورة فقط لا غير'."""
    amount = Decimal(amount).quantize(Decimal('0.01'))
    whole, cents = divmod(int(abs(amount) * 100), 100)
    if currency != 'شيكل':
        text = f'{number_words(whole)} {currency}'
    elif whole == 1:
        text = 'شيكل واحد'
    elif whole == 2:
        text = 'شيكلان'
    else:
        text = f'{number_words(whole)} {_counted(whole, "شيكل", "شواكل", "شيكلًا")}'
    if cents:
        text += f' و{number_words(cents)} {_counted(cents, "أغورة", "أغورات", "أغورة")}'
    return f'{text} فقط لا غير'


# ------------------------------------------------------------------ the figures
def _leave_figures(employee, period_start):
    """Entitlement, used in the month, and what is left of the year's leave (see attendance_service.compute_leave_summary)."""
    try:
        from .services.attendance_service import compute_leave_summary
        summary = compute_leave_summary(employee, period_start.year)
        entitled = Decimal(str(summary.get('total_allowance', 0)))
        used_month = Decimal(str(summary.get('by_month', {}).get(period_start.month, 0)))
        remaining = Decimal(str(summary.get('remaining', entitled - Decimal(str(summary.get('total_used', 0))))))
        return entitled, used_month, remaining
    except Exception:
        return ZERO, ZERO, ZERO


def payslip_form_data(payslip):
    """Everything the form prints, as plain values (Decimals / strings), before any manual override."""
    from .models import Holiday, Payslip

    employee = payslip.employee
    start, end = payslip.period_start, payslip.period_end
    month_days = (end - start).days + 1
    fridays = sum(1 for i in range(month_days) if date.fromordinal(start.toordinal() + i).weekday() == 4)
    holidays = Holiday.objects.filter(date__gte=start, date__lte=end)
    official = sum(1 for h in holidays if h.date.weekday() != 4)
    entitled, leave_used, balance = _leave_figures(employee, start)
    unpaid_days = Decimal(payslip.unpaid_leave_days or 0)
    paid_days = Decimal(month_days) - unpaid_days
    if payslip.manual_actual_days not in (None, ''):
        working = Decimal(payslip.manual_actual_days)
    else:
        working = max(ZERO, Decimal(month_days) - fridays - official - leave_used - unpaid_days)

    # what was paid in this year before this month (posted payslips only) and in the years before
    posted = Payslip.objects.filter(employee=employee, status='posted').exclude(pk=payslip.pk)
    earlier_this_year = {p.period_start.month: p.net_pay for p in posted.filter(period_start__year=start.year, period_start__lt=start)}
    earlier_years = sum((p.net_pay for p in posted.filter(period_start__year__lt=start.year)), ZERO)

    overtime = (payslip.overtime_pay or ZERO) + (payslip.weekend_pay or ZERO) + (payslip.holiday_pay or ZERO)
    allowances = overtime + (payslip.other_allowances or ZERO)
    deductions = (payslip.advances or ZERO) + (payslip.other_deductions or ZERO) + (payslip.unpaid_leave_deduction or ZERO)
    data = {
        'month_label': f'{start:%m.%Y}', 'is_posted': payslip.status == 'posted', 'year': start.year, 'month': start.month,
        'employee_id': employee.employee_id, 'name': employee.full_name,
        'job_title': getattr(employee.position, 'title', '') if employee.position_id else '',
        'department': getattr(employee.department, 'name', '') if employee.department_id else '',
        'working_days': working, 'friday_days': Decimal(fridays), 'leave_entitled': entitled, 'official_holidays': Decimal(official),
        'leave_used': leave_used, 'paid_days': paid_days, 'leave_balance': balance,
        'bank_name': employee.bank_name or '', 'bank_account': employee.bank_account_number or '', 'bank_branch': employee.bank_branch or '',
        'currency': 'شيكل',
        'previous_total': earlier_years, 'previous_bonus': ZERO,
        'month_rows': [earlier_this_year.get(m, ZERO) for m in range(1, 13)],
        'gross': payslip.gross_pay, 'base': payslip.base_pay,
        'transport': ZERO, 'overtime': overtime, 'other_allowances': payslip.other_allowances or ZERO,
        'income_tax': payslip.tax or ZERO, 'advances': payslip.advances or ZERO, 'unpaid_leave': payslip.unpaid_leave_deduction or ZERO,
        'other_deductions': payslip.other_deductions or ZERO,
        'extra_benefits': ZERO, 'bonus': ZERO,
        'net': payslip.net_pay, 'note': payslip.note or '',
    }
    data['words'] = amount_in_words(data['net'], data['currency'])
    return data


def effective(payslip):
    """The computed figures with the admin's manual entries laid over them; the totals follow the entries unless typed too."""
    data = payslip_form_data(payslip)
    overrides = payslip.print_overrides or {}
    changed = set()
    for key, value in overrides.items():
        if key not in {k for k, _, _ in OVERRIDE_FIELDS} or value in (None, ''):
            continue
        data[key] = Decimal(str(value)) if key in NUMBER_KEYS else str(value)
        changed.add(key)
    # totals follow the typed lines when the admin did not type the total himself
    data['total_allowances'] = data['transport'] + data['overtime'] + data['other_allowances']
    data['total_deductions'] = data['advances'] + data['other_deductions'] + data['unpaid_leave']
    if 'words' not in changed:
        data['words'] = amount_in_words(data['net'], data['currency'])
    data['changed'] = changed
    # the current month's row in the payments statement is this payslip's own net pay
    rows = list(data['month_rows'])
    rows[data['month'] - 1] = data['net']
    data['month_rows'] = rows
    data['month_total'] = sum(rows, ZERO)
    return data
