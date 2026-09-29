"""
Email Notification Models

This module contains models for managing email reminders and notifications
for engineers to fill their daily and monthly reports.

Models:
    - EmailReminder: Stores email reminder configurations
    - EmailLog: Logs all sent emails for audit purposes
    - ReminderSchedule: Manages reminder schedules
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from accounts.models import CustomUser
from projects.models import Project
from datetime import datetime, timedelta


class EmailReminder(models.Model):
    """
    Email Reminder Configuration
    
    Stores settings for automated email reminders to engineers
    to fill their daily and monthly reports.
    """
    
    REMINDER_TYPE_CHOICES = (
        ('daily', _('Daily Report')),
        ('monthly', _('Monthly Report')),
        ('both', _('Both Daily and Monthly')),
    )
    
    FREQUENCY_CHOICES = (
        ('daily', _('Every Day')),
        ('weekly', _('Every Week')),
        ('bi_weekly', _('Every Two Weeks')),
        ('monthly', _('Every Month')),
        ('custom', _('Custom')),
    )
    
    TIME_CHOICES = (
        ('morning', _('Morning (8:00 AM)')),
        ('afternoon', _('Afternoon (1:00 PM)')),
        ('evening', _('Evening (5:00 PM)')),
        ('end_of_day', _('End of Day (6:00 PM)')),
        ('custom', _('Custom Time')),
    )
    
    # Basic Information
    name = models.CharField(
        max_length=100,
        help_text=_('Name of the reminder configuration')
    )
    description = models.TextField(
        blank=True,
        help_text=_('Description of the reminder')
    )
    
    # Reminder Settings
    reminder_type = models.CharField(
        max_length=20,
        choices=REMINDER_TYPE_CHOICES,
        default='daily',
        help_text=_('Type of report to remind about')
    )
    
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily',
        help_text=_('How often to send reminders')
    )
    
    send_time = models.CharField(
        max_length=20,
        choices=TIME_CHOICES,
        default='evening',
        help_text=_('What time to send reminders')
    )
    
    custom_time = models.TimeField(
        null=True,
        blank=True,
        help_text=_('Custom time to send reminders (if Custom Time selected)')
    )
    
    # Target Settings
    target_engineers = models.ManyToManyField(
        CustomUser,
        blank=True,
        related_name='email_reminders',
        help_text=_('Engineers to send reminders to (leave empty for all)')
    )
    
    target_projects = models.ManyToManyField(
        Project,
        blank=True,
        related_name='email_reminders',
        help_text=_('Projects to send reminders for (leave empty for all)')
    )
    
    # Days of Week (for weekly/bi-weekly)
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text=_('Enable or disable this reminder')
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_reminders'
    )
    
    class Meta:
        verbose_name = _('Email Reminder')
        verbose_name_plural = _('Email Reminders')
        ordering = ['-created_at']
    
    def __str__(self):
        return f'{self.name} - {self.get_reminder_type_display()}'
    
    def get_days_of_week(self):
        """Get selected days of week"""
        days = []
        if self.monday:
            days.append('Monday')
        if self.tuesday:
            days.append('Tuesday')
        if self.wednesday:
            days.append('Wednesday')
        if self.thursday:
            days.append('Thursday')
        if self.friday:
            days.append('Friday')
        if self.saturday:
            days.append('Saturday')
        if self.sunday:
            days.append('Sunday')
        return days
    
    def get_send_time(self):
        """Get the time to send reminders"""
        if self.send_time == 'custom' and self.custom_time:
            return self.custom_time
        
        time_map = {
            'morning': '08:00',
            'afternoon': '13:00',
            'evening': '17:00',
            'end_of_day': '18:00',
        }
        return time_map.get(self.send_time, '17:00')
    
    def should_send_today(self):
        """Check if reminder should be sent today"""
        if not self.is_active:
            return False
        
        today = timezone.now().weekday()  # 0=Monday, 6=Sunday
        days_map = [self.monday, self.tuesday, self.wednesday, self.thursday, 
                    self.friday, self.saturday, self.sunday]
        
        if self.frequency in ['weekly', 'bi_weekly']:
            return days_map[today]
        
        return True


class EmailLog(models.Model):
    """
    Email Log
    
    Logs all sent emails for audit and tracking purposes.
    """
    
    STATUS_CHOICES = (
        ('sent', _('Sent')),
        ('failed', _('Failed')),
        ('bounced', _('Bounced')),
        ('opened', _('Opened')),
        ('clicked', _('Clicked')),
    )
    
    # Email Information
    reminder = models.ForeignKey(
        EmailReminder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='email_logs',
        help_text=_('The scheduled reminder config this email came from, if any -- an ad-hoc check '
                    '(e.g. check_overdue_daily_reports) logs its emails with this left unset')
    )
    
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='received_emails'
    )
    
    subject = models.CharField(max_length=200)
    body = models.TextField()
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='sent'
    )
    
    error_message = models.TextField(
        blank=True,
        help_text=_('Error message if email failed to send')
    )
    
    # Timestamps
    sent_at = models.DateTimeField(auto_now_add=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    email_id = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Email service provider ID')
    )
    
    class Meta:
        verbose_name = _('Email Log')
        verbose_name_plural = _('Email Logs')
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['recipient', '-sent_at']),
            models.Index(fields=['status', '-sent_at']),
        ]
    
    def __str__(self):
        return f'{self.subject} - {self.recipient.email} ({self.status})'
    
    def mark_as_opened(self):
        """Mark email as opened"""
        if not self.opened_at:
            self.opened_at = timezone.now()
            self.status = 'opened'
            self.save()
    
    def mark_as_clicked(self):
        """Mark email as clicked"""
        if not self.clicked_at:
            self.clicked_at = timezone.now()
            self.status = 'clicked'
            self.save()


class ReminderSchedule(models.Model):
    """
    Reminder Schedule
    
    Tracks the schedule of when reminders were sent to each engineer.
    Useful for preventing duplicate sends and tracking reminder history.
    """
    
    reminder = models.ForeignKey(
        EmailReminder,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    
    engineer = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='reminder_schedules'
    )
    
    last_sent = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Last time reminder was sent to this engineer')
    )
    
    next_send = models.DateTimeField(
        help_text=_('Next scheduled time to send reminder')
    )
    
    send_count = models.IntegerField(
        default=0,
        help_text=_('Number of times reminder has been sent')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this schedule is active')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Reminder Schedule')
        verbose_name_plural = _('Reminder Schedules')
        ordering = ['next_send']
        unique_together = ['reminder', 'engineer']
        indexes = [
            models.Index(fields=['next_send', 'is_active']),
            models.Index(fields=['engineer', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.reminder.name} - {self.engineer.username}'
    
    def update_next_send(self):
        """Calculate and update next send time"""
        from datetime import timedelta
        
        if self.reminder.frequency == 'daily':
            self.next_send = timezone.now() + timedelta(days=1)
        elif self.reminder.frequency == 'weekly':
            self.next_send = timezone.now() + timedelta(weeks=1)
        elif self.reminder.frequency == 'bi_weekly':
            self.next_send = timezone.now() + timedelta(weeks=2)
        elif self.reminder.frequency == 'monthly':
            self.next_send = timezone.now() + timedelta(days=30)
        
        self.save()


class ReminderTemplate(models.Model):
    """
    Email Template for Reminders
    
    Stores email templates for different reminder types.
    """
    
    TEMPLATE_TYPE_CHOICES = (
        ('daily', _('Daily Report Reminder')),
        ('monthly', _('Monthly Report Reminder')),
        ('overdue', _('Overdue Report Reminder')),
        ('welcome', _('Welcome Email')),
    )
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(
        max_length=20,
        choices=TEMPLATE_TYPE_CHOICES
    )
    
    subject = models.CharField(
        max_length=200,
        help_text=_('Email subject line')
    )
    
    body_html = models.TextField(
        help_text=_('HTML email body (use {{variables}} for placeholders)')
    )
    
    body_text = models.TextField(
        blank=True,
        help_text=_('Plain text email body (optional)')
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Reminder Template')
        verbose_name_plural = _('Reminder Templates')
        unique_together = ['template_type', 'is_active']
    
    def __str__(self):
        return f'{self.name} - {self.get_template_type_display()}'
    
    def render(self, context):
        """Render template with context variables"""
        from django.template import Template, Context
        
        template = Template(self.body_html)
        return template.render(Context(context))
