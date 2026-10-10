"""
Owner Financial & Technical Report

This is a distinct report type from MonthlyReport (which covers the EDGE
consultant's progress-focused monthly report): it targets the owner/client
and centers on the payment-due calculation and material/equipment price
tracking, on top of the same BOQ phase progress captured in
progress_models.py.

Payment formula (reverse-engineered from a real 07/2026 report; the
performance-retention step was corrected per the client's confirmation
that it applies to the payment net of the advance-payment deduction, not
to the gross earned value -- see the seed_tab_project_phases management
command for the source data):

    advance_retention_rate% = ROUND(advance_payment_value / contract_value * 100, 2)
    advance_retention_amount = earned_value_to_date * advance_retention_rate%
    performance_retention_amount = (earned_value_to_date - advance_retention_amount) * performance_retention_rate%
    amount_due = earned_value_to_date - advance_retention_amount
                 - performance_retention_amount - previous_payments_total

Note the advance-payment recovery rate is ROUNDED to 2 decimal places
BEFORE being applied -- using the exact unrounded fraction gives a
result off by tens of shekels from the real, signed report.
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

from .models import BaseReport
from .progress_models import calculate_project_progress


def _num(value):
    return None if value is None else str(value)


def _freeze_progress(result):
    """calculate_project_progress() -> plain JSON data (phases and items copied with every attribute the report prints)."""
    def phase_data(phase):
        return {'id': phase.pk, 'code': phase.code, 'name_ar': phase.name_ar, 'name_en': phase.name_en, 'order': phase.order,
                'weight_percentage': str(phase.weight_percentage)}

    def item_data(item):
        return {'id': item.pk, 'code': item.code, 'name_ar': item.name_ar, 'name_en': item.name_en, 'order': item.order,
                'weight_percentage': str(item.weight_percentage),
                'planned_start_date': item.planned_start_date.isoformat() if item.planned_start_date else None,
                'planned_completion_date': item.planned_completion_date.isoformat() if item.planned_completion_date else None}

    return {
        'overall_percentage': str(result['overall_percentage']),
        'phases': [{
            'phase': phase_data(row['phase']), 'execution_percentage': _num(row['execution_percentage']), 'earned_value': _num(row['earned_value']),
            'sub_items': [{'sub_item': item_data(sub['sub_item']), 'execution_percentage': _num(sub['execution_percentage'])} for sub in row['sub_items']],
        } for row in result['phases']],
    }


class _Items:
    """Stands in for `phase.sub_items` (the printed report only calls .all() on it)."""
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)


def _thaw_progress(data):
    """The frozen JSON -> the same structure calculate_project_progress() returns, with plain objects for phases and items."""
    def dec(value):
        return None if value is None else Decimal(value)

    def day(value):
        return datetime.date.fromisoformat(value) if value else None

    phases = []
    for row in data['phases']:
        items, sub_rows = [], []
        for sub in row['sub_items']:
            d = sub['sub_item']
            item = SimpleNamespace(pk=d['id'], id=d['id'], code=d['code'], name_ar=d['name_ar'], name_en=d['name_en'], order=d['order'],
                                   weight_percentage=Decimal(d['weight_percentage']), planned_start_date=day(d['planned_start_date']),
                                   planned_completion_date=day(d['planned_completion_date']))
            items.append(item)
            sub_rows.append({'sub_item': item, 'execution_percentage': dec(sub['execution_percentage'])})
        d = row['phase']
        phase = SimpleNamespace(pk=d['id'], id=d['id'], code=d['code'], name_ar=d['name_ar'], name_en=d['name_en'], order=d['order'],
                                weight_percentage=Decimal(d['weight_percentage']), sub_items=_Items(items))
        phases.append({'phase': phase, 'execution_percentage': dec(row['execution_percentage']), 'earned_value': dec(row['earned_value']),
                       'sub_items': sub_rows})
    return {'overall_percentage': Decimal(data['overall_percentage']), 'phases': phases}


class OwnerFinancialReport(BaseReport):
    """Monthly technical & financial report for the project owner/client."""

    REPORT_NUMBER_PREFIX = 'OFR'

    reporting_period_from = models.DateField(help_text=_('Start date of the reporting period'))
    reporting_period_to = models.DateField(help_text=_('End date of the reporting period (the "as of" date for progress)'))

    # Snapshots of the contract terms at report time, so amending the
    # contract later doesn't silently rewrite the numbers on past reports.
    contract_value_snapshot = models.DecimalField(max_digits=15, decimal_places=2)
    advance_payment_value_snapshot = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    performance_retention_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))

    previous_payments_total = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Cumulative amount already certified/paid before this report (entered manually, matching the source report)')
    )

    progress_summary = models.TextField(blank=True, help_text=_('"ملخص سير المشروع" narrative'))
    next_month_expected_works = models.TextField(blank=True, help_text=_('"الأعمال المتوقعة للشهر القادم"'))
    next_month_expected_completion_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text=_('Expected cumulative completion % by next month')
    )
    material_price_note = models.TextField(blank=True, help_text=_('"الوضع الراهن لأسعار المواد" narrative'))

    # No model-level default: MySQL/MariaDB reject any literal DEFAULT on a TEXT/BLOB column outright
    # (error 1067), no matter the value. The standard pre-filled wording lives in
    # reports/forms.py::OwnerFinancialReportForm (STANDARD_CLOSING_NOTE / __init__) as a form-level
    # `initial=` instead, applied only when adding a new report -- same UX, no DB default involved.
    closing_note = models.TextField(
        blank=True,
        null=True,
        help_text=_('Closing "ملاحظة تنظيمية متعلقة بالتدفق المالي للمشروع" note (pre-filled with the standard wording, editable per report)')
    )

    class Meta:
        verbose_name = _('Owner Financial Report')
        verbose_name_plural = _('Owner Financial Reports')
        ordering = ['-reporting_period_to', '-created_at']
        indexes = [
            models.Index(fields=['project', 'reporting_period_to']),
        ]

    def get_report_type(self):
        return 'owner_financial'

    # A report that went to the owner is FROZEN: the progress it showed (overall %, every phase and item with its weight, dates and
    # execution %) is stored here, and the report keeps showing exactly that, whatever is edited in the BOQ or the progress later.
    frozen_at = models.DateTimeField(null=True, blank=True, help_text=_('When the report was frozen as final (its figures no longer follow the live progress)'))
    frozen_progress = models.JSONField(null=True, blank=True, help_text=_('The progress breakdown as it was when the report was frozen'))

    @property
    def is_frozen(self):
        return self.frozen_at is not None and self.frozen_progress is not None

    @property
    def is_editable(self):
        return self.status == 'draft' and not self.is_frozen

    def _progress_result(self):
        if self.is_frozen:
            return _thaw_progress(self.frozen_progress)
        return calculate_project_progress(
            self.project, as_of_date=self.reporting_period_to, contract_value=self.contract_value_snapshot,
        )

    def freeze(self, when=None):
        """Store the current progress breakdown and stop following the live data."""
        from django.utils import timezone
        self.frozen_progress = _freeze_progress(calculate_project_progress(
            self.project, as_of_date=self.reporting_period_to, contract_value=self.contract_value_snapshot))
        self.frozen_at = when or timezone.now()
        self.save(update_fields=['frozen_progress', 'frozen_at'])

    def unfreeze(self):
        self.frozen_progress = None
        self.frozen_at = None
        self.save(update_fields=['frozen_progress', 'frozen_at'])

    def earned_value_to_date(self):
        """Monetary value of work completed to date ("قيمة الأعمال المنجزة")."""
        result = self._progress_result()
        return (result['overall_percentage'] / Decimal('100')) * self.contract_value_snapshot

    def advance_retention_rate(self):
        """Advance-payment recovery rate, ROUNDED to 2dp before use (see module docstring)."""
        if not self.contract_value_snapshot:
            return Decimal('0')
        rate = (self.advance_payment_value_snapshot / self.contract_value_snapshot) * Decimal('100')
        return rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def advance_retention_amount(self):
        return self.earned_value_to_date() * (self.advance_retention_rate() / Decimal('100'))

    def performance_retention_amount(self):
        """
        Performance retention applies to the payment net of the advance-
        payment deduction (earned value minus advance_retention_amount),
        not to the gross earned value -- confirmed by the client.
        """
        net_of_advance = self.earned_value_to_date() - self.advance_retention_amount()
        return net_of_advance * (self.performance_retention_rate_snapshot / Decimal('100'))

    def amount_due(self):
        return (
            self.earned_value_to_date()
            - self.advance_retention_amount()
            - self.performance_retention_amount()
            - self.previous_payments_total
        )


class OwnerReportPriceComparisonItem(models.Model):
    """
    One material/equipment price-fluctuation line in an owner financial
    report (concrete grades, equipment hourly/daily rates, bulk
    materials). Mirrors the "old price vs. new price" tables in the
    source report, used to track the 1.5%-of-contract-value threshold
    below which price increases don't trigger a contract claim.
    """

    ITEM_TYPE_CHOICES = (
        ('concrete_grade', _('Concrete Grade')),
        ('equipment', _('Equipment')),
        ('material', _('Other Material')),
    )

    report = models.ForeignKey(
        OwnerFinancialReport,
        on_delete=models.CASCADE,
        related_name='price_comparison_items',
        help_text=_('Owner financial report this price comparison belongs to')
    )

    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    item_name = models.CharField(max_length=150, help_text=_('e.g. "B450", "Bobcat", "مواد وطمم"'))
    unit = models.CharField(max_length=50, help_text=_('e.g. كوب / ساعة / يوم / طلعة'))

    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_(
            'Cumulative quantity used to date for this material/equipment line. '
            '"Copy for Next Period" carries this total forward; use "Add Quantity" '
            'on the report to add just the new period\'s usage on top of it.'
        )
    )

    old_unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    price_difference = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        help_text=_('Computed: (new_unit_price - old_unit_price) * quantity')
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Owner Report Price Comparison Item')
        verbose_name_plural = _('Owner Report Price Comparison Items')
        ordering = ['report', 'item_type', 'item_name']

    def __str__(self):
        return f"{self.report.report_number} - {self.item_name}"

    def save(self, *args, **kwargs):
        self.price_difference = (self.new_unit_price - self.old_unit_price) * self.quantity
        super().save(*args, **kwargs)

    @classmethod
    def cumulative_difference_for_period(cls, project, start_date, end_date):
        """Sum of price differences across all reports in [start_date, end_date] (for the '1.5% of contract' check)."""
        total = cls.objects.filter(
            report__project=project,
            report__reporting_period_to__gte=start_date,
            report__reporting_period_to__lte=end_date,
        ).aggregate(total=models.Sum('price_difference'))['total']
        return total or Decimal('0')

    @classmethod
    def is_within_contract_threshold(cls, project, start_date, end_date, contract_value, threshold_pct=Decimal('1.5')):
        """True if the cumulative price difference over the period stays within threshold_pct of contract_value."""
        if not contract_value:
            return True
        cumulative = cls.cumulative_difference_for_period(project, start_date, end_date)
        return cumulative <= (contract_value * threshold_pct / Decimal('100'))


class OwnerReportPhaseUpdate(models.Model):
    """
    One phase's status line in an owner financial report's "ملخص سير
    المشروع" table -- e.g. "Phase 3: Structural Frame - In Progress -
    <free-text description of what was executed this period>". One phase
    can appear more than once in the same report (the source report lists
    "Phase 3" twice: once for the sub-scope finished, once for the
    sub-scope still in progress), so this is not unique per (report, phase).
    """

    # Plain Arabic labels (no emoji): Tahoma -- the Arabic-capable font used
    # for PDF export -- has no emoji glyphs, so an emoji here would render
    # as an empty box in the exported report. The PDF distinguishes status
    # with a colored cell instead (see generate_owner_financial_report_pdf).
    STATUS_CHOICES = (
        ('done', _('منجزة')),
        ('in_progress', _('قيد التنفيذ')),
        ('pending', _('لم تبدأ بعد')),
    )

    report = models.ForeignKey(
        OwnerFinancialReport,
        on_delete=models.CASCADE,
        related_name='phase_updates',
        help_text=_('Owner financial report this phase status belongs to')
    )

    phase = models.ForeignKey(
        'reports.ProjectPhase',
        on_delete=models.CASCADE,
        related_name='owner_report_updates',
        help_text=_('Project phase this status line describes')
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')

    work_performed = models.TextField(help_text=_('"الأعمال المنفذة" -- free-text description of work done this period'))

    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Owner Report Phase Update')
        verbose_name_plural = _('Owner Report Phase Updates')
        ordering = ['report', 'order', 'phase__order']

    def __str__(self):
        return f"{self.report.report_number} - {self.phase.name_ar} ({self.get_status_display()})"
