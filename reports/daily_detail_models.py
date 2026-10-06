"""
Daily Site Report - Detail Models

This module fills the gaps between the original DailyReport model
(reports/models.py) and the real daily site-report template it needs to
support:

    - DailyReportWorkerAttendance: named-worker attendance (in/out/break/
      overtime/total hours per individual worker), instead of the
      category-level headcount already covered by DailyWorkForce /
      DailyReportWorkforceEntry.
    - DailyReportActivityProgress: activity rows with today's/cumulative
      quantity and completion %, linked to the ProjectPhaseSubItem BOQ
      hierarchy from progress_models.py so daily entries feed the shared
      progress-tracking foundation automatically.
    - DailyReportQAQC: the QA/QC & HSE header block (inspection status,
      Toolbox Talk, incident/near-miss flags, PPE compliance, NCR
      reference).
    - DailyReportNextDayPlan: the "next day plan" table.

The daily event/delay log itself does NOT get a new model here -- it's
already covered by site_event_models.SiteEvent, which has a `daily_report`
FK. This module only adds what SiteEvent doesn't already provide.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

from .master_data_models import LaborClassification
from .progress_models import ProjectPhaseSubItem, ProjectPhaseProgressEntry
from .site_event_models import SiteEvent


def local_day_range_utc(day):
    """
    (start, end) aware-UTC datetimes spanning local midnight-to-midnight
    for `day`, for filtering a timestamp field by "this calendar day"
    with a plain >=/< range instead of a `__date` lookup -- see
    DailyReportWorkerAttendance.has_gps_record()'s docstring for why
    `__date` isn't safe to use against this project's MySQL server.
    """
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    end = start + timedelta(days=1)
    return start, end


class DailyReportCrew(models.Model):
    """
    A named group of workers on this daily report, for a project big enough to have several
    crews working at once (e.g. a masonry crew and a plumbing crew, both logged the same day).
    A crew is tied to the one activity it's executing and, if it's a subcontracted crew, to the
    subcontractor agreement it works under -- set once on the crew rather than repeated on every
    worker under it. Workers not part of any named crew (e.g. an HR staff member marking their
    own presence) simply leave DailyReportWorkerAttendance.crew unset and keep their own
    contractor_name/activity_location as before.
    """

    report = models.ForeignKey(
        'DailyReport', on_delete=models.CASCADE, related_name='crews',
        help_text=_('Daily report this crew belongs to')
    )

    name = models.CharField(max_length=100, help_text=_('e.g. "Masonry Crew A", "Crew 1"'))

    activity = models.ForeignKey(
        'DailyReportActivityProgress', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='crews',
        help_text=_("Which of this report's logged activities this crew is executing")
    )

    agreement = models.ForeignKey(
        'subcontractors.SubcontractorAgreement', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='daily_crews',
        help_text=_('Subcontractor agreement this crew works under, if it is a subcontracted crew')
    )

    contractor_name = models.CharField(
        max_length=150, blank=True,
        help_text=_('Company this crew belongs to (e.g. "One Stop" for an in-house crew); '
                    'auto-filled from the agreement above when one is set')
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['report', 'name']
        verbose_name = _('Daily Report Crew')
        verbose_name_plural = _('Daily Report Crews')

    def save(self, *args, **kwargs):
        if self.agreement_id:
            self.contractor_name = self.agreement.vendor.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.report.report_number})'


class ProjectSub(models.Model):
    """
    A named sub-group (متفرقة) inside a project, chosen from this list when the site engineer records which odd job a
    day-labor worker did. The wages sheets and the Manual Entry tab group the project's workers by it.
    """

    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='subs')
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, help_text=_('Inactive subs are no longer offered to the site engineer'))
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['project', 'order', 'name']
        unique_together = [('project', 'name')]
        verbose_name = _('Project sub (متفرقة)')
        verbose_name_plural = _('Project subs (متفرقات)')

    def __str__(self):
        return f"{self.project.project_symbol} - {self.name}"


class DailyReportWorkerAttendance(models.Model):
    """
    Named-worker attendance for a single daily report.

    `worker_name` is the source of truth since most site labor (day
    laborers, subcontractor crews) has no `timesheets.Employee` record;
    `employee` is an optional convenience link for workers who ARE
    registered HR employees.
    """

    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='worker_attendance',
        help_text=_('Daily report this attendance entry belongs to')
    )

    worker_name = models.CharField(
        max_length=255,
        help_text=_('Worker full name, as written on site')
    )

    sub_name = models.CharField(
        max_length=120, blank=True,
        help_text=_('متفرقة -- which sub-group (odd job) of the project this day-labor entry belongs to; blank = the project itself')
    )

    labor_classification = models.ForeignKey(
        LaborClassification,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_('Labor classification, for category-level rollups')
    )

    employee = models.ForeignKey(
        'timesheets.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_report_attendance',
        help_text=_('Linked HR employee record, if this worker has one')
    )

    daily_worker = models.ForeignKey(
        'timesheets.DailyWorker',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_entries',
        help_text=_('Link to the shared day-labor roster, so this worker\'s hours across every '
                     'project they worked this month can be aggregated for payroll')
    )

    crew = models.ForeignKey(
        'DailyReportCrew',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workers',
        help_text=_('Crew this worker is part of, on a project with more than one crew working '
                     'the same day -- when set, contractor_name/activity_location are taken from '
                     'the crew rather than entered per worker')
    )

    contractor_name = models.CharField(
        max_length=150, blank=True,
        help_text=_('Subcontractor/company this worker belongs to (e.g. "One Stop", a named subcontractor); '
                    'auto-filled from crew when this worker is part of one')
    )

    activity_location = models.CharField(
        max_length=255, blank=True,
        help_text=_('What/where this worker worked on today')
    )

    time_in = models.TimeField(null=True, blank=True, help_text=_('Check-in time'))
    time_out = models.TimeField(null=True, blank=True, help_text=_('Check-out time'))

    break_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Unpaid break time, in hours')
    )

    overtime_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Overtime hours, added on top of time_in/time_out')
    )

    total_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        help_text=_('Computed: (time_out - time_in) - break_hours + overtime_hours')
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Daily Report Worker Attendance')
        verbose_name_plural = _('Daily Report Worker Attendance')
        ordering = ['report', 'worker_name']
        indexes = [
            models.Index(fields=['report']),
        ]

    def __str__(self):
        return f"{self.report.report_number} - {self.worker_name}"

    def has_gps_record(self):
        """
        Whether this row's linked HR employee has a real GPS check-in/out
        (timesheets.CheckInLocation) on this report's date -- drives the
        "GPS verified" badge next to a worker's name; see
        api_views.pull_gps_daily_worker_attendance for actually pulling
        those times into time_in/time_out.

        Filters by an explicit UTC datetime range (local midnight to
        midnight, converted up front in Python) rather than a `__date`
        lookup: Django compiles `timestamp__date=...` to
        `DATE(CONVERT_TZ(timestamp, 'UTC', '<TIME_ZONE>'))` on MySQL,
        which silently returns NULL (matching nothing, with no error) if
        the server's mysql.time_zone_name tables were never loaded via
        mysql_tzinfo_to_sql -- a common out-of-the-box MySQL state. A
        plain >=/< range on the stored UTC value needs no server-side
        named-timezone lookup at all, so it works regardless.
        """
        if not self.employee_id:
            return False
        from timesheets.models import CheckInLocation
        start, end = local_day_range_utc(self.report.report_date)
        return CheckInLocation.objects.filter(
            employee_id=self.employee_id, timestamp__gte=start, timestamp__lt=end,
        ).exists()

    def save(self, *args, **kwargs):
        # A crew groups several workers under one activity/contractor set once on the crew --
        # keep contractor_name/activity_location on the row itself in sync so every existing
        # display/PDF that reads them directly (rather than following crew) still works.
        if self.crew_id:
            if self.crew.contractor_name:
                self.contractor_name = self.crew.contractor_name
            if self.crew.activity_id:
                self.activity_location = self.crew.activity.activity_description

        # Auto-fill total_hours from time_in/time_out only when it hasn't
        # been set explicitly (either left at the default 0, or the times
        # are identical -- real site sheets use e.g. 00:00/00:00 as a
        # placeholder for "not individually timed" and enter total_hours
        # by hand instead). This avoids silently clobbering a manual
        # override on every save.
        if self.time_in and self.time_out and self.time_in != self.time_out and not self.total_hours:
            anchor = timezone.localdate()
            start = datetime.combine(anchor, self.time_in)
            end = datetime.combine(anchor, self.time_out)
            if end < start:
                # Overnight shift (e.g. night crew ending after midnight).
                end += timedelta(days=1)
            worked = Decimal((end - start).total_seconds()) / Decimal(3600)
            worked -= self.break_hours or Decimal('0')
            worked += self.overtime_hours or Decimal('0')
            self.total_hours = max(worked, Decimal('0'))
        super().save(*args, **kwargs)


class DailyReportActivityProgress(models.Model):
    """
    Activity row ("1. DAILY WORKS / PROGRESS" on the site report) with
    today's/total/cumulative quantity and completion %. `sub_item` is an
    OPTIONAL link into the ProjectPhaseSubItem BOQ hierarchy: when set,
    this row also feeds the shared progress-tracking foundation
    (progress_models.calculate_project_progress) automatically. It's
    optional because day-to-day field activities are often more granular
    than the ~40 BOQ sub-items tracked for the monthly/owner reports, so
    not every row will map cleanly to one.
    """

    STATUS_CHOICES = (
        ('not_started', _('Not Started')),
        ('in_progress', _('In Progress')),
        ('completed', _('Completed')),
        ('delayed', _('Delayed')),
        ('on_hold', _('On Hold')),
    )

    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='activity_progress_entries',
        help_text=_('Daily report this activity belongs to')
    )

    sub_item = models.ForeignKey(
        ProjectPhaseSubItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_activity_entries',
        help_text=_('BOQ sub-item this activity contributes to, if it maps to one')
    )

    activity_description = models.TextField(help_text=_('Description of the work/activity'))
    location = models.CharField(max_length=255, blank=True, help_text=_('Location / floor / area on site'))
    unit = models.CharField(max_length=50, blank=True, help_text=_('Unit of measurement (m3, m2, ton, ...)'))

    total_quantity = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Total scope quantity for this activity')
    )

    quantity_today = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Quantity executed today')
    )

    quantity_cumulative = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text=_('Cumulative quantity executed to date')
    )

    completion_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text=_('Cumulative % complete of this activity, as of this report')
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')

    reference_notes = models.CharField(
        max_length=255, blank=True,
        help_text=_('Work reference / remarks (e.g. responsible crew, drawing ref.)')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Daily Report Activity Progress')
        verbose_name_plural = _('Daily Report Activity Progress Entries')
        ordering = ['report', 'id']
        indexes = [
            models.Index(fields=['report']),
            models.Index(fields=['sub_item']),
        ]

    def __str__(self):
        return f"{self.report.report_number} - {self.activity_description[:50]} ({self.completion_percentage}%)"

    @staticmethod
    def cumulative_before(project, activity_description, report_date):
        """
        Sum of quantity_today across every earlier report (by date) on this project that logged
        this same activity (exact activity_description match) -- the running total this activity
        had already reached before the entry being added now. Used to auto-fill
        quantity_cumulative on a new entry (see api_views.add_daily_activity_progress) instead of
        retyping a running total by hand on every report; summed fresh from the raw quantity_today
        history each time rather than trusting the previous row's own quantity_cumulative, so it
        self-corrects even if an earlier row's cumulative was ever hand-edited to something off.
        """
        return DailyReportActivityProgress.objects.filter(
            report__project=project,
            activity_description=activity_description,
            report__report_date__lt=report_date,
        ).aggregate(total=models.Sum('quantity_today'))['total'] or Decimal('0')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep the shared progress-tracking foundation (Stage 4) in sync
        # whenever this activity is linked to a BOQ sub-item: one
        # ProjectPhaseProgressEntry per (sub_item, daily_report).
        if self.sub_item_id:
            ProjectPhaseProgressEntry.objects.update_or_create(
                sub_item=self.sub_item,
                daily_report=self.report,
                defaults={
                    'report_date': self.report.report_date,
                    'execution_percentage': self.completion_percentage,
                },
            )

    def delete(self, *args, **kwargs):
        if self.sub_item_id:
            ProjectPhaseProgressEntry.objects.filter(
                sub_item=self.sub_item, daily_report=self.report,
            ).delete()
        super().delete(*args, **kwargs)


class DailyReportQAQC(models.Model):
    """QA/QC & HSE header block -- one per daily report."""

    INSPECTION_STATUS_CHOICES = (
        ('passed', _('Passed')),
        ('failed', _('Failed')),
        ('pending', _('Pending')),
        ('not_applicable', _('Not Applicable')),
    )

    report = models.OneToOneField(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='qaqc',
        help_text=_('Daily report this QA/QC & HSE section belongs to')
    )

    inspection_status = models.CharField(
        max_length=20,
        choices=INSPECTION_STATUS_CHOICES,
        default='not_applicable',
        help_text=_('Result of today\'s QA/QC inspection, if any')
    )

    ir_mir_test_reference = models.CharField(
        max_length=100, blank=True,
        help_text=_('Inspection Request / Material Inspection Request / Test reference number')
    )

    toolbox_talk_conducted = models.BooleanField(default=False)
    toolbox_talk_topic = models.CharField(max_length=255, blank=True)

    incident_occurred = models.BooleanField(default=False, help_text=_('An HSE incident occurred today'))
    near_miss_occurred = models.BooleanField(default=False, help_text=_('A near-miss occurred today'))

    ppe_site_cleanliness_status = models.CharField(
        max_length=100, blank=True,
        help_text=_('Free-text PPE compliance / site cleanliness status (e.g. "OK", "Sound")')
    )

    ncr_hse_reference = models.CharField(
        max_length=100, blank=True,
        help_text=_('Raw NCR / HSE reference text, if not yet logged as a formal site event')
    )

    related_site_event = models.ForeignKey(
        SiteEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='qaqc_references',
        limit_choices_to={'event_type__in': ['ncr', 'hse_incident', 'near_miss']},
        help_text=_('NCR / HSE event this section refers to, if logged in the site events log')
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Daily Report QA/QC & HSE')
        verbose_name_plural = _('Daily Report QA/QC & HSE Sections')

    def __str__(self):
        return f"{self.report.report_number} - QA/QC & HSE"

    @classmethod
    def toolbox_talks_conducted_for_period(cls, project, start_date, end_date):
        """Count of daily reports with a Toolbox Talk logged in [start_date, end_date] (EDGE monthly HSE KPI)."""
        return cls.objects.filter(
            report__project=project,
            report__report_date__gte=start_date,
            report__report_date__lte=end_date,
            toolbox_talk_conducted=True,
        ).count()


class DailyReportNextDayPlan(models.Model):
    """One planned work-item row in the "6. NEXT DAY PLAN / READINESS" table."""

    PRIORITY_CHOICES = (
        ('high', _('High')),
        ('medium', _('Medium')),
        ('low', _('Low')),
    )

    READINESS_CHOICES = (
        ('ready', _('Ready')),
        ('pending', _('Pending')),
        ('not_ready', _('Not Ready')),
    )

    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='next_day_plan',
        help_text=_('Daily report this plan row belongs to')
    )

    sub_item = models.ForeignKey(
        ProjectPhaseSubItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_day_plan_entries',
        help_text=_('BOQ sub-item this planned work maps to, if known')
    )

    planned_activity = models.TextField(help_text=_('Description of the planned activity'))
    location = models.CharField(max_length=255, blank=True)

    manpower_required = models.PositiveIntegerField(
        null=True, blank=True, help_text=_('Number of workers needed')
    )

    resources_required = models.TextField(
        blank=True, help_text=_('Materials / equipment required')
    )

    requirement_notes = models.CharField(
        max_length=255, blank=True,
        help_text=_('Requirement or approval needed before this work can proceed')
    )

    responsible_party = models.CharField(
        max_length=150, blank=True,
        help_text=_('Crew / subcontractor responsible for this work')
    )

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, blank=True)
    readiness = models.CharField(max_length=10, choices=READINESS_CHOICES, blank=True)

    remarks = models.TextField(blank=True)

    order = models.PositiveIntegerField(default=0, help_text=_('Display order within the table'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Daily Report Next-Day Plan Item')
        verbose_name_plural = _('Daily Report Next-Day Plan Items')
        ordering = ['report', 'order']
        indexes = [
            models.Index(fields=['report']),
        ]

    def __str__(self):
        return f"{self.report.report_number} - {self.planned_activity[:50]}"
