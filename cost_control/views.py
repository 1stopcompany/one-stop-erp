from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
)
from rest_framework import permissions, viewsets

from projects.models import Project

from .forms import CostForecastForm, CostReportForm
from django.db.models import Q

from procurement.models import PurchaseOrderLine
from reports.progress_models import ProjectPhaseSubItem

from .models import Budget, BudgetAlert, CostForecast, CostReport
from .services import project_cost_summary
from .serializers import (
    BudgetAlertSerializer,
    BudgetSerializer,
    CostForecastSerializer,
    CostReportSerializer,
)


ZERO = Decimal("0")


def accessible_projects(user):
    """Return the projects visible to the current user.

    Administrators and site engineers keep the project's existing behaviour and
    can see all projects. Project managers can see only projects assigned to
    them.
    """
    queryset = Project.objects.all().order_by("name")
    if user.is_project_manager():
        queryset = queryset.filter(manager=user)
    return queryset


def get_accessible_project(request, project_id):
    """Resolve a project while applying the same access rule as the dashboard."""
    return get_object_or_404(accessible_projects(request.user), pk=project_id)


class CostControlDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "cost_control/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = accessible_projects(self.request.user)
        project_id = self.request.GET.get("project")
        project = None

        if project_id:
            project = get_accessible_project(self.request, project_id)

        context.update(
            {
                "projects": projects,
                "project": project,
                "total_budgeted": ZERO,
                "total_actual": ZERO,
                "total_variance": ZERO,
                "variance_percentage": ZERO,
                "on_budget_count": 0,
                "over_budget_count": 0,
                "under_budget_count": 0,
                "active_alerts": 0,
                "recent_alerts": BudgetAlert.objects.none(),
                "recent_reports": CostReport.objects.none(),
            }
        )

        if project is None:
            return context

        summary = project_cost_summary(project)
        totals = summary["totals"]
        counts = summary["counts"]

        # Variance here is earned value minus actual (negative = over cost), not actual minus the
        # whole budget -- see cost_control.services for why.
        variance = totals["cost_variance"]
        recent_alerts = (
            BudgetAlert.objects.filter(
                project=project,
                is_active=True,
                is_resolved=False,
            )
            .select_related("sub_item", "sub_item__phase")
            .order_by("-created_date")[:10]
        )

        context.update(
            {
                "summary": summary,
                "totals": totals,
                "total_budgeted": totals["budget"],
                "total_actual": totals["actual"],
                "total_variance": variance,
                "variance_percentage": (variance / totals["earned"] * Decimal("100")) if totals["earned"] else ZERO,
                "unassigned": summary["unassigned"],
                "on_budget_count": counts["on_budget"],
                "over_budget_count": counts["over_budget"],
                "under_budget_count": counts["under_budget"],
                "active_alerts": BudgetAlert.objects.filter(
                    project=project,
                    is_active=True,
                    is_resolved=False,
                ).count(),
                "recent_alerts": recent_alerts,
                "recent_reports": CostReport.objects.filter(project=project)
                .select_related("project")
                .order_by("-report_date", "-created_date")[:5],
            }
        )
        return context


