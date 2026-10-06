"""
Palestinian income tax on a monthly salary, exactly as the company's own "ضريبة" sheet (08.2026.xlsx) works it out:

    taxable income = gross pay - transport allowance (10% of gross) - residence (3,000) - university deduction
    tax            = 5% of the first 6,250 of taxable income
                   + 10% of the part between 6,250 and 12,500
                   + 15% of the part above 12,500

The figure is shown for information only (the worker is paid his full net wage; the tax is not subtracted).
The rates and thresholds live here so that a change in the law is a change of these few constants.
"""
from decimal import Decimal

TRANSPORT_RATE = Decimal('0.10')          # مواصلات: a tenth of the gross pay is exempt
RESIDENCE_DEDUCTION = Decimal('3000')     # اقامة: fixed monthly deduction
# (upper limit of the slice, rate); the last slice has no limit
BRACKETS = [(Decimal('6250'), Decimal('0.05')), (Decimal('12500'), Decimal('0.10')), (None, Decimal('0.15'))]


def taxable_income(gross, university=0):
    """الدخل الخاضع: never below zero."""
    gross = Decimal(gross)
    return max(gross - gross * TRANSPORT_RATE - RESIDENCE_DEDUCTION - Decimal(university), Decimal('0'))


def monthly_income_tax(gross, university=0):
    """The month's income tax for a gross pay (and an optional university deduction), rounded to 2 decimals."""
    remaining = taxable_income(gross, university)
    tax, lower = Decimal('0'), Decimal('0')
    for upper, rate in BRACKETS:
        if remaining <= 0:
            break
        width = remaining if upper is None else min(remaining, upper - lower)
        tax += width * rate
        remaining -= width
        lower = upper if upper is not None else lower
    return tax.quantize(Decimal('0.01'))
