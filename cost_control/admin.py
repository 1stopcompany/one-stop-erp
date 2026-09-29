from django.contrib import admin
from .models import Budget, CostForecast, CostReport, BudgetAlert


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("project", "item", "budgeted_total", "actual_total", "total_variance", "variance_percentage", "status", "updated_date")
    list_filter = ("status", "project", "created_date", "updated_date")
    search_fields = ("project__name", "item__full_code", "item__description")
    readonly_fields = (
        "budgeted_total", "actual_quantity", "actual_unit_price", "actual_total",
        "quantity_variance", "price_variance", "total_variance", "variance_percentage",
        "status", "created_date", "updated_date",
    )


@admin.register(CostForecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ("project", "item", "forecast_date", "forecast_total", "total_variance", "confidence_level")
    list_filter = ("confidence_level", "project", "forecast_date")
    search_fields = ("project__name", "item__full_code")
    readonly_fields = ("project", "item", "forecast_total", "quantity_variance", "price_variance", "total_variance", "created_date")


@admin.register(CostReport)
class CostReportAdmin(admin.ModelAdmin):
    list_display = ("project", "report_type", "period_start", "period_end", "total_variance", "variance_percentage", "created_date")
    list_filter = ("report_type", "project", "report_date")
    search_fields = ("project__name",)
    readonly_fields = (
        "total_budgeted", "total_actual", "total_variance", "variance_percentage",
        "on_budget_count", "over_budget_count", "under_budget_count", "created_date"
    )


@admin.register(BudgetAlert)
class BudgetAlertAdmin(admin.ModelAdmin):
    list_display = ("project", "alert_type", "severity", "is_active", "is_resolved", "created_date")
    list_filter = ("severity", "alert_type", "is_active", "is_resolved")
    search_fields = ("project__name", "message")
