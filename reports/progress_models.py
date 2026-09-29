"""
Project Progress / Schedule-of-Values Models

This module implements the hierarchical "BOQ progress breakdown" structure
that appears in both the monthly consultant report (e.g. EDGE) and the
monthly technical & financial report for the owner:

    Main Item (Phase)  --6%--   e.g. "Design & Licensing Works"
        Sub-item        --3%--  e.g. "Design works"
        Sub-item        --2.5%--e.g. "Submission of licenses & fee payment"
        Sub-item        --0.5%--e.g. "Review & approval"

Every ProjectPhase / ProjectPhaseSubItem weight is expressed as a
percentage OF THE TOTAL CONTRACT VALUE (not of the parent phase), exactly
like the source documents: the sub-item weights within a phase sum up to
that phase's own weight, and all phase weights across a project sum to
100%.

Progress against each sub-item is recorded over time in
ProjectPhaseProgressEntry (one row per reading), optionally tied back to
the daily or monthly report that captured it. This gives:

    - cumulative project completion % (for the executive summary /
      progress-summary sections), and
    - a monetary "value of work done" once a contract value is known
      (weight% * contract_value * execution_fraction), which is exactly
      the "الإجمالي حسب نسب التنفيذ" column in the owner's financial
      report.

PRICING lives on the same two levels. Each phase and each sub-item can carry a
unit, a quantity, a budget (cost) unit price and a contract (sell) unit price -- exactly
the columns of the tender's bill of quantities. Sub-items are the priced lines; a phase
that is priced as a whole (a lump sum with no real sub-items) is carried by one
automatic "whole item" sub-item, so progress can still be recorded against it. A phase's
totals are always the sum of its sub-items. See ProjectPhase.sync_whole_item().

Nothing here computes payments/retention yet -- that belongs to a later,
dedicated "owner financial report" module. This module only establishes
the shared progress-tracking foundation both the EDGE monthly report and
the owner report will read from.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from accounts.models import CustomUser
from projects.models import Project


class ProjectPhase(models.Model):
    """
    Main BOQ / Work-Breakdown item ("البند الرئيسي") for a project.

    Example: "Foundations & Tie-Beam Works", weight_percentage=10.000
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='phases',
        help_text=_('Associated project')
    )

    code = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('Display code/number for this phase (e.g. "1", "2")')
    )

    name_ar = models.CharField(
        max_length=255,
        help_text=_('Phase name in Arabic')
    )

    name_en = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Phase name in English')
    )

    weight_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text=_('This phase\'s weight as a percentage of the TOTAL contract value')
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text=_('Display order within the project')
    )

    notes = models.TextField(blank=True)

    # ---- pricing (see the module docstring) ----
    section = models.CharField(
        max_length=100, blank=True,
        help_text=_('Bill-of-quantities section this item belongs to, e.g. "Civil Works" -- used to group and subtotal')
    )
    unit = models.CharField(max_length=20, blank=True, help_text=_('Unit of measure, e.g. m2, m, No., L.S.'))
    quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    budget_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text=_('Expected cost per unit')
    )
    contract_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text=_('Price per unit under the contract (what the owner pays)')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Project Phase')
        verbose_name_plural = _('Project Phases')
        ordering = ['project', 'order', 'code']
        unique_together = ('project', 'code')
        indexes = [
            models.Index(fields=['project', 'order']),
        ]

    def __str__(self):
        label = self.name_en or self.name_ar
        prefix = f"{self.code}. " if self.code else ""
        return f"{self.project.project_symbol} - {prefix}{label}"

    def sub_items_weight_total(self):
        """Sum of this phase's sub-items' weights (should equal weight_percentage)."""
        total = self.sub_items.aggregate(total=models.Sum('weight_percentage'))['total']
        return total or Decimal('0')

    def execution_percentage(self, as_of_date=None):
        """
        Weighted execution % of this phase, expressed as a fraction of the
        phase's OWN weight (0-100), based on its sub-items' latest progress.
        """
        sub_items = list(self.sub_items.all())
        if not sub_items:
            return Decimal('0')
        phase_weight = self.weight_percentage or Decimal('0')
        if phase_weight == 0:
            return Decimal('0')
        earned = sum(
            (item.weight_percentage * item.latest_execution_fraction(as_of_date))
            for item in sub_items
        )
        return (earned / phase_weight) * Decimal('100')

    # ---- pricing ----
    def budget_total(self):
        """Cost budget of the phase: the sum of its sub-items' budgets."""
        return sum((item.budget_total for item in self.sub_items.all()), Decimal('0'))

    def contract_total(self):
        """Contract (sell) value of the phase: the sum of its sub-items' contract values."""
        return sum((item.contract_total for item in self.sub_items.all()), Decimal('0'))

    def sync_whole_item(self):
        """
        A phase priced as a whole (its own quantity/prices, no real sub-items) is carried by
        one automatic "whole item" sub-item that holds the same figures -- that sub-item is
        what progress is recorded against, and what cost control prices and tracks.
        Once real sub-items exist they take over and the automatic one is dropped (unless it
        already has progress readings, in which case it stays as an ordinary sub-item).
        """
        real_exists = self.sub_items.filter(is_whole=False).exists()
        whole = self.sub_items.filter(is_whole=True).first()

        if real_exists:
            if whole and not whole.progress_entries.exists():
                whole.delete()
            return

        priced = self.quantity is not None or self.budget_unit_price or self.contract_unit_price
        if not priced and not whole:
            return
        if not whole:
            whole = ProjectPhaseSubItem(phase=self, is_whole=True)
        whole.code, whole.name_ar, whole.name_en = self.code, self.name_ar, self.name_en
        whole.unit, whole.quantity = self.unit, self.quantity
        whole.budget_unit_price, whole.contract_unit_price = self.budget_unit_price, self.contract_unit_price
        whole.weight_percentage = self.weight_percentage
        whole.save()

    def earned_value(self, contract_value, as_of_date=None):
        """Monetary value of work completed in this phase to date."""
        if not contract_value:
            return Decimal('0')
        sub_items = list(self.sub_items.all())
        earned_weight = sum(
            (item.weight_percentage * item.latest_execution_fraction(as_of_date))
            for item in sub_items
        )
        return (earned_weight / Decimal('100')) * Decimal(contract_value)


