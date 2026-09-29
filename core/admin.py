from django.contrib import admin
from .models import SystemSettings, NotificationTemplate, SpecificationVolume, SpecificationSection


class SpecificationSectionInline(admin.TabularInline):
    model = SpecificationSection
    extra = 0
    fields = ('code', 'title', 'order')


@admin.register(SpecificationVolume)
class SpecificationVolumeAdmin(admin.ModelAdmin):
    list_display = ('label', 'title', 'revision', 'order', 'uploaded_at')
    inlines = [SpecificationSectionInline]


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """Admin configuration for SystemSettings"""
    
    list_display = ('key', 'value', 'updated_at')
    search_fields = ('key', 'description')
    readonly_fields = ('updated_at',)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """Admin configuration for NotificationTemplate"""
    
    list_display = ('name', 'template_type', 'is_active', 'updated_at')
    list_filter = ('template_type', 'is_active', 'updated_at')
    search_fields = ('name', 'subject')
    readonly_fields = ('created_at', 'updated_at')
