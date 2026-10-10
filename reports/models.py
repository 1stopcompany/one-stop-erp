"""
Reports Module Models - Unified Daily and Monthly Reporting System

This module contains all database models for the unified reporting system.
It includes a base Report class with Daily and Monthly report implementations.

Models:
    - BaseReport: Abstract base class for all reports
    - DailyReport: Daily construction reports with workforce, equipment, activities
    - MonthlyReport: Monthly maintenance reports with floor activities and materials
    - DailyWorkForce: Workforce tracking for daily reports
    - DailyEquipment: Equipment tracking for daily reports
    - DailyActivity: Activity logging for daily reports
    - DailyMaterial: Material tracking for daily reports
    - DailyVisitor: Visitor tracking for daily reports
    - FloorActivity: Floor-based activities for monthly reports
    - ExternalWork: External works for monthly reports
    - MaterialSupply: Material supplies for monthly reports
    - UpcomingWork: Upcoming works for monthly reports
    - ReportAttachment: Attachments for both report types
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from accounts.models import CustomUser
from projects.models import Project, ProjectFloor
import uuid
from datetime import datetime, timedelta


class BaseReport(models.Model):
    """
    Abstract base class for all reports
    
    Provides common functionality for both daily and monthly reports.
    """
    
    # Two-stage approval: the creator submits, the Engineering Manager
    # reviews every report company-wide (across all projects) before it
    # goes to the General Manager for final sign-off. Either stage can
    # reject back to the creator with a reason.
    STATUS_CHOICES = (
        ('draft', _('Draft')),
        ('submitted', _('Submitted')),
        ('engineering_approved', _('Approved by Engineering Manager')),
        ('approved', _('Approved by General Manager')),
        ('rejected', _('Rejected')),
        ('archived', _('Archived')),
    )
    
    # Auto-generated fields
    report_number = models.CharField(
        max_length=50,
        unique=True,
        help_text=_('Auto-generated unique report number')
    )
    
    # Reference fields
    project = models.ForeignKey(
    Project,
    on_delete=models.CASCADE,
    related_name='%(class)s_reports',
    help_text=_('Associated construction project')
)
    
    site_engineer = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='%(class)s_reports',
        # Despite the field name (kept as-is across all subclasses to
        # avoid a disruptive rename), this holds whichever role actually
        # authors that report type: a site_engineer for DailyReport, but
        # a project_manager for MonthlyReport/OwnerFinancialReport (see
        # each CreateView's dispatch() for the actual enforcement).
        limit_choices_to={'role__in': ['site_engineer', 'project_manager']},
        help_text=_('User who authored the report (site engineer for daily reports, project manager for monthly/owner financial reports)')
    )
    
    report_date = models.DateField(
        default=timezone.localdate,
        help_text=_('Date this report covers (the work date being reported on) -- editable so a report '
                    'written up the next morning still records the day it actually covers, not the day '
                    'it was filed; see created_at for the real filing timestamp')
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text=_('Current status of the report')
    )
    
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_reviewed',
        limit_choices_to={'role': 'engineering_manager'},
        help_text=_('Engineering manager who reviewed the report (first approval stage)')
    )

    review_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When the engineering manager reviewed the report')
    )

    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_approved',
        limit_choices_to={'role': 'general_manager'},
        help_text=_('General manager who gave final approval')
    )

    approval_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When the report received final approval')
    )

    rejection_reason = models.TextField(
        blank=True,
        help_text=_('Reason given when the engineering manager or general manager rejected this report')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Timestamp of creation')
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Timestamp of last update')
    )
    
    # Subclasses added after DailyReport/MonthlyReport should set this
    # explicitly rather than relying on the legacy DCR/MR fallback below
    # (kept as-is for those two so existing report numbers don't change).
    REPORT_NUMBER_PREFIX = None

    class Meta:
        abstract = True
        ordering = ['-report_date', '-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['site_engineer', 'status']),
            models.Index(fields=['report_date']),
        ]

    def __str__(self):
        return f"{self.report_number} - {self.project.name}"

    def save(self, *args, **kwargs):
        """Generate report number if not set"""
        if not self.report_number:
            prefix = self.REPORT_NUMBER_PREFIX or ('DCR' if isinstance(self, DailyReport) else 'MR')
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            unique_id = str(uuid.uuid4())[:8].upper()
            self.report_number = f"{prefix}-{self.project.project_symbol}-{timestamp}-{unique_id}"
        super().save(*args, **kwargs)


class DailyReport(BaseReport):
    """
    Daily Construction Report Model
    
    Represents a daily report for construction activities including workforce,
    equipment, activities, materials, and visitors.
    """
    
    WEATHER_CHOICES = (
        ('sunny', _('Sunny')),
        ('rainy', _('Rainy')),
        ('cloudy', _('Cloudy')),
        ('windy', _('Windy')),
        ('mixed', _('Mixed')),
        ('stormy', _('Stormy')),
    )
    
    weather_conditions = models.CharField(
        max_length=50,
        choices=WEATHER_CHOICES,
        help_text=_('Weather conditions during the day')
    )
    
    remarks = models.TextField(
        blank=True,
        null=True,
        help_text=_('Additional remarks and notes')
    )

    work_hours_note = models.TextField(
        blank=True,
        null=True,
        help_text=_("Site engineer's note on how today's man-hours split between staff and labor, e.g. \"24 hrs staff / 8 hrs workers\"")
    )

    class Meta:
        verbose_name = _('Daily Report')
        verbose_name_plural = _('Daily Reports')
        ordering = ['-report_date', '-created_at']
        indexes = [
            models.Index(fields=['project', 'report_date']),
            models.Index(fields=['site_engineer', 'report_date']),
        ]
    
    def get_report_type(self):
        return 'daily'


class MonthlyReport(BaseReport):
    """
    Monthly Maintenance Report Model

    Represents a monthly report for a construction project covering a specific
    reporting period. This models the real "Monthly Site Progress Report"
    format submitted to the EDGE (green-building) consultant/certifier: a
    much richer structure than the original floor/external-works/materials
    fields alone -- see MonthlyKeyActivity, MonthlyIssueRiskDelay, and
    MonthlyProgressCategoryItem below for the sections those don't cover,
    and note that the BOQ Progress Breakdown, Photographic Record, and
    Sign-Off sections of that report are NOT separate fields here: they
    reuse, respectively, progress_models.calculate_project_progress()
    (rendered in English via each ProjectPhase/ProjectPhaseSubItem's
    name_en), ProjectPhasePhoto (via its monthly_report FK), and this
    model's own site_engineer/reviewed_by/review_date/approved_by/
    approval_date fields (Prepared By / Reviewed By / Approved By).
    """

    WEATHER_CHOICES = (
        ('sunny', _('Sunny')),
        ('rainy', _('Rainy')),
        ('cloudy', _('Cloudy')),
        ('windy', _('Windy')),
        ('mixed', _('Mixed')),
    )

    reporting_period_from = models.DateField(
        help_text=_('Start date of the reporting period')
    )

    reporting_period_to = models.DateField(
        help_text=_('End date of the reporting period')
    )

    weather_conditions = models.CharField(
        max_length=50,
        choices=WEATHER_CHOICES,
        help_text=_('Weather conditions during the period')
    )

    general_description = models.TextField(
        blank=True,
        null=True,
        help_text=_('General description of activities')
    )

    # ---- "2. Executive Summary" ----
    executive_summary = models.TextField(
        blank=True,
        help_text=_('"Executive Summary" narrative -- project status, phase transition, cumulative progress.')
    )

    # ---- "3. Progress Summary" schedule-variance row (the item rows
    # themselves are MonthlyProgressCategoryItem; the cumulative and
    # this-month percentages are computed, not stored -- see
    # progress_models.calculate_project_progress) ----
    schedule_variance_note = models.CharField(
        max_length=255, blank=True,
        help_text=_('e.g. "≈ +3 days (ahead of schedule), based on 900 calendar days"')
    )

    # ---- "6. Health, Safety & Environment (HSE)" ----
    hse_lti_note = models.CharField(max_length=255, blank=True, verbose_name=_('Lost Time Incidents (LTI)'))
    hse_near_misses_note = models.CharField(max_length=255, blank=True, verbose_name=_('Near Misses Reported (NM)'))
    hse_toolbox_talks_note = models.CharField(max_length=255, blank=True, verbose_name=_('Toolbox Talks Conducted (TBT)'))
    hse_site_inspections_note = models.CharField(max_length=255, blank=True, verbose_name=_('Site Inspections Conducted'))
    hse_corrective_actions_note = models.CharField(max_length=255, blank=True, verbose_name=_('Corrective Actions Open / Closed'))

    # ---- "7. Quality Control / Inspections" ----
    qc_inspections_note = models.TextField(blank=True, help_text=_('Inspections / tests conducted this month'))
    qc_nonconformances_note = models.TextField(blank=True, help_text=_('Non-conformances raised and status'))
    qc_pending_submittals_note = models.TextField(blank=True, help_text=_('Approvals / material submittals pending'))

    # ---- "9. Plan for Next Month" ----
    next_month_plan = models.TextField(blank=True, help_text=_('Plan for next month, one activity per line'))

    # ---- "11. Photographic Record" external album link -- the real EDGE
    # report doesn't embed every site photo, it links out to a full album
    # ("Link : Photos Link"), typically hosted on Dropbox or similar. ----
    photos_external_link = models.URLField(
        max_length=500, blank=True,
        help_text=_('Link to the full external photo album (e.g. Dropbox folder) for this reporting period')
    )

    # ---- Custom display order for this report's page sections (Overview,
    # Progress Summary, Key Activities, ...): a comma-separated list of
    # section ids, e.g. "progress,overview,activities,...". Lets a viewer
    # rearrange which section shows above/below which on the report page
    # (like the Move Up/Down buttons on the Owner Financial report's Phase
    # Status Updates accordion), independent of the fixed category groups
    # the toggle buttons are organized into. Blank means "use the built-in
    # default order" -- see views.MONTHLY_REPORT_DEFAULT_SECTION_ORDER. ----
    section_order = models.CharField(
        max_length=500, blank=True,
        help_text=_('Comma-separated section ids controlling display order on the report page; blank = default order')
    )

    # ---- Revision tracking ("R02.07.2026.Rev02" in the real EDGE report:
    # the same monthly period gets reissued as Rev02, Rev03, ... after the
    # external supervision/consultant (e.g. EDGE) sends back review
    # comments -- see MonthlyReviewComment below for the comment/response
    # log itself. This is separate from the internal draft/submitted/
    # approved workflow above, which tracks this company's own
    # Engineering/General Manager sign-off, not the outside consultant's. ----
    revision_number = models.PositiveIntegerField(
        default=1,
        help_text=_('Revision number of this report for its reporting period (Rev01, Rev02, ... after supervision comments)')
    )
    revision_note = models.CharField(
        max_length=255, blank=True,
        help_text=_('Brief note on what changed in this revision, e.g. "Addressed EDGE comments on slab photos"')
    )

    class Meta:
        verbose_name = _('Monthly Report')
        verbose_name_plural = _('Monthly Reports')
        ordering = ['-reporting_period_to', '-created_at']
        indexes = [
            models.Index(fields=['project', 'reporting_period_to']),
            models.Index(fields=['site_engineer', 'reporting_period_to']),
        ]

    def get_report_type(self):
        return 'monthly'


# ==================== DAILY REPORT RELATED MODELS ====================

class DailyWorkForce(models.Model):
    """
    Work Force Model for Daily Reports
    
    Tracks workforce information for a daily report.
    """
    
    CATEGORY_CHOICES = [
        ('management', _('Management')),
        ('skilled', _('Skilled Labor')),
        ('unskilled', _('Unskilled Labor')),
        ('contractor', _('Contractor')),
    ]
    
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='workforce',
        help_text=_('Daily report this workforce belongs to')
    )
    
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        help_text=_('Category of workforce')
    )
    
    designation = models.CharField(
        max_length=255,
        help_text=_('Job designation or title')
    )
    
    count = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text=_('Number of workers in this category')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Daily Work Force')
        verbose_name_plural = _('Daily Work Forces')
        ordering = ['report', 'category']
        indexes = [
            models.Index(fields=['report', 'category']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - {self.designation} ({self.count})"


class DailyEquipment(models.Model):
    """
    Equipment Model for Daily Reports
    
    Tracks equipment usage and availability on site.
    """
    
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='equipment',
        help_text=_('Daily report this equipment belongs to')
    )

    equipment_master = models.ForeignKey(
        'EquipmentMaster',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='daily_usage',
        help_text=_('Chosen from the equipment list; required going forward, nullable only so historical rows recorded before this list existed still load')
    )

    activity = models.ForeignKey(
        'DailyReportActivityProgress',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_used',
        help_text=_("Which of this report's logged activities this equipment was used for")
    )

    equipment_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Set automatically from the chosen equipment; kept editable only for historical rows from before the equipment list existed')
    )

    hours_worked = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(24)],
        help_text=_('Number of hours equipment worked')
    )
    
    quantity_idle = models.IntegerField(
        validators=[MinValueValidator(0)],
        default=0,
        help_text=_('Quantity of equipment idle')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Daily Equipment')
        verbose_name_plural = _('Daily Equipment')
        ordering = ['report', 'equipment_name']
        indexes = [
            models.Index(fields=['report']),
        ]

    def save(self, *args, **kwargs):
        if self.equipment_master_id:
            self.equipment_name = self.equipment_master.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.report.report_number} - {self.equipment_name}"


class DailyActivity(models.Model):
    """
    Daily Activity Model
    
    Documents daily construction activities.
    """
    
    ACTIVITY_CHOICES = [
        ('excavation', _('Excavation')),
        ('foundation', _('Foundation Work')),
        ('structure', _('Structural Work')),
        ('finishing', _('Finishing Work')),
        ('painting', _('Painting')),
        ('plumbing', _('Plumbing')),
        ('electrical', _('Electrical')),
        ('hvac', _('HVAC')),
        ('inspection', _('Inspection')),
        ('testing', _('Testing')),
        ('other', _('Other')),
    ]
    
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='daily_activities',
        help_text=_('Daily report this activity belongs to')
    )
    
    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_CHOICES,
        help_text=_('Type of activity')
    )
    
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Location of activity on site')
    )
    
    activity_description = models.TextField(
        help_text=_('Detailed description of the activity')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Daily Activity')
        verbose_name_plural = _('Daily Activities')
        ordering = ['report', 'created_at']
        indexes = [
            models.Index(fields=['report', 'activity_type']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - {self.get_activity_type_display()}"


class DailyMaterial(models.Model):
    """
    Daily Material Model
    
    Tracks materials delivered during the day.
    """
    
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='daily_materials',
        help_text=_('Daily report this material belongs to')
    )
    
    material_description = models.CharField(
        max_length=255,
        help_text=_('Description of the material')
    )
    
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text=_('Quantity of material')
    )
    
    unit = models.CharField(
        max_length=50,
        help_text=_('Unit of measurement (cubic meters, tons, pieces, etc.)')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Daily Material')
        verbose_name_plural = _('Daily Materials')
        ordering = ['report', 'material_description']
        indexes = [
            models.Index(fields=['report']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - {self.material_description}"


class DailyVisitor(models.Model):
    """
    Daily Visitor Model
    
    Records site visitors.
    """
    
    report = models.ForeignKey(
        DailyReport,
        on_delete=models.CASCADE,
        related_name='visitors',
        help_text=_('Daily report this visitor belongs to')
    )
    
    visit_time = models.TimeField(
        help_text=_('Time of visit')
    )
    
    visitor_name = models.CharField(
        max_length=255,
        help_text=_('Name of the visitor')
    )
    
    representing = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Organization or company the visitor represents')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Daily Visitor')
        verbose_name_plural = _('Daily Visitors')
        ordering = ['report', 'visit_time']
        indexes = [
            models.Index(fields=['report']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - {self.visitor_name}"


# ==================== MONTHLY REPORT RELATED MODELS ====================

class FloorActivity(models.Model):
    """
    Floor Activity Model for Monthly Reports
    
    Tracks activities on specific floors.
    """
    
    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='floor_activities',
        help_text=_('Monthly report this activity belongs to')
    )
    
    floor = models.ForeignKey(
        ProjectFloor,
        on_delete=models.CASCADE,
        help_text=_('Floor where activity occurred')
    )
    
    activity_description = models.TextField(
        help_text=_('Description of activities on this floor')
    )
    
    completion_percentage = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text=_('Percentage of completion')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Floor Activity')
        verbose_name_plural = _('Floor Activities')
        ordering = ['report', 'floor']
        indexes = [
            models.Index(fields=['report', 'floor']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - Floor {self.floor.floor_number}"


class ExternalWork(models.Model):
    """
    External Work Model for Monthly Reports
    
    Tracks external and miscellaneous works.
    """
    
    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='external_works',
        help_text=_('Monthly report this work belongs to')
    )
    
    work_description = models.TextField(
        help_text=_('Description of external work')
    )
    
    completion_percentage = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text=_('Percentage of completion')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('External Work')
        verbose_name_plural = _('External Works')
        ordering = ['report']
        indexes = [
            models.Index(fields=['report']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - External Work"


class MaterialSupply(models.Model):
    """
    Material Supply Model for Monthly Reports

    Tracks materials delivered during the reporting period. `quantity` is
    cumulative -- same idea as OwnerReportPriceComparisonItem.quantity on
    the Owner Financial report (just without that model's price-tracking
    fields): it carries the running total to date, and grows only via the
    dedicated "Add Quantity" action (monthly_material_supply_add_quantity
    in api_views.py), not by editing this field directly.
    """

    MATERIAL_TYPE_CHOICES = (
        ('concrete_grade', _('Concrete Grade')),
        ('equipment', _('Equipment')),
        ('material', _('Other Material')),
    )

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='material_supplies',
        help_text=_('Monthly report this material belongs to')
    )

    material_type = models.CharField(
        max_length=20, choices=MATERIAL_TYPE_CHOICES, blank=True,
        help_text=_('Broad category, e.g. Concrete Grade / Equipment / Other Material')
    )

    material_description = models.CharField(
        max_length=255,
        help_text=_('Description of the material')
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text=_(
            'Cumulative quantity used to date for this material. Set once on creation; '
            'use the "Add Quantity" action to add just the new period\'s usage on top of it.'
        )
    )

    unit = models.CharField(
        max_length=50,
        help_text=_('Unit of measurement')
    )

    delivered_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_('Quantity delivered this period (EDGE "Materials Status" table)')
    )

    used_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_('Quantity used this period')
    )

    remaining_notes = models.CharField(
        max_length=255, blank=True,
        help_text=_('Remaining stock / notes (e.g. "Datasheet attached")')
    )

    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_(
            'Cost per unit, for the preliminary cost estimate. Real supplier '
            'quotes should replace any placeholder value entered here.'
        )
    )
    unit_price_is_estimated = models.BooleanField(
        default=False,
        help_text=_('True if unit_price is a random placeholder (no real quote yet), not an actual price')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Material Supply')
        verbose_name_plural = _('Material Supplies')
        ordering = ['report', 'material_description']
        indexes = [
            models.Index(fields=['report']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - {self.material_description}"

    def total_cost(self):
        if self.unit_price is None:
            return None
        return self.quantity * self.unit_price


class UpcomingWork(models.Model):
    """
    Upcoming Work Model for Monthly Reports
    
    Tracks planned activities for the next month.
    """
    
    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='upcoming_works',
        help_text=_('Monthly report this work belongs to')
    )
    
    work_description = models.TextField(
        help_text=_('Description of upcoming work')
    )
    
    planned_start_date = models.DateField(
        help_text=_('Planned start date for this work')
    )
    
    planned_end_date = models.DateField(
        help_text=_('Planned end date for this work')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Upcoming Work')
        verbose_name_plural = _('Upcoming Works')
        ordering = ['report', 'planned_start_date']
        indexes = [
            models.Index(fields=['report']),
        ]
    
    def __str__(self):
        return f"{self.report.report_number} - Upcoming Work"


class MonthlyProgressCategoryItem(models.Model):
    """
    One row of the EDGE monthly report's "Progress Summary" table for a
    broad work category (Civil/Structural, Finishing, MEP, Acoustic/
    Insulation, ...) -- planned vs. actual are free text (e.g. "In
    progress (Phase 3)", "Not started (0%)", "—") since they're
    qualitative narrative, not always a bare percentage. The table's
    "Overall Project Progress" and "Progress This Month" rows are NOT
    stored here -- they're computed on the fly from
    progress_models.calculate_project_progress() so they can never drift
    from the BOQ data.
    """

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='progress_category_items',
        help_text=_('Monthly report this progress row belongs to')
    )

    item_name = models.CharField(max_length=150, help_text=_('e.g. "Civil / Structural Works"'))
    planned_value = models.CharField(max_length=150, blank=True, help_text=_('e.g. "≈ 32.6%" or "—"'))
    actual_value = models.CharField(max_length=255, blank=True, help_text=_('e.g. "In progress (Phase 3)" or "Not started (0%)"'))
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Monthly Progress Category Item')
        verbose_name_plural = _('Monthly Progress Category Items')
        ordering = ['report', 'order', 'id']

    def __str__(self):
        return f"{self.report.report_number} - {self.item_name}"


class MonthlyKeyActivity(models.Model):
    """One row of "Key Activities Carried Out This Month" (EDGE monthly report, Section 4)."""

    STATUS_CHOICES = (
        ('completed', _('Completed')),
        ('in_progress', _('In Progress')),
        ('not_started', _('Not Started')),
        ('delayed', _('Delayed')),
    )

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='key_activities',
        help_text=_('Monthly report this activity belongs to')
    )

    activity = models.TextField(help_text=_('Activity / work item, e.g. "Columns & walls of the ground floor"'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    remarks = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Monthly Key Activity')
        verbose_name_plural = _('Monthly Key Activities')
        ordering = ['report', 'order', 'id']

    def __str__(self):
        return f"{self.report.report_number} - {self.activity[:50]}"


class MonthlyIssueRiskDelay(models.Model):
    """One row of "Issues, Risks & Delays" (EDGE monthly report, Section 8)."""

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='issues_risks_delays',
        help_text=_('Monthly report this issue/risk/delay belongs to')
    )

    description = models.TextField(help_text=_('Issue / risk / delay description'))
    impact = models.TextField(blank=True, help_text=_('Impact on schedule, cost, or quality'))
    mitigation = models.TextField(blank=True, help_text=_('Mitigation / action taken or planned'))
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Monthly Issue / Risk / Delay')
        verbose_name_plural = _('Monthly Issues / Risks / Delays')
        ordering = ['report', 'order', 'id']

    def __str__(self):
        return f"{self.report.report_number} - {self.description[:50]}"


class MonthlyReviewComment(models.Model):
    """
    One comment/response pair in the "Response to Comments" log the real
    EDGE report carries after the external supervision/consultant reviews
    a submitted period and sends back feedback (e.g. "Slab Reinforcement /
    Tendon Strands Photos", "Insulation Thickness - 11 cm vs. 6 cm") --
    the contractor's written response to each becomes part of the next
    revision (see MonthlyReport.revision_number/revision_note). Distinct
    from this app's own internal draft/submitted/approved workflow: this
    tracks the outside consultant's review, not this company's Engineering/
    General Manager sign-off.
    """

    STATUS_CHOICES = (
        ('open', _('Open')),
        ('resolved', _('Resolved')),
    )

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='review_comments',
        help_text=_('Monthly report this supervision comment belongs to')
    )

    reference = models.CharField(
        max_length=150, blank=True,
        help_text=_('Short topic/reference for the comment, e.g. "Photo-01" or "Insulation Thickness"')
    )
    comment_text = models.TextField(help_text=_("The supervision/consultant's comment"))
    response_text = models.TextField(blank=True, help_text=_("The contractor's response to the comment"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Monthly Review Comment')
        verbose_name_plural = _('Monthly Review Comments')
        ordering = ['report', 'order', 'id']

    def __str__(self):
        return f"{self.report.report_number} - {self.reference or self.comment_text[:50]}"


class MonthlyWorkForce(models.Model):
    """
    Work Force Model for Monthly Reports
    """
    CATEGORY_CHOICES = DailyWorkForce.CATEGORY_CHOICES  # reuse

    report = models.ForeignKey(
        MonthlyReport,
        on_delete=models.CASCADE,
        related_name='workforce',
        help_text=_('Monthly report this workforce belongs to')
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        help_text=_('Category of workforce')
    )

    designation = models.CharField(
        max_length=255,
        help_text=_('Job designation or title')
    )

    count = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text=_('Number of workers in this category')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Monthly Work Force')
        verbose_name_plural = _('Monthly Work Forces')
        ordering = ['report', 'category']
        indexes = [models.Index(fields=['report', 'category'])]

    def __str__(self):
        return f"{self.report.report_number} - {self.designation} ({self.count})"


class MonthlyEquipment(models.Model):
    report = models.ForeignKey(MonthlyReport, on_delete=models.CASCADE, related_name='equipment')
    equipment_name = models.CharField(max_length=150)
    total_hours = models.DecimalField(max_digits=6, decimal_places=1)
    remarks = models.CharField(max_length=255, blank=True)

class MonthlyActivity(models.Model):
    report = models.ForeignKey(MonthlyReport, on_delete=models.CASCADE, related_name='activities')
    description = models.TextField()
    completion_percentage = models.PositiveIntegerField()

class ReportAttachment(models.Model):
    """
    Report Attachment Model
    
    Handles attachments (photos, documents) for both daily and monthly reports.
    Uses generic relations to support both report types.
    """
    
    ATTACHMENT_TYPE_CHOICES = [
        ('photo', _('Photo')),
        ('document', _('Document')),
        ('video', _('Video')),
        ('other', _('Other')),
    ]
    
    # Store report type and ID to support both Daily and Monthly reports
    report_type = models.CharField(
        max_length=10,
        choices=[('daily', _('Daily')), ('monthly', _('Monthly'))],
        help_text=_('Type of report')
    )
    
    report_id = models.IntegerField(
        help_text=_('ID of the report')
    )
    
    attachment_type = models.CharField(
        max_length=20,
        choices=ATTACHMENT_TYPE_CHOICES,
        default='photo',
        help_text=_('Type of attachment')
    )
    
    file = models.FileField(
        upload_to='report_attachments/%Y/%m/%d/',
        help_text=_('Attached file')
    )
    
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Description of the attachment')
    )
    
    uploaded_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        help_text=_('User who uploaded the file')
    )

    location = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Location on site where this attachment was captured')
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text=_('Display order within the report\'s photo log (Photo 01, 02, ...)')
    )

    activity = models.ForeignKey(
        'DailyReportActivityProgress',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attachments',
        help_text=_('Daily activity this attachment documents, if any')
    )

    site_event = models.ForeignKey(
        'SiteEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attachments',
        help_text=_('Site event (delay/NCR/HSE/...) this attachment documents, if any')
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Report Attachment')
        verbose_name_plural = _('Report Attachments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type', 'report_id']),
        ]
    
    def __str__(self):
        return f"{self.report_type.upper()} - {self.description or 'Attachment'}"


# ==================== OTHER MODEL FILES ====================
# These model classes live in separate files for readability, but MUST be
# imported here so Django's app registry (and `makemigrations`) picks them
# up -- a module that's never imported never gets its models registered.
#
# NOTE: master_data_models and email_models already existed as separate
# files before this change but were never imported anywhere in the app,
# so they had no migrations and their tables never existed in the
# database despite having full model/admin code. Wiring them in here
# fixes that alongside adding the new progress-tracking models.

from .master_data_models import (  # noqa: E402,F401
    WorkforceCategory,
    LaborClassification,
    EquipmentMaster,
    ReportMaterialItem,
    DailyReportWorkforceEntry,
    DailyReportEquipmentEntry,
    DailyReportMaterialEntry,
)

from .email_models import (  # noqa: E402,F401
    EmailReminder,
    EmailLog,
    ReminderSchedule,
    ReminderTemplate,
)

from .progress_models import (  # noqa: E402,F401
    ProjectPhase,
    ProjectPhaseSubItem,
    ProjectPhaseProgressEntry,
    ProjectMilestone,
    ProjectPhasePhoto,
)

from .schedule_models import (  # noqa: E402,F401
    ScheduleTask,
    PhaseScheduleLink,
)

from .site_event_models import (  # noqa: E402,F401
    SiteEvent,
)

from .daily_detail_models import (  # noqa: E402,F401
    DailyReportWorkerAttendance,
    DailyReportCrew,
    DailyReportActivityProgress,
    DailyReportQAQC,
    DailyReportNextDayPlan,
)

from .owner_financial_models import (  # noqa: E402,F401
    OwnerFinancialReport,
    OwnerReportPriceComparisonItem,
    OwnerReportPhaseUpdate,
)
