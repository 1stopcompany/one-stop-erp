"""
Django Admin Configuration for Daily Report Detail Models

Registers DailyReportWorkerAttendance, DailyReportActivityProgress,
DailyReportQAQC, DailyReportNextDayPlan (daily_detail_models.py), plus a
SiteEvent inline scoped to DailyReport (SiteEvent itself is already
registered as a standalone admin page in progress_admin.py).
"""

from django.contrib import admin

from .daily_detail_models import (
    DailyReportWorkerAttendance,
    DailyReportCrew,
    DailyReportActivityProgress,
    DailyReportQAQC,
    DailyReportNextDayPlan,
)
from .site_event_models import SiteEvent


# ==================== INLINES (used on DailyReportAdmin, see admin.py) ====================

class DailyReportWorkerAttendanceInline(admin.TabularInline):
    model = DailyReportWorkerAttendance
    extra = 1
    fields = (
        'worker_name', 'labor_classification', 'crew', 'contractor_name', 'activity_location', 'employee', 'daily_worker',
        'time_in', 'time_out', 'break_hours', 'overtime_hours', 'total_hours', 'notes',
    )
    readonly_fields = ('total_hours',)


class DailyReportActivityProgressInline(admin.TabularInline):
    model = DailyReportActivityProgress
    extra = 1
    fields = (
        'activity_description', 'sub_item', 'location', 'unit', 'status',
        'total_quantity', 'quantity_today', 'quantity_cumulative', 'completion_percentage', 'reference_notes',
    )


class DailyReportQAQCInline(admin.StackedInline):
    model = DailyReportQAQC
    can_delete = False
    max_num = 1


class DailyReportNextDayPlanInline(admin.TabularInline):
    model = DailyReportNextDayPlan
    extra = 1
    fields = (
        'order', 'planned_activity', 'location', 'sub_item', 'manpower_required',
        'resources_required', 'requirement_notes', 'responsible_party', 'priority', 'readiness',
    )


class SiteEventInline(admin.TabularInline):
    """Log Delay/SI/RFI/NCR/HSE events directly from the daily report they were first raised in."""
    model = SiteEvent
    fk_name = 'daily_report'
    extra = 0
    fields = ('event_type', 'reference', 'event_date', 'status', 'description', 'responsible_user', 'responsible_party')


# ==================== STANDALONE ADMIN PAGES ====================

@admin.register(DailyReportWorkerAttendance)
class DailyReportWorkerAttendanceAdmin(admin.ModelAdmin):
    list_display = ('report', 'worker_name', 'daily_worker', 'crew', 'labor_classification', 'time_in', 'time_out', 'total_hours')
    list_filter = ('labor_classification', 'report')
    search_fields = ('report__report_number', 'worker_name', 'daily_worker__full_name', 'daily_worker__national_id')
    readonly_fields = ('total_hours', 'created_at', 'updated_at')


@admin.register(DailyReportCrew)
class DailyReportCrewAdmin(admin.ModelAdmin):
    list_display = ('report', 'name', 'activity', 'contractor_name', 'agreement')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'name', 'contractor_name')


@admin.register(DailyReportActivityProgress)
class DailyReportActivityProgressAdmin(admin.ModelAdmin):
    list_display = ('report', 'activity_description', 'sub_item', 'status', 'quantity_today', 'quantity_cumulative', 'completion_percentage')
    list_filter = ('status', 'sub_item__phase__project', 'report')
    search_fields = ('report__report_number', 'activity_description', 'sub_item__name_ar', 'sub_item__name_en', 'location')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyReportQAQC)
class DailyReportQAQCAdmin(admin.ModelAdmin):
    list_display = (
        'report', 'inspection_status', 'toolbox_talk_conducted',
        'incident_occurred', 'near_miss_occurred', 'ppe_site_cleanliness_status',
    )
    list_filter = ('inspection_status', 'toolbox_talk_conducted', 'incident_occurred', 'near_miss_occurred')
    search_fields = ('report__report_number', 'notes')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyReportNextDayPlan)
class DailyReportNextDayPlanAdmin(admin.ModelAdmin):
    list_display = ('report', 'planned_activity', 'location', 'priority', 'readiness', 'responsible_party', 'order')
    list_filter = ('priority', 'readiness', 'report')
    search_fields = ('report__report_number', 'planned_activity', 'location', 'responsible_party')
    readonly_fields = ('created_at', 'updated_at')
