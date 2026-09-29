from django.contrib import admin
from .models import (
    Project, ProjectFloor, ProjectInsurance, ProjectStage, ProjectTenderDocument,
    ProjectRegulatoryApproval, ProjectManagementPlan,
)


@admin.register(ProjectStage)
class ProjectStageAdmin(admin.ModelAdmin):
    list_display = ('project', 'key', 'completed_at', 'completed_by')
    list_filter = ('key',)


@admin.register(ProjectInsurance)
class ProjectInsuranceAdmin(admin.ModelAdmin):
    list_display = ('project', 'policy_type', 'insurer', 'policy_number', 'end_date')
    list_filter = ('policy_type',)


@admin.register(ProjectTenderDocument)
class ProjectTenderDocumentAdmin(admin.ModelAdmin):
    list_display = ('project', 'category', 'title', 'uploaded_at')
    list_filter = ('category',)


@admin.register(ProjectRegulatoryApproval)
class ProjectRegulatoryApprovalAdmin(admin.ModelAdmin):
    list_display = ('project', 'body', 'approval_number', 'approved_date', 'uploaded_at')
    list_filter = ('body',)


@admin.register(ProjectManagementPlan)
class ProjectManagementPlanAdmin(admin.ModelAdmin):
    list_display = ('project', 'category', 'title', 'checklist_complete', 'uploaded_at')
    list_filter = ('category',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Admin configuration for Project"""
    
    list_display = ('name', 'project_symbol', 'contract_number', 'client_name', 'status', 'manager', 'start_date', 'created_at')
    list_filter = ('status', 'maintenance_type', 'created_at')
    search_fields = ('name', 'project_symbol', 'contract_number', 'client_name')
    readonly_fields = ('created_at', 'updated_at', 'created_by')
    fieldsets = (
        ('Project Information', {
            'fields': ('name', 'project_symbol', 'contract_number', 'client_name')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date')
        }),
        ('Details', {
            'fields': ('maintenance_type', 'status', 'location', 'description')
        }),
        ('Management', {
            'fields': ('manager', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-created_at',)


@admin.register(ProjectFloor)
class ProjectFloorAdmin(admin.ModelAdmin):
    """Admin configuration for ProjectFloor"""
    
    list_display = ('project', 'floor_number', 'floor_name', 'area_sqm', 'created_at')
    list_filter = ('project', 'created_at')
    search_fields = ('project__name', 'floor_number', 'floor_name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Floor Information', {
            'fields': ('project', 'floor_number', 'floor_name')
        }),
        ('Details', {
            'fields': ('area_sqm', 'description')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('project', 'floor_number')
