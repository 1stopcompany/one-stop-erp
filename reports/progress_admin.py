"""
Django Admin Configuration for Project Phase Progress and Site Events
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .progress_models import (
    ProjectPhase,
    ProjectPhaseSubItem,
    ProjectPhaseProgressEntry,
    ProjectMilestone,
    ProjectPhasePhoto,
)
from .site_event_models import SiteEvent
from .schedule_models import ScheduleTask


class ProjectPhaseSubItemInline(admin.TabularInline):
    model = ProjectPhaseSubItem
    extra = 1
    fields = ('order', 'name_ar', 'name_en', 'weight_percentage', 'planned_start_date', 'planned_completion_date')


class ProjectPhasePhotoInline(admin.TabularInline):
    model = ProjectPhasePhoto
    extra = 1
    fields = ('order', 'photo', 'sub_item', 'caption', 'taken_date')


@admin.register(ProjectPhase)
class ProjectPhaseAdmin(admin.ModelAdmin):
    list_display = ('project', 'code', 'name_ar', 'name_en', 'weight_percentage', 'sub_items_weight_total', 'order')
    list_filter = ('project',)
    search_fields = ('name_ar', 'name_en', 'code', 'project__name', 'project__project_symbol')
    ordering = ('project', 'order', 'code')
    inlines = [ProjectPhaseSubItemInline, ProjectPhasePhotoInline]
    readonly_fields = ('created_at', 'updated_at')

    def sub_items_weight_total(self, obj):
        return obj.sub_items_weight_total()
    sub_items_weight_total.short_description = _('Sub-items weight total')


@admin.register(ProjectPhaseSubItem)
class ProjectPhaseSubItemAdmin(admin.ModelAdmin):
    list_display = ('phase', 'name_ar', 'name_en', 'weight_percentage', 'planned_start_date', 'planned_completion_date')
    list_filter = ('phase__project',)
    search_fields = ('name_ar', 'name_en', 'phase__name_ar', 'phase__name_en')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectPhaseProgressEntry)
class ProjectPhaseProgressEntryAdmin(admin.ModelAdmin):
    list_display = ('sub_item', 'report_date', 'execution_percentage', 'daily_report', 'monthly_report', 'recorded_by')
    list_filter = ('sub_item__phase__project', 'report_date')
    search_fields = ('sub_item__name_ar', 'sub_item__name_en', 'notes')
    readonly_fields = ('created_at',)
    date_hierarchy = 'report_date'


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ('phase', 'name_ar', 'name_en', 'baseline_date', 'forecast_date', 'actual_date', 'status')
    list_filter = ('phase__project',)
    search_fields = ('name_ar', 'name_en', 'phase__name_ar', 'phase__name_en')
    readonly_fields = ('created_at', 'updated_at')

    def status(self, obj):
        return obj.status
    status.short_description = _('Status')


@admin.register(ScheduleTask)
class ScheduleTaskAdmin(admin.ModelAdmin):
    list_display = ('project', 'source_task_id', 'name', 'start_date', 'finish_date', 'is_critical', 'total_slack_days', 'is_summary')
    list_filter = ('project', 'is_critical', 'is_summary')
    search_fields = ('name',)
    ordering = ('project', 'source_task_id')
    readonly_fields = ('imported_at',)


@admin.register(SiteEvent)
class SiteEventAdmin(admin.ModelAdmin):
    list_display = (
        'project', 'event_type', 'reference', 'event_date', 'status',
        'responsible_user', 'responsible_party', 'target_date', 'time_impact_hours',
    )
    list_filter = ('project', 'event_type', 'status', 'event_date')
    search_fields = ('reference', 'description', 'required_action', 'remarks')
    date_hierarchy = 'event_date'
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('project', 'daily_report', 'event_type', 'reference', 'event_date', 'status')
        }),
        (_('Details'), {
            'fields': ('description', 'required_action', 'time_impact_hours', 'remarks')
        }),
        (_('Responsibility & Dates'), {
            'fields': ('responsible_user', 'responsible_party', 'target_date', 'closed_date')
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ProjectPhasePhoto)
class ProjectPhasePhotoAdmin(admin.ModelAdmin):
    list_display = ('phase', 'sub_item', 'taken_date', 'order', 'daily_report', 'monthly_report', 'owner_financial_report')
    list_filter = ('phase__project', 'taken_date')
    search_fields = ('caption', 'phase__name_ar', 'phase__name_en')
    readonly_fields = ('created_at',)