class PricingManualPdfView(LoginRequiredMixin, View):
    """The illustrated Arabic user guide for pricing and cost control (same idea as the Procurement / HR guides)."""

    def get(self, request):
        from .manual_pdf import generate_pricing_manual_pdf

        response = HttpResponse(generate_pricing_manual_pdf(), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="pricing-cost-control-user-guide.pdf"'
        return response


class CostReportPdfView(LoginRequiredMixin, View):
    """Print-out of the Budget vs Actual report for one project, for management."""

    def get(self, request):
        from reports.views_print import can_print_management_reports
        from .report_pdf import generate_cost_report_pdf

        project = get_accessible_project(request, request.GET.get("project", 0))
        if not can_print_management_reports(request.user, project):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("The cost report print-out is for management.")
        response = HttpResponse(generate_cost_report_pdf(project), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="cost-report-{project.project_symbol}.pdf"'
        return response


class BudgetVsActualAPIView(LoginRequiredMixin, View):
    """Return item-level budget and actual values for the selected project."""

    def get(self, request, *args, **kwargs):
        project_id = request.GET.get("project_id")
        if not project_id:
            return JsonResponse({"detail": "project_id is required."}, status=400)

        project = get_accessible_project(request, project_id)
        rows = project_cost_summary(project)["phases"]  # one bar group per BOQ phase keeps the chart readable

        return JsonResponse(
            {
                "project_id": project.pk,
                "project_name": project.name,
                "labels": [row["code"] or row["name"] for row in rows],
                "budgeted": [float(row["budget"]) for row in rows],
                "committed": [float(row["committed"]) for row in rows],
                "earned": [float(row["earned"]) for row in rows],
                "actual": [float(row["actual"]) for row in rows],
            }
        )


class VarianceAnalysisAPIView(LoginRequiredMixin, View):
    """Return budget status counts for the selected project."""

    def get(self, request, *args, **kwargs):
        project_id = request.GET.get("project_id")
        if not project_id:
            return JsonResponse({"detail": "project_id is required."}, status=400)

        project = get_accessible_project(request, project_id)
        counts = project_cost_summary(project)["counts"]

        return JsonResponse(
            {
                "project_id": project.pk,
                "on_budget": counts["on_budget"],
                "over_budget": counts["over_budget"],
                "under_budget": counts["under_budget"],
            }
        )


class BudgetListView(LoginRequiredMixin, TemplateView):
    """
    Budget vs committed vs actual vs earned, on the project's own BOQ (phases and sub-items).
    With ?project= it is that project's table; without, one headline row per project. There
    is nothing to type in here: budgets are the prices entered in Manage BOQ.
    """
    template_name = "cost_control/budget_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projects = accessible_projects(self.request.user)
        context["projects"] = projects
        project_id = self.request.GET.get("project")
        if project_id:
            project = get_accessible_project(self.request, project_id)
            summary = project_cost_summary(project)
            context.update({"project": project, "summary": summary, "lines": summary["lines"], "totals": summary["totals"]})
        else:
            rows = []
            for project in projects:
                summary = project_cost_summary(project)
                if summary["lines"]:
                    rows.append(summary)
            context["portfolio"] = rows
        return context


class BudgetCreateView(LoginRequiredMixin, TemplateView):
    """Budgets are no longer entered here: this page says so and points to the project's BOQ."""
    template_name = "cost_control/budget_from_boq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["projects"] = accessible_projects(self.request.user)
        return context


class BudgetDetailView(LoginRequiredMixin, DetailView):
    """One BOQ item (sub-item): its figures, and the purchase-order lines charged to it."""
    model = ProjectPhaseSubItem
    template_name = "cost_control/budget_detail.html"
    context_object_name = "sub_item"

    def get_queryset(self):
        return ProjectPhaseSubItem.objects.filter(
            phase__project__in=accessible_projects(self.request.user)
        ).select_related("phase", "phase__project")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object.phase.project
        summary = project_cost_summary(project)
        context["project"] = project
        context["line"] = next((row for row in summary["lines"] if row["sub_item"].pk == self.object.pk), None)
        context["po_lines"] = (
            PurchaseOrderLine.objects.filter(po__project=project)
            .filter(Q(sub_item=self.object) | Q(sub_item__isnull=True, pr_line__sub_item=self.object))
            .select_related("po", "po__vendor", "item")
            .order_by("-po__po_date")
        )
        return context


class ForecastListView(LoginRequiredMixin, ListView):
    model = CostForecast
    template_name = "cost_control/forecast_list.html"
    context_object_name = "forecasts"


class ForecastCreateView(LoginRequiredMixin, CreateView):
    model = CostForecast
    form_class = CostForecastForm
    template_name = "cost_control/form.html"
    success_url = reverse_lazy("cost_control:forecast_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ReportListView(LoginRequiredMixin, ListView):
    model = CostReport
    template_name = "cost_control/report_list.html"
    context_object_name = "reports"


class ReportCreateView(LoginRequiredMixin, CreateView):
    model = CostReport
    form_class = CostReportForm
    template_name = "cost_control/form.html"
    success_url = reverse_lazy("cost_control:report_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ReportDetailView(LoginRequiredMixin, DetailView):
    model = CostReport
    template_name = "cost_control/report_detail.html"
    context_object_name = "report"


class AlertListView(LoginRequiredMixin, ListView):
    model = BudgetAlert
    template_name = "cost_control/alert_list.html"
    context_object_name = "alerts"


# ----- DRF -----
class BudgetViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only: budget lines are created from the approved BOQ, not through the API."""
    queryset = Budget.objects.select_related("project", "item").all()
    serializer_class = BudgetSerializer
    permission_classes = [permissions.IsAuthenticated]


class ForecastViewSet(viewsets.ModelViewSet):
    queryset = CostForecast.objects.select_related("project", "item", "budget").all()
    serializer_class = CostForecastSerializer
    permission_classes = [permissions.IsAuthenticated]


class ReportViewSet(viewsets.ModelViewSet):
    queryset = CostReport.objects.select_related("project").all()
    serializer_class = CostReportSerializer
    permission_classes = [permissions.IsAuthenticated]


class AlertViewSet(viewsets.ModelViewSet):
    queryset = BudgetAlert.objects.select_related("project", "budget").all()
    serializer_class = BudgetAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
