"""
Site Events Log (Delay / Site Instruction / RFI / NCR / HSE Event)

This is the shared log referenced by:
 - Daily Site Report, section "5. SITE EVENTS / INSTRUCTIONS / DELAYS"
 - Monthly report, section "8. Issues, Risks & Delays" (a rollup of the
   period's events)
 - Monthly HSE KPIs (counts of HSE-type events / near-misses)

A SiteEvent can be raised standalone against a project, or linked to the
DailyReport it was first logged in. Monthly reports read events in their
reporting_period_from/to window rather than duplicating the data.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser
from projects.models import Project


class SiteEvent(models.Model):

    EVENT_TYPE_CHOICES = (
        ('delay', _('Delay')),
        ('site_instruction', _('Site Instruction (SI)')),
        ('rfi', _('RFI')),
        ('ncr', _('NCR')),
        ('hse_incident', _('HSE Incident')),
        ('near_miss', _('Near Miss')),
        ('other', _('Other')),
    )

    STATUS_CHOICES = (
        ('open', _('Open')),
        ('in_progress', _('In Progress')),
        ('closed', _('Closed')),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='site_events',
        help_text=_('Associated project')
    )

    daily_report = models.ForeignKey(
        'DailyReport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='site_events',
        help_text=_('Daily report this event was first logged in, if any')
    )

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        help_text=_('Type of event')
    )

    reference = models.CharField(
        max_length=50,
        blank=True,
        help_text=_('External reference number, e.g. NCR-014, RFI-022')
    )

    event_date = models.DateField(
        default=timezone.localdate,
        help_text=_('Date the event occurred / was raised')
    )

    description = models.TextField(
        help_text=_('Description of the issue / instruction / delay')
    )

    required_action = models.TextField(
        blank=True,
        help_text=_('Action required to resolve this event')
    )

    responsible_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_site_events',
        help_text=_('Internal user responsible for closing this out')
    )

    responsible_party = models.CharField(
        max_length=150,
        blank=True,
        help_text=_('External party responsible, if not an internal user (consultant, subcontractor, etc.)')
    )

    target_date = models.DateField(
        null=True,
        blank=True,
        help_text=_('Target date for closing this event')
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open',
    )

    time_impact_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Schedule time impact in hours, if any')
    )

    remarks = models.TextField(blank=True)

    closed_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_site_events',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Site Event')
        verbose_name_plural = _('Site Events')
        ordering = ['-event_date', '-created_at']
        indexes = [
            models.Index(fields=['project', 'event_type']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['event_date']),
        ]

    def __str__(self):
        ref = self.reference or f"#{self.pk}"
        return f"{self.get_event_type_display()} {ref} - {self.project.project_symbol}"

    def save(self, *args, **kwargs):
        if self.status == 'closed' and not self.closed_date:
            self.closed_date = timezone.localdate()
        super().save(*args, **kwargs)

    @classmethod
    def for_period(cls, project, start_date, end_date):
        """Events raised within [start_date, end_date], for monthly rollups."""
        return cls.objects.filter(
            project=project,
            event_date__gte=start_date,
            event_date__lte=end_date,
        )

    @classmethod
    def hse_summary_for_period(cls, project, start_date, end_date):
        """
        Quick counts for the monthly HSE KPI table:
        Lost-Time Incidents, Near Misses, open/closed corrective actions.
        Note: "Lost Time Incident" vs. a general HSE incident isn't
        distinguished at the model level yet -- all 'hse_incident' events
        are counted as incidents; refine with a severity field later if
        the business needs LTI reported separately.
        """
        qs = cls.for_period(project, start_date, end_date)
        return {
            'hse_incidents': qs.filter(event_type='hse_incident').count(),
            'near_misses': qs.filter(event_type='near_miss').count(),
            'corrective_actions_open': qs.filter(
                event_type__in=['ncr', 'hse_incident', 'near_miss'],
                status__in=['open', 'in_progress'],
            ).count(),
            'corrective_actions_closed': qs.filter(
                event_type__in=['ncr', 'hse_incident', 'near_miss'],
                status='closed',
            ).count(),
        }
