from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from reports.models import DailyReport, MonthlyReport
from reports.owner_financial_models import OwnerFinancialReport

from .forms import ProjectFloorForm, ProjectForm
from . import workflow
from .models import Project, ProjectFloor


def is_admin_or_manager(user):
    """Return True when the authenticated user can administer projects."""
    return user.is_authenticated and (user.is_admin() or user.is_project_manager())


def _normalize_report(report, report_type, type_label, detail_url_name, period):
    return {
        'report_number': report.report_number,
        'report_type': report_type,
        'type_label': type_label,
        'author': report.site_engineer,
        'period': period,
        'status': report.status,
        'created_at': report.created_at,
        'detail_url_name': detail_url_name,
        'pk': report.pk,
    }


def project_reports(project, report_type=None, status=None):
    """
    Every Daily / Monthly / Owner Financial report on this one project, normalized into one shape and
    sorted newest-first -- shared by the project page's own "Recent Reports" preview and the project's
    full, dedicated Reports page (project_reports_view below), so the two never drift into different
    logic for what counts as "this project's reports".
    """
    daily_qs = DailyReport.objects.filter(project=project).select_related('site_engineer')
    monthly_qs = MonthlyReport.objects.filter(project=project).select_related('site_engineer')
    owner_qs = OwnerFinancialReport.objects.filter(project=project).select_related('site_engineer')
    all_daily_qs, all_monthly_qs, all_owner_qs = daily_qs, monthly_qs, owner_qs
    if status:
        daily_qs = daily_qs.filter(status=status)
        monthly_qs = monthly_qs.filter(status=status)
        owner_qs = owner_qs.filter(status=status)

    normalized = []
    if report_type in (None, 'daily'):
        normalized += [_normalize_report(r, 'daily', 'Daily', 'reports:daily_report_detail', r.report_date.strftime('%b %d, %Y'))
                       for r in daily_qs]
    if report_type in (None, 'monthly'):
        normalized += [_normalize_report(r, 'monthly', 'Monthly', 'reports:monthly_report_detail',
                                          f"{r.reporting_period_from:%b %d} - {r.reporting_period_to:%b %d, %Y}")
                       for r in monthly_qs]
    if report_type in (None, 'owner_financial'):
        normalized += [_normalize_report(r, 'owner_financial', 'Owner Financial', 'reports:owner_financial_report_detail',
                                          f"{r.reporting_period_from:%b %d} - {r.reporting_period_to:%b %d, %Y}")
                       for r in owner_qs]
    normalized.sort(key=lambda r: r['created_at'], reverse=True)
    return normalized, all_daily_qs, all_monthly_qs, all_owner_qs


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 20

    def get_queryset(self):
        queryset = Project.objects.all()

        if not self.request.user.is_admin():
            if self.request.user.is_project_manager():
                queryset = queryset.filter(manager=self.request.user)
            elif self.request.user.is_site_engineer():
                queryset = queryset.filter(site_engineer=self.request.user)

        search = self.request.GET.get("search")
        status = self.request.GET.get("status")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(project_symbol__icontains=search)
                | Q(contract_number__icontains=search)
            )

        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for project in context["projects"]:
            # Only projects still in the start-up flow show which stage is next.
            project.stage_label = workflow.current_stage_label(project) if project.status == "planning" else None
        context["insurance_alerts"] = workflow.insurance_alerts(self.get_queryset())
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        # Previously unscoped: any logged-in user could open any
        # project's detail page by guessing/entering its id.
        queryset = Project.objects.all()
        if not self.request.user.is_admin():
            if self.request.user.is_project_manager():
                queryset = queryset.filter(manager=self.request.user)
            elif self.request.user.is_site_engineer():
                queryset = queryset.filter(site_engineer=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object

        floors = project.floors.all()
        context["floors"] = floors
        context["floors_count"] = floors.count()

        # The project page's own "Recent Reports" table used to only ever query MonthlyReport (and even
        # then, into a context key -- 'reports' -- the template never read; it reads 'recent_reports'),
        # so a project's Daily and Owner Financial reports never showed up here at all, and PMs/admins
        # had to go through the Reports menu to see them. project_reports() builds one unified,
        # normalized list across all three report types -- shared with the project's own full Reports
        # page (project_reports_view) so the two never show different things.
        normalized, daily_qs, monthly_qs, owner_qs = project_reports(project)
        context["reports_count"] = daily_qs.count() + monthly_qs.count() + owner_qs.count()
        context["approved_reports"] = (
            daily_qs.filter(status='approved').count()
            + monthly_qs.filter(status='approved').count()
            + owner_qs.filter(status='approved').count()
        )
        context["pending_reports"] = (
            daily_qs.filter(status__in=['submitted', 'engineering_approved']).count()
            + monthly_qs.filter(status__in=['submitted', 'engineering_approved']).count()
            + owner_qs.filter(status__in=['submitted', 'engineering_approved']).count()
        )
        context["recent_reports"] = normalized[:10]

        return context


class ProjectReportsView(LoginRequiredMixin, DetailView):
    """One project's own dedicated Reports page -- every Daily / Monthly / Owner Financial report on
    it, filterable by type and status, instead of only the top-10 preview on the project page or having
    to go through the site-wide Reports menu and filter by project there."""
    model = Project
    template_name = "projects/project_reports.html"
    context_object_name = "project"

    def get_queryset(self):
        # Same visibility rule as ProjectDetailView.
        queryset = Project.objects.all()
        if not self.request.user.is_admin():
            if self.request.user.is_project_manager():
                queryset = queryset.filter(manager=self.request.user)
            elif self.request.user.is_site_engineer():
                queryset = queryset.filter(site_engineer=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        report_type = self.request.GET.get('type') or None
        status = self.request.GET.get('status') or None

        normalized, daily_qs, monthly_qs, owner_qs = project_reports(project, report_type=report_type, status=status)
        page_obj = Paginator(normalized, 20).get_page(self.request.GET.get('page'))

        context.update({
            'reports': page_obj.object_list,
            'page_obj': page_obj,
            'is_paginated': page_obj.has_other_pages(),
            'report_type': report_type,
            'status': status,
            'type_counts': {'daily': daily_qs.count(), 'monthly': monthly_qs.count(), 'owner_financial': owner_qs.count()},
            'can_create_daily': self.request.user.is_site_engineer() or self.request.user.is_admin(),
            'can_create_monthly_or_owner': self.request.user.is_project_manager() or self.request.user.is_admin(),
            'status_choices': DailyReport.STATUS_CHOICES,
        })
        return context


class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"

    def get_success_url(self):
        # A new project starts in Planning: take the user straight to its start-up workflow.
        return reverse("projects:workflow", args=[self.object.pk])

    def test_func(self):
        return is_admin_or_manager(self.request.user)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        workflow.ensure_stages(self.object)
        messages.success(
            self.request,
            f"Project {self.object.name} created in Planning. Next: complete its start-up stages "
            f"(insurance, tender documents, approved drawings) under Workflow.",
        )
        return response


class ProjectUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("projects:project_list")

    def test_func(self):
        project = self.get_object()
        return self.request.user.is_admin() or self.request.user == project.manager

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Project {self.object.name} updated successfully.")
        return response


class ProjectDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Project
    template_name = "projects/project_confirm_delete.html"
    success_url = reverse_lazy("projects:project_list")

    def test_func(self):
        project = self.get_object()
        return self.request.user.is_admin() or self.request.user == project.manager

    def form_valid(self, form):
        messages.success(self.request, f"Project {self.object.name} deleted.")
        return super().form_valid(form)


class ProjectFloorListView(LoginRequiredMixin, ListView):
    model = ProjectFloor
    template_name = "projects/floor_list.html"
    context_object_name = "floors"

    def get_queryset(self):
        self.project = get_object_or_404(Project, pk=self.kwargs["project_pk"])
        return self.project.floors.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class ProjectFloorCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = ProjectFloor
    form_class = ProjectFloorForm
    template_name = "projects/floor_form.html"

    def test_func(self):
        project = get_object_or_404(Project, pk=self.kwargs["project_pk"])
        return self.request.user.is_admin() or self.request.user == project.manager

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = get_object_or_404(Project, pk=self.kwargs["project_pk"])
        return context

    def form_valid(self, form):
        form.instance.project_id = self.kwargs["project_pk"]
        response = super().form_valid(form)
        messages.success(self.request, f"Floor {self.object.floor_number} created successfully.")
        return response

    def get_success_url(self):
        return reverse_lazy(
            "projects:project_floors",
            kwargs={"project_pk": self.kwargs["project_pk"]},
        )


class BudgetVsActualAPI(LoginRequiredMixin, UserPassesTestMixin, View):
    """Return the total project budget, actual cost, and variance."""

    def test_func(self):
        project_id = self.request.GET.get("project_id")
        if not project_id:
            return False

        project = get_object_or_404(Project, id=project_id)
        return self.request.user.is_admin() or self.request.user == project.manager

    def get(self, request, *args, **kwargs):
        project = get_object_or_404(Project, id=request.GET.get("project_id"))
        totals = project.cost_budgets.aggregate(
            total_budget=Sum("budgeted_total"),
            total_actual=Sum("actual_total"),
        )

        total_budget = totals["total_budget"] or 0
        total_actual = totals["total_actual"] or 0
        variance = total_actual - total_budget
        variance_percentage = (variance / total_budget * 100) if total_budget else 0

        return JsonResponse(
            {
                "total_budget": float(total_budget),
                "total_actual": float(total_actual),
                "variance": float(variance),
                "variance_percentage": round(float(variance_percentage), 2),
            }
        )
