"""
Preliminary labor + materials cost estimate for a MonthlyReport.

This is explicitly a rough, early-stage estimate, not real costing:
- Labor is priced at two flat day-rates (skilled/unskilled) rather than
  each worker's real wage, because day-laborer wages aren't tracked
  anywhere in the system yet -- only real HR employees (engineers/
  supervisors with a login account) have a tracked salary.
- Material unit prices are randomly generated placeholders when no real
  price has been entered yet, because real supplier quotes aren't tracked
  per delivery yet either. Every such price is flagged
  (MaterialSupply.unit_price_is_estimated) so it's never confused with a
  real quote in the UI/PDF.
"""

import random
from decimal import Decimal

from ..daily_detail_models import DailyReportWorkerAttendance
from ..models import DailyReport

UNSKILLED_DAILY_WAGE = Decimal('130')
SKILLED_DAILY_WAGE = Decimal('180')

# Placeholder price range for materials with no real quote yet -- wide
# enough to cover anything from a small hardware item to a bulk delivery,
# since this is just a rough stand-in until real supplier prices are
# entered (see MaterialSupply.unit_price / unit_price_is_estimated).
_RANDOM_PRICE_RANGE = (Decimal('5'), Decimal('300'))

# Day laborers' trade titles (imported from the daily site-report Excel
# into DailyReportWorkerAttendance.notes as "Trade: <title>") that count
# as unskilled help rather than a skilled trade. Anything not matching is
# treated as skilled; a worker with no trade text at all is conservatively
# counted as unskilled (the cheaper rate) rather than guessed as skilled.
_UNSKILLED_KEYWORDS = ('مساعد', 'عامل عادي', 'عامل بسيط', 'helper', 'unskilled', 'laborer')


def _extract_trade(notes):
    if notes and notes.startswith('Trade:'):
        return notes[len('Trade:'):].strip()
    return ''


def _is_unskilled(trade_text):
    if not trade_text:
        return True
    return any(keyword in trade_text for keyword in _UNSKILLED_KEYWORDS)


def compute_labor_cost_estimate(report):
    """
    (skilled_days, unskilled_days, costs) for the report's period, counting
    one work-day per (worker, daily report) pair. Workers already linked
    to a real HR Employee record are excluded -- their cost is tracked via
    a real salary elsewhere, so including them here would double-count.
    """
    project = report.project
    daily_reports = DailyReport.objects.filter(
        project=project,
        report_date__gte=report.reporting_period_from,
        report_date__lte=report.reporting_period_to,
    ).exclude(status='rejected')

    rows = DailyReportWorkerAttendance.objects.filter(
        report__in=daily_reports, employee__isnull=True,
    ).values('worker_name', 'notes', 'report_id')

    seen = set()
    skilled_days = 0
    unskilled_days = 0
    for row in rows:
        key = (row['worker_name'].strip().lower(), row['report_id'])
        if key in seen:
            continue
        seen.add(key)
        if _is_unskilled(_extract_trade(row['notes'])):
            unskilled_days += 1
        else:
            skilled_days += 1

    unskilled_cost = unskilled_days * UNSKILLED_DAILY_WAGE
    skilled_cost = skilled_days * SKILLED_DAILY_WAGE

    return {
        'unskilled_days': unskilled_days,
        'skilled_days': skilled_days,
        'unskilled_wage': UNSKILLED_DAILY_WAGE,
        'skilled_wage': SKILLED_DAILY_WAGE,
        'unskilled_cost': unskilled_cost,
        'skilled_cost': skilled_cost,
        'total_labor_cost': unskilled_cost + skilled_cost,
    }


def compute_materials_cost_estimate(report):
    """
    Materials cost for the report's MaterialSupply rows. Any row with no
    unit_price yet gets a random placeholder assigned and saved (so it
    stays stable across repeated views/exports instead of re-randomizing
    every time) -- flagged via unit_price_is_estimated so it always
    displays as a placeholder, never as a real quote.
    """
    materials = list(report.material_supplies.all())
    for m in materials:
        if m.unit_price is None:
            m.unit_price = Decimal(str(round(random.uniform(
                float(_RANDOM_PRICE_RANGE[0]), float(_RANDOM_PRICE_RANGE[1]),
            ), 2)))
            m.unit_price_is_estimated = True
            m.save(update_fields=['unit_price', 'unit_price_is_estimated'])

    items = [
        {
            'material': m,
            'total_cost': m.total_cost(),
        }
        for m in materials
    ]
    total_materials_cost = sum((i['total_cost'] for i in items), Decimal('0'))

    return {
        'items': items,
        'total_materials_cost': total_materials_cost,
        'any_estimated': any(m.unit_price_is_estimated for m in materials),
    }


def compute_cost_estimate(report):
    labor = compute_labor_cost_estimate(report)
    materials = compute_materials_cost_estimate(report)
    return {
        'labor': labor,
        'materials': materials,
        'grand_total': labor['total_labor_cost'] + materials['total_materials_cost'],
    }
