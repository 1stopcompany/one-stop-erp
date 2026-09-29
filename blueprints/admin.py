from django.contrib import admin

from .models import Blueprint, BlueprintRevision


class BlueprintRevisionInline(admin.TabularInline):
    model = BlueprintRevision
    extra = 0


@admin.register(Blueprint)
class BlueprintAdmin(admin.ModelAdmin):
    list_display = ("drawing_number", "title", "project", "discipline")
    list_filter = ("discipline", "project")
    search_fields = ("drawing_number", "title")
    inlines = [BlueprintRevisionInline]
