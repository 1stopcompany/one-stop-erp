from rest_framework import serializers
from .models import Budget, CostForecast, CostReport, BudgetAlert


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = "__all__"
        read_only_fields = (
            "budgeted_total", "actual_quantity", "actual_unit_price", "actual_total",
            "quantity_variance", "price_variance", "total_variance", "variance_percentage",
            "status", "created_by", "created_date", "updated_date",
        )


class CostForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostForecast
        fields = "__all__"
        read_only_fields = ("project", "item", "forecast_total", "quantity_variance", "price_variance", "total_variance", "created_by", "created_date")


class CostReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostReport
        fields = "__all__"
        read_only_fields = (
            "total_budgeted", "total_actual", "total_variance", "variance_percentage",
            "on_budget_count", "over_budget_count", "under_budget_count", "created_by", "created_date",
        )


class BudgetAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetAlert
        fields = "__all__"
