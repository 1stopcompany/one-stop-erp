"""
The month's employee payroll laid out like the company's own salary sheet ("جدول رواتب الموظفين شهر MM-YYYY", file
08.2026.xlsx): one line per employee with the 16 columns of that sheet, a totals line, the "prepared by / reviewed by" line and
the notes written for the month. Used by the Excel and the PDF export so both come out the same.

Columns (right to left on the page):
    # | الأسم | طبيعة العمل | رقم الهوية | رقم الحساب البنكي | عدد الأيام | الراتب الأساسي | الساعات الأضافية | أجر الساعة الأضافية |
    بدل ساعات إضافي | بدلات أخرى | مقتطعات | الضريبة | اجمالي الراتب | سلف | صافي الراتب بعد الضريبة

As in the sheet: مقتطعات = other deductions + the unpaid-leave deduction; اجمالي الراتب = base + tax + overtime + allowances -
deductions (the tax is added on top, the company bears it); صافي الراتب = اجمالي - الضريبة - سلف, which is the payslip's net pay
(the tax is shown for information and never reduces what the employee receives).
"""
from datetime import timedelta
from decimal import Decimal

HEADERS = [
    '#', 'الأسم', 'طبيعة العمل', 'رقم الهوية', 'رقم الحساب البنكي', 'عدد الايام', 'الراتب الأساسي', 'الساعات الأضافية',
    'أجر الساعة الأضافية', 'بدل ساعات إضافي', 'بدلات أخرى', 'مقتطعات', 'الضريبة', 'اجمالي الراتب', 'سلف',
    'صافي الراتب بعد الضريبة - شيكل',
]


def working_days(payslip):
    """Paid days of the month: the days of the period the employee was employed, Fridays and unpaid leave left out."""
    employee = payslip.employee
    start = max(payslip.period_start, employee.hire_date) if employee.hire_date else payslip.period_start
    end = min(payslip.period_end, employee.termination_date) if employee.termination_date else payslip.period_end
    days, day = 0, start
    while day <= end:
        days += day.weekday() != 4   # Friday is the weekly day off
        day += timedelta(days=1)
    return max(days - int(payslip.unpaid_leave_days or 0), 0)


def overtime_rate(payslip):
    """Pay for one overtime hour."""
    if payslip.overtime_hours:
        return payslip.overtime_pay / payslip.overtime_hours
    multiplier = payslip.salary_structure.overtime_multiplier if payslip.salary_structure_id else Decimal('1.5')
    return payslip.hourly_rate * multiplier


def sheet_rows(payslips):
    """One dict per payslip, in the order given, with every column of the sheet."""
    rows = []
    for n, p in enumerate(payslips, start=1):
        employee = p.employee
        deductions = p.other_deductions + p.unpaid_leave_deduction
        total = p.base_pay + p.tax + p.overtime_pay + p.other_allowances - deductions
        rows.append({
            'n': n, 'name': employee.full_name, 'position': employee.position.title if employee.position_id else '',
            'national_id': employee.national_id or '', 'bank_account': employee.bank_account_number or '',
            'days': working_days(p), 'base': p.base_pay, 'ot_hours': p.overtime_hours,
            'ot_rate': overtime_rate(p), 'ot_value': p.overtime_pay, 'allowances': p.other_allowances,
            'deductions': deductions, 'tax': p.tax, 'total': total, 'advances': p.advances, 'net': p.net_pay,
        })
    return rows


def totals(rows):
    """The columns the sheet sums: base, deductions, tax, total, advances, net (plus overtime pay and allowances)."""
    keys = ('base', 'ot_value', 'allowances', 'deductions', 'tax', 'total', 'advances', 'net')
    return {key: sum((r[key] for r in rows), Decimal('0')) for key in keys}


def title(period_start):
    return f'جدول رواتب الموظفين شهر {period_start:%m-%Y}'