class ProjectPhaseSubItem(models.Model):
    """
    Sub-item ("بند فرعي") under a ProjectPhase.

    weight_percentage is ALSO a percentage of the total contract value
    (not of the parent phase) -- the sub-item weights within one phase
    sum to that phase's weight.
    """

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.CASCADE,
        related_name='sub_items',
        help_text=_('Parent phase')
    )

    name_ar = models.CharField(max_length=255, help_text=_('Sub-item name in Arabic'))
    name_en = models.CharField(max_length=255, blank=True, help_text=_('Sub-item name in English'))

    weight_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text=_('This sub-item\'s weight as a percentage of the TOTAL contract value')
    )

    planned_start_date = models.DateField(null=True, blank=True)
    planned_completion_date = models.DateField(null=True, blank=True)

    order = models.PositiveIntegerField(default=0)

    # ---- pricing (see the module docstring) ----
    code = models.CharField(max_length=20, blank=True, help_text=_('Item number in the bill of quantities, e.g. 1.17.1'))
    unit = models.CharField(max_length=20, blank=True, help_text=_('Unit of measure, e.g. m2, m, No., L.S.'))
    quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    budget_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text=_('Expected cost per unit')
    )
    contract_unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, help_text=_('Price per unit under the contract (what the owner pays)')
    )
    is_whole = models.BooleanField(
        default=False, editable=False,
        help_text=_('The automatic stand-in for a phase that is priced as a whole (see ProjectPhase.sync_whole_item)')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Project Phase Sub-item')
        verbose_name_plural = _('Project Phase Sub-items')
        ordering = ['phase', 'order']
        indexes = [
            models.Index(fields=['phase', 'order']),
        ]

    def __str__(self):
        label = self.name_en or self.name_ar
        return f"{self.phase} / {label}"

    @property
    def budget_total(self):
        return ((self.quantity or Decimal('0')) * self.budget_unit_price).quantize(Decimal('0.01'))

    @property
    def contract_total(self):
        return ((self.quantity or Decimal('0')) * self.contract_unit_price).quantize(Decimal('0.01'))

    def latest_progress_entry(self, as_of_date=None):
        qs = self.progress_entries.all()
        if as_of_date:
            qs = qs.filter(report_date__lte=as_of_date)
        return qs.order_by('-report_date', '-created_at').first()

    def latest_execution_percentage(self, as_of_date=None):
        """Cumulative % complete (0-100) of this sub-item's own scope."""
        entry = self.latest_progress_entry(as_of_date)
        return entry.execution_percentage if entry else Decimal('0')

    def latest_execution_fraction(self, as_of_date=None):
        return self.latest_execution_percentage(as_of_date) / Decimal('100')


class ProjectPhaseProgressEntry(models.Model):
    """
    One progress reading for a ProjectPhaseSubItem, e.g. "as of 31/07/2026
    this sub-item is 40% complete". Cumulative, not incremental.
    """

    sub_item = models.ForeignKey(
        ProjectPhaseSubItem,
        on_delete=models.CASCADE,
        related_name='progress_entries',
        help_text=_('The sub-item this reading applies to')
    )

    report_date = models.DateField(
        help_text=_('Date this progress reading applies to')
    )

    execution_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text=_('Cumulative % complete of this sub-item as of report_date')
    )

    daily_report = models.ForeignKey(
        'DailyReport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='phase_progress_entries',
        help_text=_('Daily report this reading was captured in, if any')
    )

    monthly_report = models.ForeignKey(
        'MonthlyReport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='phase_progress_entries',
        help_text=_('Monthly report this reading was captured in, if any')
    )

    recorded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_phase_progress'
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Phase Progress Entry')
        verbose_name_plural = _('Phase Progress Entries')
        ordering = ['sub_item', '-report_date']
        indexes = [
            models.Index(fields=['sub_item', 'report_date']),
        ]

    def __str__(self):
        return f"{self.sub_item} - {self.report_date}: {self.execution_percentage}%"

    def clean(self):
        # Soft guard: cumulative % should not go backwards without an explicit note.
        previous = (
            self.sub_item.progress_entries
            .filter(report_date__lt=self.report_date)
            .order_by('-report_date')
            .exclude(pk=self.pk)
            .first()
        )
        if previous and self.execution_percentage < previous.execution_percentage and not self.notes:
            raise ValidationError(_(
                'Execution percentage dropped compared to a previous reading; '
                'add a note explaining why.'
            ))


