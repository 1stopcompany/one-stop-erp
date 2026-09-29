"""
Django Admin Configuration for Email Reminders

This module configures the Django admin interface for managing email reminders.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .email_models import EmailReminder, EmailLog, ReminderSchedule, ReminderTemplate


@admin.register(EmailReminder)
class EmailReminderAdmin(admin.ModelAdmin):
    """Admin interface for Email Reminders"""
    
    list_display = (
        'name',
        'reminder_type',
        'frequency',
        'send_time',
        'is_active',
        'created_at',
    )
    
    list_filter = (
        'is_active',
        'reminder_type',
        'frequency',
        'send_time',
        'created_at',
    )
    
    search_fields = ('name', 'description')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_active')
        }),
        (_('Reminder Settings'), {
            'fields': (
                'reminder_type',
                'frequency',
                'send_time',
                'custom_time',
            )
        }),
        (_('Target Settings'), {
            'fields': (
                'target_engineers',
                'target_projects',
            ),
            'description': _('Leave empty to target all engineers/projects')
        }),
        (_('Days of Week'), {
            'fields': (
                'monday',
                'tuesday',
                'wednesday',
                'thursday',
                'friday',
                'saturday',
                'sunday',
            ),
            'description': _('Select days for weekly/bi-weekly reminders')
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    filter_horizontal = ('target_engineers', 'target_projects')
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Admin interface for Email Logs"""
    
    list_display = (
        'subject',
        'recipient',
        'status',
        'sent_at',
        'opened_at',
    )
    
    list_filter = (
        'status',
        'sent_at',
        'opened_at',
        'reminder',
    )
    
    search_fields = (
        'subject',
        'recipient__email',
        'recipient__username',
    )
    
    fieldsets = (
        (_('Email Information'), {
            'fields': (
                'reminder',
                'recipient',
                'subject',
                'body',
            )
        }),
        (_('Status'), {
            'fields': (
                'status',
                'error_message',
            )
        }),
        (_('Timestamps'), {
            'fields': (
                'sent_at',
                'opened_at',
                'clicked_at',
            )
        }),
        (_('Metadata'), {
            'fields': ('email_id',)
        }),
    )
    
    readonly_fields = (
        'sent_at',
        'opened_at',
        'clicked_at',
        'reminder',
        'recipient',
        'subject',
        'body',
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReminderSchedule)
class ReminderScheduleAdmin(admin.ModelAdmin):
    """Admin interface for Reminder Schedules"""
    
    list_display = (
        'reminder',
        'engineer',
        'last_sent',
        'next_send',
        'send_count',
        'is_active',
    )
    
    list_filter = (
        'is_active',
        'reminder',
        'last_sent',
        'next_send',
    )
    
    search_fields = (
        'reminder__name',
        'engineer__username',
        'engineer__email',
    )
    
    fieldsets = (
        (_('Schedule Information'), {
            'fields': (
                'reminder',
                'engineer',
                'is_active',
            )
        }),
        (_('Send History'), {
            'fields': (
                'last_sent',
                'next_send',
                'send_count',
            )
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_sent', 'send_count')


@admin.register(ReminderTemplate)
class ReminderTemplateAdmin(admin.ModelAdmin):
    """Admin interface for Reminder Templates"""
    
    list_display = (
        'name',
        'template_type',
        'is_active',
        'created_at',
    )
    
    list_filter = (
        'is_active',
        'template_type',
        'created_at',
    )
    
    search_fields = ('name', 'subject')
    
    fieldsets = (
        (_('Template Information'), {
            'fields': (
                'name',
                'template_type',
                'is_active',
            )
        }),
        (_('Email Content'), {
            'fields': (
                'subject',
                'body_html',
                'body_text',
            )
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
