"""
Reports Admin Configuration - Unified Daily and Monthly Reporting System

This module configures the Django admin interface for reports.
"""

from django.contrib import admin
from .models import (
    DailyReport, DailyWorkForce, DailyEquipment, DailyActivity, DailyMaterial, DailyVisitor,
    MonthlyReport, FloorActivity, ExternalWork, MaterialSupply, UpcomingWork, ReportAttachment,
    MonthlyProgressCategoryItem, MonthlyKeyActivity, MonthlyIssueRiskDelay, MonthlyReviewComment,
)

# NOTE: these admin modules previously existed but were never imported
# anywhere, so none of their models ever showed up in Django admin.
# Importing them here (admin.py is the module Django auto-discovers)
# is what actually registers them.
from . import master_data_admin  # noqa: E402,F401
from . import email_admin  # noqa: E402,F401
from . import progress_admin  # noqa: E402,F401
from . import daily_detail_admin  # noqa: E402,F401
from . import owner_financial_admin  # noqa: E402,F401

from .daily_detail_admin import (
    DailyReportWorkerAttendanceInline,
    DailyReportActivityProgressInline,
    DailyReportQAQCInline,
    DailyReportNextDayPlanInline,
    SiteEventInline,
)


# ==================== DAILY REPORT ADMIN ====================

class DailyWorkForceInline(admin.TabularInline):
    """Inline admin for DailyWorkForce"""
    model = DailyWorkForce
    extra = 1
    fields = ('category', 'designation', 'count')


class DailyEquipmentInline(admin.TabularInline):
    """Inline admin for DailyEquipment"""
    model = DailyEquipment
    extra = 1
    fields = ('equipment_name', 'hours_worked', 'quantity_idle')


class DailyActivityInline(admin.TabularInline):
    """Inline admin for DailyActivity"""
    model = DailyActivity
    extra = 1
    fields = ('activity_type', 'location', 'activity_description')


class DailyMaterialInline(admin.TabularInline):
    """Inline admin for DailyMaterial"""
    model = DailyMaterial
    extra = 1
    fields = ('material_description', 'quantity', 'unit')