class ProjectMilestone(models.Model):
    """
    A named project milestone (e.g. "استلام رخصة البناء", "تسليم المبنى"),
    tied to a ProjectPhase for grouping/reporting purposes -- unlike a
    ProjectPhaseSubItem, a milestone isn't a slice of billable scope, just
    a date to track. Feeds the "Project Key Milestones" table in the
    internal monthly report (see reports.utils.generate_internal_monthly_report_pdf).
    """

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.CASCADE,
        related_name='milestones',
        help_text=_('BOQ phase this milestone belongs to')
    )

    name_ar = models.CharField(max_length=255, help_text=_('Milestone name in Arabic'))
    name_en = models.CharField(max_length=255, blank=True, help_text=_('Milestone name in English'))

    baseline_date = models.DateField(help_text=_('Originally planned/contracted date'))
    forecast_date = models.DateField(
        null=True, blank=True,
        help_text=_('Current expected date, if revised from the baseline')
    )
    actual_date = models.DateField(
        null=True, blank=True,
        help_text=_('Date the milestone was actually achieved')
    )

    notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Project Milestone')
        verbose_name_plural = _('Project Milestones')
        ordering = ['phase', 'order', 'baseline_date']
        indexes = [
            models.Index(fields=['phase', 'baseline_date']),
        ]

    def __str__(self):
        label = self.name_en or self.name_ar
        return f"{self.phase.project.project_symbol} - {label}"

    @property
    def project(self):
        return self.phase.project

    @property
    def effective_due_date(self):
        return self.forecast_date or self.baseline_date

    @property
    def status(self):
        """One of: achieved_on_time, achieved_late, overdue, upcoming."""
        if self.actual_date:
            return 'achieved_late' if self.actual_date > self.baseline_date else 'achieved_on_time'
        due = self.effective_due_date
        if due and due < timezone.localdate():
            return 'overdue'
        return 'upcoming'


