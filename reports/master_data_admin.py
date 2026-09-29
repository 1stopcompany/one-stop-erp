"""
Django Admin Configuration for Master Data Models
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .master_data_models import (
    WorkforceCategory, LaborClassification, EquipmentMaster,
    ReportMaterialItem, DailyReportWorkforceEntry, DailyReportEquipmentEntry,
    DailyReportMaterialEntry
)


@admin.register(WorkforceCategory)
class WorkforceCategoryAdmin(admin.ModelAdmin):
    """Admin for Workforce Categories"""
    
    list_display = ('name', 'is_staff_category', 'is_active', 'order', 'created_at')
    list_filter = ('is_staff_category', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('order', 'name')

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'is_staff_category', 'is_active', 'order')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LaborClassification)
class LaborClassificationAdmin(admin.ModelAdmin):
    """Admin for Labor Classifications"""
    
    list_display = ('name', 'category', 'default_gender', 'is_active', 'order')
    list_filter = ('category', 'is_active', 'default_gender')
    search_fields = ('name', 'description')
    ordering = ('category', 'order', 'name')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('category', 'name', 'description')
        }),
        (_('Settings'), {
            'fields': ('default_gender', 'is_active', 'order')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(EquipmentMaster)
class EquipmentMasterAdmin(admin.ModelAdmin):
    """Admin for Equipment Master List"""
    
    list_display = ('name', 'category', 'manufacturer', 'model', 'is_active')
    list_filter = ('category', 'is_active', 'manufacturer')
    search_fields = ('name', 'description', 'manufacturer', 'model')
    ordering = ('category', 'name')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'description', 'category')
        }),
        (_('Specifications'), {
            'fields': ('manufacturer', 'model', 'year_built')
        }),
        (_('Status'), {
            'fields': ('is_active',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReportMaterialItem)
class ReportMaterialItemAdmin(admin.ModelAdmin):
    """Admin for Bill of Quantities"""
    
    list_display = ('item_code', 'project', 'description', 'quantity', 'unit', 'category', 'is_active')
    list_filter = ('project', 'category', 'is_active', 'created_at')
    search_fields = ('item_code', 'description', 'category', 'supplier')
    ordering = ('project', 'category', 'item_code')
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('project', 'item_code', 'description', 'category')
        }),
        (_('Quantities and Rates'), {
            'fields': ('quantity', 'unit', 'unit_rate', 'total_amount')
        }),
        (_('Supplier'), {
            'fields': ('supplier',)
        }),
        (_('Additional Information'), {
            'fields': ('notes', 'is_active')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('total_amount', 'created_at', 'updated_at')


@admin.register(DailyReportWorkforceEntry)
class DailyReportWorkforceEntryAdmin(admin.ModelAdmin):
    """Admin for Daily Report Workforce Entries"""
    
    list_display = ('report', 'labor_classification', 'number_of_employees', 'gender', 'hours_worked')
    list_filter = ('report__report_date', 'gender', 'labor_classification__category')
    search_fields = ('report__report_number', 'labor_classification__name')
    ordering = ('-report__report_date', 'labor_classification')
    
    fieldsets = (
        (_('Report Information'), {
            'fields': ('report', 'labor_classification')
        }),
        (_('Workforce Details'), {
            'fields': ('number_of_employees', 'gender', 'hours_worked')
        }),
        (_('Additional Information'), {
            'fields': ('notes',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyReportEquipmentEntry)
class DailyReportEquipmentEntryAdmin(admin.ModelAdmin):
    """Admin for Daily Report Equipment Entries"""
    
    list_display = ('report', 'equipment', 'quantity_in_use', 'hours_worked', 'quantity_idle')
    list_filter = ('report__report_date', 'equipment__category')
    search_fields = ('report__report_number', 'equipment__name')
    ordering = ('-report__report_date', 'equipment')
    
    fieldsets = (
        (_('Report Information'), {
            'fields': ('report', 'equipment')
        }),
        (_('Equipment Usage'), {
            'fields': ('quantity_in_use', 'hours_worked', 'quantity_idle')
        }),
        (_('Additional Information'), {
            'fields': ('remarks',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DailyReportMaterialEntry)
class DailyReportMaterialEntryAdmin(admin.ModelAdmin):
    """Admin for Daily Report Material Entries"""
    
    list_display = ('report', 'boq_item', 'quantity_used', 'quantity_wasted')
    list_filter = ('report__report_date', 'boq_item__category')
    search_fields = ('report__report_number', 'boq_item__description')
    ordering = ('-report__report_date', 'boq_item')
    
    fieldsets = (
        (_('Report Information'), {
            'fields': ('report', 'boq_item')
        }),
        (_('Material Usage'), {
            'fields': ('quantity_used', 'quantity_wasted')
        }),
        (_('Additional Information'), {
            'fields': ('remarks',)
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
