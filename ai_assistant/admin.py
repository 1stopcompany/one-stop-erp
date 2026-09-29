from django.contrib import admin

from .models import AIRun


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "project", "kind", "status", "model_name", "input_tokens", "output_tokens", "created_by")
    list_filter = ("kind", "status")
    readonly_fields = ("result", "error", "import_summary")