class DailyVisitorInline(admin.TabularInline):
    """Inline admin for DailyVisitor"""
    model = DailyVisitor
    extra = 1
    fields = ('visit_time', 'visitor_name', 'representing')


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    """Admin configuration for DailyReport"""
    
    list_display = ('report_number', 'project', 'site_engineer', 'report_date', 'status', 'approved_by')
    list_filter = ('status', 'report_date', 'weather_conditions', 'project')
    search_fields = ('report_number', 'project__name', 'site_engineer__username')
    readonly_fields = ('report_number', 'created_at', 'updated_at', 'approval_date')
    inlines = [
        DailyWorkForceInline, DailyEquipmentInline, DailyActivityInline, DailyMaterialInline, DailyVisitorInline,
        DailyReportWorkerAttendanceInline, DailyReportActivityProgressInline, DailyReportQAQCInline,
        DailyReportNextDayPlanInline, SiteEventInline,
    ]
    
    fieldsets = (
        ('Report Information', {
            'fields': ('report_number', 'project', 'site_engineer', 'report_date')
        }),
        ('Details', {
            'fields': ('weather_conditions', 'remarks')
        }),
        ('Approval', {
            'fields': ('status', 'approved_by', 'approval_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-report_date',)


@admin.register(DailyWorkForce)
class DailyWorkForceAdmin(admin.ModelAdmin):
    """Admin configuration for DailyWorkForce"""
    
    list_display = ('report', 'category', 'designation', 'count')
    list_filter = ('category', 'report')
    search_fields = ('report__report_number', 'designation')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyEquipment)
class DailyEquipmentAdmin(admin.ModelAdmin):
    """Admin configuration for DailyEquipment"""
    
    list_display = ('report', 'equipment_name', 'hours_worked', 'quantity_idle')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'equipment_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyActivity)
class DailyActivityAdmin(admin.ModelAdmin):
    """Admin configuration for DailyActivity"""
    
    list_display = ('report', 'activity_type', 'location')
    list_filter = ('activity_type', 'report')
    search_fields = ('report__report_number', 'location', 'activity_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyMaterial)
class DailyMaterialAdmin(admin.ModelAdmin):
    """Admin configuration for DailyMaterial"""
    
    list_display = ('report', 'material_description', 'quantity', 'unit')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'material_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyVisitor)
class DailyVisitorAdmin(admin.ModelAdmin):
    """Admin configuration for DailyVisitor"""
    
    list_display = ('report', 'visitor_name', 'visit_time', 'representing')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'visitor_name', 'representing')
    readonly_fields = ('created_at', 'updated_at')


# ==================== MONTHLY REPORT ADMIN ====================

class FloorActivityInline(admin.TabularInline):
    """Inline admin for FloorActivity"""
    model = FloorActivity
    extra = 1
    fields = ('floor', 'activity_description', 'completion_percentage')


class ExternalWorkInline(admin.TabularInline):
    """Inline admin for ExternalWork"""
    model = ExternalWork
    extra = 1
    fields = ('work_description', 'completion_percentage')


class MaterialSupplyInline(admin.TabularInline):
    """Inline admin for MaterialSupply"""
    model = MaterialSupply
    extra = 1
    # delivered_quantity/used_quantity/remaining_notes back the EDGE
    # report's "Materials Status" table (Delivered/Used/Remaining columns)
    # -- they existed on the model but were missing here, so that table
    # had no way to be filled in from admin.
    fields = ('material_type', 'material_description', 'quantity', 'unit', 'delivered_quantity', 'used_quantity', 'remaining_notes')


class MonthlyProgressCategoryItemInline(admin.TabularInline):
    model = MonthlyProgressCategoryItem
    extra = 1
    fields = ('order', 'item_name', 'planned_value', 'actual_value')


class MonthlyKeyActivityInline(admin.TabularInline):
    model = MonthlyKeyActivity
    extra = 1
    fields = ('order', 'activity', 'status', 'remarks')


class MonthlyIssueRiskDelayInline(admin.TabularInline):
    model = MonthlyIssueRiskDelay
    extra = 1
    fields = ('order', 'description', 'impact', 'mitigation')


class MonthlyReviewCommentInline(admin.TabularInline):
    model = MonthlyReviewComment
    extra = 1
    fields = ('order', 'reference', 'comment_text', 'response_text', 'status')


class UpcomingWorkInline(admin.TabularInline):
    """Inline admin for UpcomingWork"""
    model = UpcomingWork
    extra = 1
    fields = ('work_description', 'planned_start_date', 'planned_end_date')


@admin.register(MonthlyReport)
class MonthlyReportAdmin(admin.ModelAdmin):
    """Admin configuration for MonthlyReport"""
    
    list_display = ('report_number', 'project', 'site_engineer', 'reporting_period_to', 'revision_number', 'status', 'approved_by')
    list_filter = ('status', 'reporting_period_to', 'weather_conditions', 'project')
    search_fields = ('report_number', 'project__name', 'site_engineer__username')
    readonly_fields = ('report_number', 'created_at', 'updated_at', 'approval_date')
    inlines = [
        MonthlyProgressCategoryItemInline, MonthlyKeyActivityInline,
        FloorActivityInline, ExternalWorkInline, MaterialSupplyInline, UpcomingWorkInline,
        MonthlyIssueRiskDelayInline, MonthlyReviewCommentInline,
    ]

    fieldsets = (
        ('Report Information', {
            'fields': ('report_number', 'project', 'site_engineer', 'report_date')
        }),
        ('Reporting Period', {
            'fields': ('reporting_period_from', 'reporting_period_to')
        }),
        ('Details', {
            'fields': ('weather_conditions', 'general_description')
        }),
        ('Executive Summary', {
            'fields': ('executive_summary', 'schedule_variance_note')
        }),
        ('Health, Safety & Environment (HSE)', {
            'fields': (
                'hse_lti_note', 'hse_near_misses_note', 'hse_toolbox_talks_note',
                'hse_site_inspections_note', 'hse_corrective_actions_note',
            )
        }),
        ('Quality Control / Inspections', {
            'fields': ('qc_inspections_note', 'qc_nonconformances_note', 'qc_pending_submittals_note')
        }),
        ('Plan for Next Month', {
            'fields': ('next_month_plan',)
        }),
        ('Photographic Record', {
            'fields': ('photos_external_link',)
        }),
        ('Revision (Supervision / External Consultant Review)', {
            'fields': ('revision_number', 'revision_note')
        }),
        ('Approval', {
            'fields': ('status', 'approved_by', 'approval_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-reporting_period_to',)


@admin.register(FloorActivity)
class FloorActivityAdmin(admin.ModelAdmin):
    """Admin configuration for FloorActivity"""
    
    list_display = ('report', 'floor', 'completion_percentage')
    list_filter = ('report', 'floor')
    search_fields = ('report__report_number', 'activity_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ExternalWork)
class ExternalWorkAdmin(admin.ModelAdmin):
    """Admin configuration for ExternalWork"""
    
    list_display = ('report', 'completion_percentage')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'work_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MaterialSupply)
class MaterialSupplyAdmin(admin.ModelAdmin):
    """Admin configuration for MaterialSupply"""
    
    list_display = ('report', 'material_description', 'quantity', 'unit')
    list_filter = ('report',)
    search_fields = ('report__report_number', 'material_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(UpcomingWork)
class UpcomingWorkAdmin(admin.ModelAdmin):
    """Admin configuration for UpcomingWork"""
    
    list_display = ('report', 'planned_start_date', 'planned_end_date')
    list_filter = ('report', 'planned_start_date')
    search_fields = ('report__report_number', 'work_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReportAttachment)
class ReportAttachmentAdmin(admin.ModelAdmin):
    """Admin configuration for ReportAttachment"""

    list_display = ('report_type', 'report_id', 'attachment_type', 'order', 'location', 'activity', 'site_event', 'created_at')
    list_filter = ('report_type', 'attachment_type', 'created_at')
    search_fields = ('description', 'location')
    ordering = ('report_type', 'report_id', 'order')
    readonly_fields = ('created_at',)
