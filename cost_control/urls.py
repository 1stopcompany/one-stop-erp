from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "cost_control"

router = DefaultRouter()
router.register(r"budgets", views.BudgetViewSet, basename="api_budgets")
router.register(r"forecasts", views.ForecastViewSet, basename="api_forecasts")
router.register(r"reports", views.ReportViewSet, basename="api_reports")
router.register(r"alerts", views.AlertViewSet, basename="api_alerts")

urlpatterns = [
    path("", views.CostControlDashboardView.as_view(), name="dashboard"),
    path("manual.pdf", views.PricingManualPdfView.as_view(), name="manual_pdf"),
    path("report.pdf", views.CostReportPdfView.as_view(), name="report_pdf"),

    path("budgets/", views.BudgetListView.as_view(), name="budget_list"),
    path("budgets/create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("budgets/<int:pk>/", views.BudgetDetailView.as_view(), name="budget_detail"),

    path("forecasts/", views.ForecastListView.as_view(), name="forecast_list"),
    path("forecasts/create/", views.ForecastCreateView.as_view(), name="forecast_create"),

    path("reports/", views.ReportListView.as_view(), name="report_list"),
    path("reports/create/", views.ReportCreateView.as_view(), name="report_create"),
    path("reports/<int:pk>/", views.ReportDetailView.as_view(), name="report_detail"),

    path("alerts/", views.AlertListView.as_view(), name="alert_list"),

    # Dashboard chart endpoints. Keep them before the DRF router include.
    path(
        "api/charts/budget-vs-actual/",
        views.BudgetVsActualAPIView.as_view(),
        name="api_budget_vs_actual",
    ),
    path(
        "api/charts/variance-analysis/",
        views.VarianceAnalysisAPIView.as_view(),
        name="api_variance_analysis",
    ),

    path("api/", include(router.urls)),
]
