from django import forms
from .models import CostForecast, CostReport, BudgetAlert


class CostForecastForm(forms.ModelForm):
    class Meta:
        model = CostForecast
        fields = ["budget", "forecast_quantity", "forecast_unit_price", "confidence_level"]


class CostReportForm(forms.ModelForm):
    class Meta:
        model = CostReport
        fields = ["project", "report_type", "period_start", "period_end", "recommendations"]


class BudgetAlertForm(forms.ModelForm):
    class Meta:
        model = BudgetAlert
        fields = ["project", "budget", "alert_type", "severity", "message", "threshold_value", "actual_value", "is_active", "is_resolved"]