class ProjectPhasePhoto(models.Model):
    """
    A site photo tagged to a project phase (and optionally a specific
    sub-item), for the phase-organized photo galleries used by the EDGE
    monthly report ("Photographic Record: Phase 3 - ...") and the owner
    financial report ("صور المشروع - المرحلة الثالثة"). Unlike
    reports.ReportAttachment (tied to one specific daily/monthly report),
    a phase photo lives independently of any single report and can be
    referenced from several: which report(s) first published it, if any,
    is optional metadata rather than the primary organization.
    """

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.CASCADE,
        related_name='photos',
        help_text=_('Project phase this photo documents')
    )

    sub_item = models.ForeignKey(
        ProjectPhaseSubItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='photos',
        help_text=_('Specific sub-item this photo documents, if any')
    )

    photo = models.ImageField(upload_to='phase_photos/%Y/%m/')
    caption = models.TextField(blank=True, help_text=_('Description / location / activity / reference'))
    taken_date = models.DateField(default=timezone.localdate)

    daily_report = models.ForeignKey(
        'DailyReport', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phase_photos',
    )
    monthly_report = models.ForeignKey(
        'MonthlyReport', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phase_photos',
    )
    owner_financial_report = models.ForeignKey(
        'OwnerFinancialReport', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='phase_photos',
    )

    order = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Project Phase Photo')
        verbose_name_plural = _('Project Phase Photos')
        ordering = ['phase', 'order', '-taken_date']
        indexes = [
            models.Index(fields=['phase', 'taken_date']),
        ]

    def __str__(self):
        return f"{self.phase} - {self.caption[:50] or 'Photo'}"


def calculate_project_progress(project, as_of_date=None, contract_value=None):
    """
    Convenience helper: returns the overall cumulative progress % for a
    project (sum of weight% * execution_fraction across every sub-item),
    plus a per-phase breakdown suitable for rendering the "BOQ Progress
    Breakdown by Item" table used in both the EDGE and owner reports.

    Returns a dict:
        {
            'overall_percentage': Decimal,
            'phases': [
                {
                    'phase': ProjectPhase,
                    'execution_percentage': Decimal,   # of the phase's own weight
                    'earned_value': Decimal or None,
                    'sub_items': [
                        {
                            'sub_item': ProjectPhaseSubItem,
                            'execution_percentage': Decimal,
                        },
                        ...
                    ],
                },
                ...
            ],
        }
    """
    phases = (
        ProjectPhase.objects
        .filter(project=project)
        .prefetch_related('sub_items__progress_entries')
        .order_by('order', 'code')
    )

    overall_earned_weight = Decimal('0')
    phase_rows = []

    for phase in phases:
        sub_rows = []
        phase_earned_weight = Decimal('0')
        for sub_item in phase.sub_items.all():
            fraction = sub_item.latest_execution_fraction(as_of_date)
            phase_earned_weight += sub_item.weight_percentage * fraction
            sub_rows.append({
                'sub_item': sub_item,
                'execution_percentage': sub_item.latest_execution_percentage(as_of_date),
            })

        overall_earned_weight += phase_earned_weight

        earned_value = None
        if contract_value:
            earned_value = (phase_earned_weight / Decimal('100')) * Decimal(contract_value)

        phase_execution_pct = (
            (phase_earned_weight / phase.weight_percentage) * Decimal('100')
            if phase.weight_percentage else Decimal('0')
        )

        phase_rows.append({
            'phase': phase,
            'execution_percentage': phase_execution_pct,
            'earned_value': earned_value,
            'sub_items': sub_rows,
        })

    return {
        'overall_percentage': overall_earned_weight,
        'phases': phase_rows,
    }


def recalculate_weights_from_contract(project):
    """
    Set every sub-item's weight to its share of the project's total contract value, and each
    phase's weight to the sum of its sub-items -- so the weights that drive progress and the
    owner's financial report follow the priced bill of quantities instead of being typed twice.
    Returns the total contract value; raises ValueError if nothing is priced yet.
    """
    sub_items = list(ProjectPhaseSubItem.objects.filter(phase__project=project).select_related('phase'))
    total = sum((item.contract_total for item in sub_items), Decimal('0'))
    if total <= 0:
        raise ValueError('No contract prices are entered yet -- price at least one item first.')

    phase_weights = {}
    for item in sub_items:
        weight = (item.contract_total / total * Decimal('100')).quantize(Decimal('0.001'))
        if item.weight_percentage != weight:
            item.weight_percentage = weight
            item.save(update_fields=['weight_percentage', 'updated_at'])
        phase_weights[item.phase_id] = phase_weights.get(item.phase_id, Decimal('0')) + weight
    for phase in ProjectPhase.objects.filter(project=project):
        weight = phase_weights.get(phase.pk, Decimal('0'))
        if phase.weight_percentage != weight:
            phase.weight_percentage = weight
            phase.save(update_fields=['weight_percentage', 'updated_at'])
    return total
