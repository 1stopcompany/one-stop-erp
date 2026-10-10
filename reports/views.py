"""
Reports Views - Unified Daily and Monthly Reporting System

This module contains all views for creating, viewing, and managing both
daily and monthly construction reports.
"""

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.db.models import Q
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from projects import readiness
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from datetime import timedelta
import calendar
from dateutil.relativedelta import relativedelta

from .models import (
    DailyReport, DailyWorkForce, DailyEquipment, DailyActivity, DailyMaterial, DailyVisitor,
    MonthlyReport, FloorActivity, ExternalWork, MaterialSupply, UpcomingWork, ReportAttachment
)
from .services.monthly_report_generator import (
    generate_monthly_report as generate_monthly_report_from_daily_data,
    MonthlyReportGenerationError,
    compute_dashboard_data,
)
from .services.cost_estimator import compute_cost_estimate
from .services.internal_report_data import compute_internal_report_data
from .master_data_models import LaborClassification, EquipmentMaster
from .progress_models import ProjectPhase, ProjectPhaseSubItem, ProjectPhasePhoto, ProjectMilestone, calculate_project_progress
from .forms import (
    DailyReportForm, DailyWorkForceForm, DailyEquipmentForm, DailyActivityForm, DailyMaterialForm, DailyVisitorForm,
    MonthlyReportForm, FloorActivityForm, ExternalWorkForm, MaterialSupplyForm, UpcomingWorkForm,
    OwnerFinancialReportForm,
)
from projects.models import Project
from accounts.models import UserAuditLog
from .models import MonthlyWorkForce
from .owner_financial_models import OwnerFinancialReport, OwnerReportPhaseUpdate, OwnerReportPriceComparisonItem
from timesheets.models import Employee, DailyWorker
from django.http import JsonResponse


# ==================== TWO-STAGE APPROVAL (Engineering Manager -> General Manager) ====================
#
# Every report type shares the same workflow: draft -> submitted ->
# engineering_approved -> approved (or rejected at either review stage).
# The Engineering Manager and General Manager act company-wide, across
# every project, not scoped to one project like site engineers/PMs.
# These two helpers implement the shared logic once; the thin
# per-report-type view functions below just supply the right model/URLs.

def _report_type_config(report_type):
    return {
        'daily': {
            'model': DailyReport, 'content_type': 'DailyReport',
            'detail_url': 'reports:daily_report_detail',
            'review_template': 'reports/review_report.html',
            'approve_template': 'reports/approve_daily_report.html',
            'label': 'Daily Report',
        },
        'monthly': {
            'model': MonthlyReport, 'content_type': 'MonthlyReport',
            'detail_url': 'reports:monthly_report_detail',
            'review_template': 'reports/review_report.html',
            'approve_template': 'reports/approve_monthly_report.html',
            'label': 'Monthly Report',
        },
        'owner_financial': {
            'model': OwnerFinancialReport, 'content_type': 'OwnerFinancialReport',
            'detail_url': 'reports:owner_financial_report_detail',
            'review_template': 'reports/review_report.html',
            'approve_template': 'reports/approve_owner_financial_report.html',
            'label': 'Owner Financial Report',
        },
    }[report_type]


def _review_report(request, pk, report_type):
    """Engineering Manager's review stage: submitted -> engineering_approved (or rejected)."""
    config = _report_type_config(report_type)
    report = get_object_or_404(config['model'], pk=pk)

    if not (request.user.is_engineering_manager() or request.user.is_admin()):
        messages.error(request, 'Only the engineering manager can review this report.')
        return redirect(config['detail_url'], pk=pk)

    if request.method == 'POST':
        if report.status != 'submitted':
            messages.error(request, 'Only submitted reports can be reviewed.')
            return redirect(config['detail_url'], pk=pk)

        action = request.POST.get('action')
        report.reviewed_by = request.user
        report.review_date = timezone.now()

        if action == 'approve':
            report.status = 'engineering_approved'
            report.rejection_reason = ''
            report.save()
            UserAuditLog.objects.create(
                user=request.user, action='approve', content_type=config['content_type'],
                object_id=report.id, description=f"Engineering review approved {report.report_number}",
                ip_address=get_client_ip(request),
            )
            messages.success(request, 'Report approved and forwarded to the general manager.')
        elif action == 'reject':
            report.status = 'rejected'
            report.rejection_reason = request.POST.get('rejection_reason', '').strip()
            report.save()
            UserAuditLog.objects.create(
                user=request.user, action='reject', content_type=config['content_type'],
                object_id=report.id, description=f"Engineering review rejected {report.report_number}",
                ip_address=get_client_ip(request),
            )
            messages.warning(request, 'Report rejected and sent back to the creator.')
        return redirect(config['detail_url'], pk=pk)

    return render(request, config['review_template'], {'report': report, 'report_type_label': config['label']})


def _final_approve_report(request, pk, report_type):
    """General Manager's final stage: engineering_approved -> approved (or rejected)."""
    config = _report_type_config(report_type)
    report = get_object_or_404(config['model'], pk=pk)

    if not (request.user.is_general_manager() or request.user.is_admin()):
        messages.error(request, 'Only the general manager can give final approval.')
        return redirect(config['detail_url'], pk=pk)

    if request.method == 'POST':
        if report.status != 'engineering_approved':
            messages.error(request, 'Only reports already approved by the engineering manager can receive final approval.')
            return redirect(config['detail_url'], pk=pk)

        action = request.POST.get('action')
        if action == 'approve':
            report.status = 'approved'
            report.approved_by = request.user
            report.approval_date = timezone.now()
            report.rejection_reason = ''
            report.save()
            UserAuditLog.objects.create(
                user=request.user, action='approve', content_type=config['content_type'],
                object_id=report.id, description=f"Final approval given for {report.report_number}",
                ip_address=get_client_ip(request),
            )
            messages.success(request, 'Report given final approval.')
        elif action == 'reject':
            report.status = 'rejected'
            report.approved_by = request.user
            report.rejection_reason = request.POST.get('rejection_reason', '').strip()
            report.save()
            UserAuditLog.objects.create(
                user=request.user, action='reject', content_type=config['content_type'],
                object_id=report.id, description=f"Final approval rejected for {report.report_number}",
                ip_address=get_client_ip(request),
            )
            messages.warning(request, 'Report rejected.')
        return redirect(config['detail_url'], pk=pk)

    return render(request, config['approve_template'], {'report': report})


# ==================== REPORT TYPE SELECTION ====================

@login_required
@require_http_methods(["GET"])
def report_type_selection(request):
    """
    Report type selection view

    Site engineers create Daily reports; project managers create Monthly
    (EDGE) and Owner Financial reports. Admins can reach all three.
    """
    can_create_daily = request.user.is_site_engineer() or request.user.is_admin()
    can_create_monthly = request.user.is_project_manager() or request.user.is_admin()
    can_view_approvals = request.user.is_engineering_manager() or request.user.is_general_manager() or request.user.is_admin()
    if not (can_create_daily or can_create_monthly or can_view_approvals):
        messages.error(request, 'You do not have permission to access reports.')
        return redirect('dashboard')

    def _scoped(model):
        """Scope a report queryset by role, same rule the list views use."""
        qs = model.objects.all()
        # is_admin() must be checked first: it's also true for any Django
        # superuser regardless of their `role` value (see its docstring),
        # so an admin whose role happens to be e.g. 'site_engineer' isn't
        # wrongly scoped down to only reports they personally authored.
        if request.user.is_admin():
            pass
        elif request.user.is_site_engineer():
            qs = qs.filter(site_engineer=request.user)
        elif request.user.is_project_manager():
            qs = qs.filter(project__manager=request.user)
        return qs

    daily_qs = _scoped(DailyReport)
    monthly_qs = _scoped(MonthlyReport)
    owner_qs = _scoped(OwnerFinancialReport)

    context = {
        'can_create_daily': can_create_daily,
        'can_create_monthly': can_create_monthly,
        'can_view_approvals': can_view_approvals,
        'projects': Project.objects.all().order_by('-created_at'),
        # The template's stat cards (daily/monthly totals + pending/approved
        # across all three report types) read these directly -- they used
        # to always render blank because this view never populated them.
        'daily_total_reports': daily_qs.count(),
        'total_reports': monthly_qs.count(),
        'pending_reports': (
            daily_qs.filter(status='submitted').count()
            + monthly_qs.filter(status='submitted').count()
            + owner_qs.filter(status='submitted').count()
        ),
        'approved_reports': (
            daily_qs.filter(status='approved').count()
            + monthly_qs.filter(status='approved').count()
            + owner_qs.filter(status='approved').count()
        ),
        # The template's "Recent Daily/Monthly Reports" tables read these
        # directly -- they used to always render the "No reports yet" empty
        # state because this view never populated them.
        'recent_reports': monthly_qs.select_related('project').order_by('-created_at')[:5],
        'recent_daily_reports': daily_qs.select_related('project').order_by('-created_at')[:5],
    }

    # A project manager's own view of what is stuck with management: every report on the
    # projects they manage that is still waiting on the engineering manager's review
    # ('submitted') or the general manager's final approval ('engineering_approved').
    if request.user.is_project_manager():
        waiting = []
        for label, model, detail_url in (
            ('Daily', DailyReport, 'reports:daily_report_detail'),
            ('Monthly', MonthlyReport, 'reports:monthly_report_detail'),
            ('Owner Financial', OwnerFinancialReport, 'reports:owner_financial_report_detail'),
        ):
            reports = model.objects.filter(
                project__manager=request.user, status__in=['submitted', 'engineering_approved'],
            ).select_related('project')
            for report in reports:
                waiting.append({
                    'type_label': label, 'report': report, 'detail_url': detail_url,
                    'waiting_for': 'Engineering manager review' if report.status == 'submitted'
                    else 'General manager final approval',
                    'since': report.review_date if report.status == 'engineering_approved' and report.review_date
                    else report.created_at,
                })
        waiting.sort(key=lambda row: row['since'])  # oldest first: the ones waiting longest
        context['awaiting_management'] = waiting
    return render(request, 'reports/report_type_selection.html', context)



@login_required
@require_http_methods(["GET"])
def select_project_for_report(request, report_type):
    """
    Project selection view for creating a new report
    """
    if report_type not in ['daily', 'monthly', 'owner_financial']:
        messages.error(request, 'Invalid report type.')
        return redirect('reports:report_type_selection')

    # Daily reports are the site engineer's own; Monthly/Owner Financial
    # are the project manager's -- see the roles agreed for this app.
    if report_type == 'daily':
        if not (request.user.is_site_engineer() or request.user.is_admin()):
            messages.error(request, 'Only site engineers can create daily reports.')
            return redirect('reports:report_type_selection')
        projects = Project.objects.filter(status='active', pk__in=readiness.ready_projects().values('pk'))
        if not request.user.is_admin():
            projects = projects.filter(site_engineer=request.user)
    else:
        if not (request.user.is_project_manager() or request.user.is_admin()):
            messages.error(request, 'Only project managers can create this report type.')
            return redirect('reports:report_type_selection')
        projects = Project.objects.filter(status='active', pk__in=readiness.ready_projects().values('pk'))
        if not request.user.is_admin():
            projects = projects.filter(manager=request.user)

    projects = projects.order_by('-created_at')

    context = {
        'report_type': report_type,
        'projects': projects,
    }
    return render(request, 'reports/select_project.html', context)


# ==================== DAILY REPORT VIEWS ====================

class DailyReportListView(LoginRequiredMixin, ListView):
    """List daily reports"""
    model = DailyReport
    template_name = 'reports/daily_report_list.html'
    context_object_name = 'reports'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = DailyReport.objects.all()
        
        # Filter based on user role
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        
        # Apply search and filters
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        project = self.request.GET.get('project')
        
        if search:
            queryset = queryset.filter(
                Q(report_number__icontains=search) |
                Q(project__name__icontains=search)
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        if project:
            queryset = queryset.filter(project_id=project)
        
        return queryset.order_by('-report_date', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = 'daily'
        projects = Project.objects.all()
        if not self.request.user.is_admin() and self.request.user.is_site_engineer():
            projects = projects.filter(site_engineer=self.request.user)
        context['projects'] = projects
        return context


class DailyReportDetailView(LoginRequiredMixin, DetailView):
    """View daily report details"""
    model = DailyReport
    template_name = 'reports/daily_report_detail.html'
    context_object_name = 'report'

    def get_queryset(self):
        queryset = DailyReport.objects.all()
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        # The template reads these as bare context variables (`equipment`,
        # `materials`, `visitors`) rather than `report.equipment.all` etc.,
        # so without this they silently render as empty regardless of the
        # report's actual data. (The old free-text `DailyActivity` log --
        # `activities` -- was removed from the UI as a duplicate of the
        # BOQ-linked "Daily Works / Progress" section; DailyActivity itself
        # is kept for monthly_report_generator's historical narrative text.)
        context['equipment'] = report.equipment.all()
        context['materials'] = report.daily_materials.all()
        context['visitors'] = report.visitors.all()
        # "Add Equipment" links a piece of equipment to one of this report's own logged
        # activities (DailyReportActivityProgress, the BOQ-linked "Daily Works / Progress"
        # entries), and to a real equipment master record instead of a free-text name.
        context['equipment_master_list'] = EquipmentMaster.objects.filter(is_active=True).order_by('name')
        context['equipment_categories'] = sorted({c for c in EquipmentMaster.objects.exclude(category='').values_list('category', flat=True)})
        context['activity_progress_entries'] = report.activity_progress_entries.all()
        # ReportAttachment isn't a direct FK on DailyReport (it supports
        # both report types via report_type/report_id), so it needs an
        # explicit queryset rather than report.attachments.all().
        context['attachments'] = ReportAttachment.objects.filter(
            report_type='daily', report_id=report.id
        ).order_by('order', 'created_at')
        context['labor_classifications'] = LaborClassification.objects.filter(is_active=True)
        from .master_data_models import WorkforceCategory
        context['workforce_categories'] = WorkforceCategory.objects.filter(is_active=True).order_by('order', 'name')
        context['phase_sub_items'] = ProjectPhaseSubItem.objects.filter(
            phase__project=report.project
        ).select_related('phase')
        # HR employees who can show up in "Add Worker Attendance" -- not just those explicitly
        # assigned to this project (Employee.project), but also this project's own manager and
        # site engineer, whose HR record's `project` field is often unset even though they
        # clearly belong here (they run it). Without the OR, the very people most likely to mark
        # their own presence -- the site engineer filling out the report, the project manager --
        # could be missing from the list entirely.
        relevant_user_ids = [uid for uid in [report.project.manager_id, report.project.site_engineer_id] if uid]
        # ...and since an engineer must be able to put ANY employee who worked with them on the sheet (a driver from the office, a
        # technician lent from another project), the picker offers every active employee: this project's people first, the rest after.
        own_ids = set(Employee.objects.filter(
            Q(project=report.project) | Q(user_id__in=relevant_user_ids), employment_status='active'
        ).values_list('pk', flat=True))
        everyone = list(Employee.objects.filter(employment_status='active')
                        .select_related('position__default_labor_classification').order_by('first_name', 'last_name'))
        for emp in everyone:
            emp.on_this_project = emp.pk in own_ids
        everyone.sort(key=lambda e: (not e.on_this_project, e.first_name, e.last_name))
        context['project_employees'] = everyone
        # the attendance rows split in two tables: HR employees, and the day-labor workers
        attendance = list(report.worker_attendance.select_related('employee', 'crew', 'labor_classification').order_by('worker_name'))
        context['attendance_employees'] = [a for a in attendance if a.employee_id]
        context['attendance_workers'] = [a for a in attendance if not a.employee_id]
        context['attendance_employees_hours'] = sum((a.total_hours or 0 for a in context['attendance_employees']), 0)
        context['attendance_workers_hours'] = sum((a.total_hours or 0 for a in context['attendance_workers']), 0)
        # Day laborers (no HR record) are picked from this shared, reusable roster instead of
        # typing a fresh name on every report -- see DailyReportWorkerAttendance.daily_worker
        # and api_views.add_daily_worker for adding one that isn't on it yet.
        context['daily_workers'] = DailyWorker.objects.filter(is_active=True).order_by('full_name')
        # Active subcontractor agreements on this project -- offered when creating a Crew, so a
        # subcontracted crew's contractor name comes from the real agreement/vendor instead of
        # being retyped, and shows up in Cost Control exactly like the agreement's other costs do.
        from subcontractors.models import SubcontractorAgreement
        context['subcontractor_agreements'] = SubcontractorAgreement.objects.filter(
            project=report.project, status='active'
        ).select_related('vendor')
        # Named crews already logged on this report, for the "Crew" picker on Add Worker
        # Attendance -- lets several workers share one activity/contractor set once on the crew.
        context['crews'] = report.crews.select_related('activity', 'agreement__vendor').all()
        # Today's labor cost vs. the work it produced, grouped by the activity each crew is
        # executing -- see services/daily_labor_summary.py for the cost estimate basis.
        from .services.daily_labor_summary import daily_labor_productivity_summary
        context['labor_productivity_summary'] = daily_labor_productivity_summary(report)
        # This user's own saved section order (from the accordion's move-up/move-down controls),
        # or None to use the page's built-in default order -- see api_views.save_daily_report_section_order.
        context['section_order'] = self.request.user.daily_report_section_order or []
        # One row per distinct activity name already logged on this project (most recent report
        # first), so "Add Activity Progress" offers a history list instead of retyping the same
        # activity's description fresh every day -- picking one also previews how much of it is
        # cumulatively done so far, from that row's own (already auto-calculated) quantity_cumulative.
        from .daily_detail_models import DailyReportActivityProgress
        seen_activity_names = set()
        activity_history = []
        for entry in DailyReportActivityProgress.objects.filter(
            report__project=report.project
        ).exclude(report=report).order_by('activity_description', '-report__report_date', '-id'):
            if entry.activity_description in seen_activity_names:
                continue
            seen_activity_names.add(entry.activity_description)
            activity_history.append(entry)
        context['activity_history'] = activity_history
        return context


def _redirect_if_requested_project_unusable(request, assigned_queryset):
    """
    The "Create Report" link on a project page passes ?project=<id> to pre-select it on the create
    form. If that project isn't in the field's own allowed queryset -- not ready yet, or this user
    isn't assigned to it -- Django's ModelChoiceField silently drops the initial value and the
    picker falls back to whichever project happens to be first, with nothing on screen explaining
    why the project the user came from isn't the one shown. Catch that here and send them back with
    a clear reason instead, the same way the readiness middleware would if the save itself were blocked.
    Returns a redirect response, or None if the request should proceed to the form as normal.
    """
    project_id = request.GET.get('project')
    if not project_id:
        return None
    project = Project.objects.filter(pk=project_id).first()
    if not project:
        return None
    result = readiness.check(project)
    if not result.ok and not request.user.is_admin():
        messages.error(request, f"Can't create a report for '{project.name}' yet: {result.summary()}")
        return redirect('projects:workflow', pk=project.pk)
    if not request.user.is_admin() and not assigned_queryset.filter(pk=project.pk).exists():
        messages.error(request, f"You aren't assigned to '{project.name}', so it can't be picked here.")
        return redirect('projects:project_detail', pk=project.pk)
    return None


class DailyReportCreateView(LoginRequiredMixin, CreateView):
    """Create a new daily report"""
    model = DailyReport
    form_class = DailyReportForm
    template_name = 'reports/daily_report_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_site_engineer() or request.user.is_admin()):
            messages.error(request, 'Only site engineers can create daily reports.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        redirected = _redirect_if_requested_project_unusable(request, Project.objects.filter(site_engineer=request.user))
        if redirected:
            return redirected
        return super().get(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Not just hiding options in the picker page -- restrict the
        # form's own project field so a submitted project_id for a
        # project this engineer isn't assigned to is rejected server-side.
        if not self.request.user.is_admin():
            form.fields['project'].queryset = Project.objects.filter(site_engineer=self.request.user)
        form.fields['project'].queryset = form.fields['project'].queryset.filter(pk__in=readiness.ready_projects().values('pk'))
        return form

    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
        initial['site_engineer'] = self.request.user
        return initial

    def form_valid(self, form):
        form.instance.site_engineer = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Daily report created successfully.')
        return response

    def get_success_url(self):
        return reverse_lazy('reports:daily_report_detail', kwargs={'pk': self.object.pk})


class DailyReportUpdateView(LoginRequiredMixin, UpdateView):
    """Update a daily report (draft only)"""
    model = DailyReport
    form_class = DailyReportForm
    template_name = 'reports/daily_report_form.html'
    
    def get_queryset(self):
        if self.request.user.is_admin():
            return DailyReport.objects.filter(status='draft')
        return DailyReport.objects.filter(
            site_engineer=self.request.user,
            status='draft'
        )
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Daily report updated successfully.')
        return response
    
    def get_success_url(self):
        return reverse_lazy('reports:daily_report_detail', kwargs={'pk': self.object.pk})


@login_required
@require_http_methods(["POST"])
def submit_daily_report(request, pk):
    """Submit a daily report for approval"""
    report = get_object_or_404(DailyReport, pk=pk)

    if not (report.site_engineer == request.user or request.user.is_admin()):
        messages.error(request, 'Only the report\'s author (or an admin) can submit it.')
        return redirect('reports:daily_report_detail', pk=pk)

    if report.status != 'draft':
        messages.error(request, 'Only draft reports can be submitted.')
        return redirect('reports:daily_report_detail', pk=pk)
    
    report.status = 'submitted'
    report.save()
    
    # Log the action
    UserAuditLog.objects.create(
        user=request.user,
        action='submit',
        content_type='DailyReport',
        object_id=report.id,
        description=f'Submitted daily report {report.report_number}',
        ip_address=get_client_ip(request),
    )
    
    messages.success(request, 'Daily report submitted for approval.')
    return redirect('reports:daily_report_detail', pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def review_daily_report(request, pk):
    """Engineering manager's review stage for a daily report"""
    return _review_report(request, pk, 'daily')


@login_required
@require_http_methods(["GET", "POST"])
def approve_daily_report(request, pk):
    """General manager's final approval stage for a daily report"""
    return _final_approve_report(request, pk, 'daily')


@login_required
@require_http_methods(["GET"])
def export_daily_pdf(request, pk):
    """Export daily report to PDF"""
    report = get_object_or_404(DailyReport, pk=pk)
    
    # Check permissions (is_admin() always bypasses -- see the note on the
    # shared _scoped() helper above about why it must be checked first)
    if request.user.is_admin():
        pass
    elif request.user.is_site_engineer() and report.site_engineer != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:daily_report_detail', pk=pk)
    elif request.user.is_project_manager() and report.project.manager != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:daily_report_detail', pk=pk)
    
    from .utils import generate_daily_report_pdf
    
    pdf_content = generate_daily_report_pdf(report)
    
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="DCR-{report.report_number}.pdf"'
    
    return response


# ==================== MONTHLY REPORT VIEWS ====================

class MonthlyReportListView(LoginRequiredMixin, ListView):
    """List monthly reports"""
    model = MonthlyReport
    template_name = 'reports/monthly_report_list.html'
    context_object_name = 'reports'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = MonthlyReport.objects.all()
        
        # Filter based on user role
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        
        # Apply search and filters
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        project = self.request.GET.get('project')
        
        if search:
            queryset = queryset.filter(
                Q(report_number__icontains=search) |
                Q(project__name__icontains=search)
            )
        
        if status:
            queryset = queryset.filter(status=status)
        
        if project:
            queryset = queryset.filter(project_id=project)
        
        return queryset.order_by('-reporting_period_to', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = 'monthly'
        projects = Project.objects.all()
        if not self.request.user.is_admin() and self.request.user.is_project_manager():
            projects = projects.filter(manager=self.request.user)
        context['projects'] = projects
        return context


# Built-in display order for the monthly report page's collapsible
# sections, used whenever a report's own MonthlyReport.section_order is
# blank or (after a code change removes/renames a section) incomplete.
# Ids use underscores, not hyphens -- the template looks each one up as
# section_positions.<id>, and Django's template dotted-variable syntax
# can't parse a hyphen as part of a dict key (it reads as subtraction).
# The DOM element ids for these sections (e.g. "tab-hse-qc") keep hyphens
# and are unrelated to these ids -- only the collapse toggle wiring uses
# those, never a template dict lookup.
# "floors" (Floor Activities) is intentionally not listed here -- that
# section was removed from the page; see monthly_report_reorder_section
# in api_views.py for how a stored order gets sanitized against this list.
MONTHLY_REPORT_DEFAULT_SECTION_ORDER = [
    'overview', 'progress', 'activities', 'materials', 'external',
    'hse_qc', 'issues', 'upcoming', 'boq', 'photos', 'appendix',
    'review_comments', 'approvals',
]


def resolve_monthly_section_order(report):
    """
    The report's custom section order (Move Up/Down on each section),
    sanitized against MONTHLY_REPORT_DEFAULT_SECTION_ORDER: unknown ids
    (e.g. a removed section) are dropped, and any current section missing
    from a stored order (e.g. a newly added section) is appended at the
    end, so every valid id appears exactly once regardless of what's saved.
    """
    stored = [s.strip() for s in (report.section_order or '').split(',') if s.strip()]
    known = set(MONTHLY_REPORT_DEFAULT_SECTION_ORDER)
    ordered = [s for s in stored if s in known]
    ordered += [s for s in MONTHLY_REPORT_DEFAULT_SECTION_ORDER if s not in ordered]
    return ordered


class MonthlyReportDetailView(LoginRequiredMixin, DetailView):
    """View monthly report details"""
    model = MonthlyReport
    template_name = 'reports/monthly_report_detail.html'
    context_object_name = 'report'

    def get_queryset(self):
        queryset = MonthlyReport.objects.all()
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        # The "Add Photo" modal needs the project's phases to populate its
        # phase picker (EDGE report's "Photographic Record" section).
        context['project_phases'] = report.project.phases.all().order_by('order', 'code')
        # "BOQ Progress Breakdown by Item" (EDGE report, Section 10) -- the
        # same cumulative phase/sub-item progress calculation already used
        # for the Owner Financial report.
        context['progress_breakdown'] = calculate_project_progress(
            report.project, as_of_date=report.reporting_period_to,
        )
        # "Progress This Month" (EDGE report, Section 3) -- the delta
        # between this period's and the previous period's cumulative %,
        # computed on the fly so it can never drift from the BOQ data.
        previous_progress = calculate_project_progress(
            report.project, as_of_date=report.reporting_period_from - timedelta(days=1),
        )
        context['progress_previous_percentage'] = previous_progress['overall_percentage']
        context['progress_this_month_percentage'] = (
            context['progress_breakdown']['overall_percentage'] - previous_progress['overall_percentage']
        )
        # Appendix -- supporting documents attached directly to this report.
        context['monthly_attachments'] = ReportAttachment.objects.filter(
            report_type='monthly', report_id=report.id
        ).order_by('order', 'created_at')
        # "Response to Comments" tab badge count.
        context['review_comments_count'] = report.review_comments.count()
        # Whether the current user can use the Add/Edit/Delete affordances
        # on this page (mirrors _can_edit_report() in api_views.py).
        context['editable'] = report.status == 'draft' and (
            self.request.user == report.site_engineer or self.request.user.is_admin()
        )
        # HSE fields as (field_name, label, value) triples, for a compact
        # loop in the template instead of five near-identical blocks.
        context['hse_rows'] = [
            ('hse_lti_note', 'Lost Time Incidents (LTI)', report.hse_lti_note),
            ('hse_near_misses_note', 'Near Misses Reported (NM)', report.hse_near_misses_note),
            ('hse_toolbox_talks_note', 'Toolbox Talks Conducted (TBT)', report.hse_toolbox_talks_note),
            ('hse_site_inspections_note', 'Site Inspections Conducted', report.hse_site_inspections_note),
            ('hse_corrective_actions_note', 'Corrective Actions Open / Closed', report.hse_corrective_actions_note),
        ]
        # Custom section order (Move Up/Down on each section) -- a plain
        # ordered list of section ids, plus a 0-based position lookup so
        # the template can flex-order each pane and disable Move Up/Down
        # at the ends without doing index arithmetic itself.
        order = resolve_monthly_section_order(report)
        context['section_order'] = order
        context['section_positions'] = {sid: i for i, sid in enumerate(order)}
        context['section_reorderable'] = (
            self.request.user.is_admin()
            or self.request.user == report.site_engineer
            or (self.request.user.is_project_manager() and report.project.manager_id == self.request.user.id)
        )
        return context


class MonthlyReportDashboardView(LoginRequiredMixin, DetailView):
    """
    Executive dashboard for a monthly report: KPI cards + charts built
    from the same real Daily Report data the report's narrative fields
    were generated from (see services.monthly_report_generator.
    compute_dashboard_data), for presenting the period's numbers to
    management rather than reading the narrative report page.
    """
    model = MonthlyReport
    template_name = 'reports/monthly_report_dashboard.html'
    context_object_name = 'report'

    def get_queryset(self):
        queryset = MonthlyReport.objects.all()
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        data = compute_dashboard_data(report)
        context['data'] = data
        # Passed as a dict, not a pre-dumped string -- the `json_script`
        # filter in the template does its own json.dumps(); dumping it
        # here too would double-encode it into a JSON string of a JSON
        # string, which JSON.parse() in the browser can't use directly.
        context['chart_data'] = {
            'manhoursSeries': data['manhours_series'],
            'phaseProgress': data['phase_progress'],
            'activityStatusCounts': data['activity_status_counts'],
            'materials': [
                {'name': m.material_description, 'quantity': float(m.quantity), 'unit': m.unit}
                for m in data['materials']
            ],
        }
        context['cost'] = compute_cost_estimate(report)
        internal = compute_internal_report_data(report)
        context['internal'] = internal
        context['rag_display'] = [
            ('Activities & Deliverables', internal['rag']['deliverables']),
            ('HSE / Safety', internal['rag']['hse']),
            ('Schedule', internal['rag']['schedule']),
            ('Cost', internal['rag']['cost']),
            ('Risks / Issues', internal['rag']['risks']),
            ('Overall Project Status', internal['rag']['overall']),
        ]
        return context


class MonthlyReportCreateView(LoginRequiredMixin, CreateView):
    """Create a new monthly report"""
    model = MonthlyReport
    form_class = MonthlyReportForm
    template_name = 'reports/monthly_report_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_project_manager() or request.user.is_admin()):
            messages.error(request, 'Only project managers can create monthly reports.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        redirected = _redirect_if_requested_project_unusable(request, Project.objects.filter(manager=request.user))
        if redirected:
            return redirected
        return super().get(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if not self.request.user.is_admin():
            form.fields['project'].queryset = Project.objects.filter(manager=self.request.user)
        form.fields['project'].queryset = form.fields['project'].queryset.filter(pk__in=readiness.ready_projects().values('pk'))
        return form

    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
        initial['site_engineer'] = self.request.user
        return initial
    
    def form_valid(self, form):
        form.instance.site_engineer = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Monthly report created successfully.')
        return response
    
    def get_success_url(self):
        return reverse_lazy('reports:monthly_report_detail', kwargs={'pk': self.object.pk})


@login_required
def generate_monthly_report_view(request):
    """
    Generate a draft monthly report for a project/month by aggregating
    that period's real daily reports (workforce, activities, materials,
    QA/QC & HSE, BOQ progress, site events) -- see
    services.monthly_report_generator.generate_monthly_report.
    """
    if not (request.user.is_project_manager() or request.user.is_admin()):
        messages.error(request, 'Only project managers can generate monthly reports.')
        return redirect('reports:monthly_report_list')

    ready = readiness.ready_projects().values('pk')
    if request.user.is_admin():
        projects = Project.objects.filter(pk__in=ready).order_by('name')
    else:
        projects = Project.objects.filter(manager=request.user, pk__in=ready).order_by('name')

    today = timezone.localdate()
    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years = list(range(today.year - 2, today.year + 1))

    if request.method == 'POST':
        project = get_object_or_404(projects, pk=request.POST.get('project'))
        try:
            year = int(request.POST.get('year'))
            month = int(request.POST.get('month'))
        except (TypeError, ValueError):
            messages.error(request, 'Please choose a valid project, month, and year.')
            return redirect('reports:monthly_report_generate')

        try:
            report = generate_monthly_report_from_daily_data(project, year, month, request.user)
        except MonthlyReportGenerationError as exc:
            messages.error(request, str(exc))
            return redirect('reports:monthly_report_generate')

        messages.success(
            request,
            f'Draft monthly report generated for {project.name} — '
            f'{calendar.month_name[month]} {year}. Review and edit it below before submitting.'
        )
        return redirect('reports:monthly_report_update', pk=report.pk)

    return render(request, 'reports/monthly_report_generate.html', {
        'projects': projects,
        'months': months,
        'years': years,
        'current_year': today.year,
        'current_month': today.month,
    })


class MonthlyReportUpdateView(LoginRequiredMixin, UpdateView):
    """Update a monthly report (draft only)"""
    model = MonthlyReport
    form_class = MonthlyReportForm
    template_name = 'reports/monthly_report_form.html'
    
    def get_queryset(self):
        if self.request.user.is_admin():
            return MonthlyReport.objects.filter(status='draft')
        return MonthlyReport.objects.filter(
            site_engineer=self.request.user,
            status='draft'
        )
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Monthly report updated successfully.')
        return response
    
    def get_success_url(self):
        return reverse_lazy('reports:monthly_report_detail', kwargs={'pk': self.object.pk})


@login_required
@require_http_methods(["POST"])
def submit_monthly_report(request, pk):
    """Submit a monthly report for approval"""
    report = get_object_or_404(MonthlyReport, pk=pk)

    if not (report.site_engineer == request.user or request.user.is_admin()):
        messages.error(request, 'Only the report\'s author (or an admin) can submit it.')
        return redirect('reports:monthly_report_detail', pk=pk)

    if report.status != 'draft':
        messages.error(request, 'Only draft reports can be submitted.')
        return redirect('reports:monthly_report_detail', pk=pk)
    
    report.status = 'submitted'
    report.save()
    
    # Log the action
    UserAuditLog.objects.create(
        user=request.user,
        action='submit',
        content_type='MonthlyReport',
        object_id=report.id,
        description=f'Submitted monthly report {report.report_number}',
        ip_address=get_client_ip(request),
    )
    
    messages.success(request, 'Monthly report submitted for approval.')
    return redirect('reports:monthly_report_detail', pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def review_monthly_report(request, pk):
    """Engineering manager's review stage for a monthly report"""
    return _review_report(request, pk, 'monthly')


@login_required
@require_http_methods(["GET", "POST"])
def approve_monthly_report(request, pk):
    """General manager's final approval stage for a monthly report"""
    return _final_approve_report(request, pk, 'monthly')

@login_required
@require_http_methods(["POST"])
def add_monthly_workforce(request, pk):
    report = get_object_or_404(MonthlyReport, pk=pk, site_engineer=request.user)

    item = MonthlyWorkForce.objects.create(
        report=report,
        category=request.POST.get('category', '').strip(),
        designation=request.POST.get('designation', '').strip(),
        count=int(request.POST.get('count') or 0),
    )

    return JsonResponse({
        'success': True,
        'id': item.id,
        'category': item.category,
        'designation': item.designation,
        'count': item.count,
    })

@login_required
@require_http_methods(["GET"])
def export_monthly_pdf(request, pk):
    """Export monthly report to PDF"""
    report = get_object_or_404(MonthlyReport, pk=pk)
    
    # Check permissions (is_admin() always bypasses -- see the note on the
    # shared _scoped() helper above about why it must be checked first)
    if request.user.is_admin():
        pass
    elif request.user.is_site_engineer() and report.site_engineer != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_detail', pk=pk)
    elif request.user.is_project_manager() and report.project.manager != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_detail', pk=pk)
    
    from .utils import generate_report_pdf

    pdf_content = generate_report_pdf(report)
    
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="MR-{report.report_number}.pdf"'

    return response


@login_required
@require_http_methods(["GET"])
def export_monthly_dashboard_pdf(request, pk):
    """Export the monthly report's executive dashboard (KPIs/charts-as-tables) to PDF"""
    report = get_object_or_404(MonthlyReport, pk=pk)

    if request.user.is_admin():
        pass
    elif request.user.is_site_engineer() and report.site_engineer != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_dashboard', pk=pk)
    elif request.user.is_project_manager() and report.project.manager != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_dashboard', pk=pk)

    from .utils import generate_monthly_dashboard_pdf

    pdf_content = generate_monthly_dashboard_pdf(report)

    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Dashboard-{report.report_number}.pdf"'

    return response


@login_required
@require_http_methods(["GET"])
def export_internal_monthly_pdf(request, pk):
    """Export the company's internal monthly progress report (RAG summary, EVA-style progress, HSE, cost) to PDF"""
    report = get_object_or_404(MonthlyReport, pk=pk)

    if request.user.is_admin():
        pass
    elif request.user.is_site_engineer() and report.site_engineer != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_detail', pk=pk)
    elif request.user.is_project_manager() and report.project.manager != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:monthly_report_detail', pk=pk)

    from .utils import generate_internal_monthly_report_pdf

    pdf_content = generate_internal_monthly_report_pdf(report)

    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Internal-{report.report_number}.pdf"'

    return response


# ==================== OWNER FINANCIAL REPORT VIEWS ====================

class OwnerFinancialReportListView(LoginRequiredMixin, ListView):
    """List owner financial reports"""
    model = OwnerFinancialReport
    template_name = 'reports/owner_financial_report_list.html'
    context_object_name = 'reports'
    paginate_by = 20

    def get_queryset(self):
        queryset = OwnerFinancialReport.objects.all()
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)

        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        project = self.request.GET.get('project')
        if search:
            queryset = queryset.filter(
                Q(report_number__icontains=search) | Q(project__name__icontains=search)
            )
        if status:
            queryset = queryset.filter(status=status)
        if project:
            queryset = queryset.filter(project_id=project)

        return queryset.order_by('-reporting_period_to', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_type'] = 'owner_financial'
        projects = Project.objects.all()
        if not self.request.user.is_admin() and self.request.user.is_project_manager():
            projects = projects.filter(manager=self.request.user)
        context['projects'] = projects
        return context


class OwnerFinancialReportDetailView(LoginRequiredMixin, DetailView):
    """View owner financial report details, including the computed payment breakdown"""
    model = OwnerFinancialReport
    template_name = 'reports/owner_financial_report_detail.html'
    context_object_name = 'report'

    def get_queryset(self):
        queryset = OwnerFinancialReport.objects.all()
        if self.request.user.is_admin():
            pass
        elif self.request.user.is_site_engineer():
            queryset = queryset.filter(site_engineer=self.request.user)
        elif self.request.user.is_project_manager():
            queryset = queryset.filter(project__manager=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report = self.object
        context['progress_breakdown'] = report._progress_result()
        # The "Add Phase Status Update" modal needs the project's phases
        # to populate its phase picker.
        context['project_phases'] = report.project.phases.all().order_by('order', 'code')
        return context


class OwnerFinancialReportCreateView(LoginRequiredMixin, CreateView):
    """Create a new owner financial report"""
    model = OwnerFinancialReport
    form_class = OwnerFinancialReportForm
    template_name = 'reports/owner_financial_report_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_project_manager() or request.user.is_admin()):
            messages.error(request, 'Only project managers can create owner financial reports.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        redirected = _redirect_if_requested_project_unusable(request, Project.objects.filter(manager=request.user))
        if redirected:
            return redirected
        return super().get(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if not self.request.user.is_admin():
            form.fields['project'].queryset = Project.objects.filter(manager=self.request.user)
        form.fields['project'].queryset = form.fields['project'].queryset.filter(pk__in=readiness.ready_projects().values('pk'))
        return form

    def get_initial(self):
        initial = super().get_initial()
        project_id = self.request.GET.get('project')
        if project_id:
            initial['project'] = project_id
        return initial

    def form_valid(self, form):
        form.instance.site_engineer = self.request.user
        # Snapshot the project's current contract terms rather than
        # asking the user to re-enter numbers the system already knows
        # (see OwnerFinancialReportForm docstring).
        project = form.instance.project
        form.instance.contract_value_snapshot = project.contract_value or 0
        form.instance.advance_payment_value_snapshot = project.advance_payment_value or 0
        form.instance.performance_retention_rate_snapshot = project.performance_retention_rate
        response = super().form_valid(form)
        messages.success(self.request, 'Owner financial report created successfully.')
        return response

    def get_success_url(self):
        return reverse_lazy('reports:owner_financial_report_detail', kwargs={'pk': self.object.pk})


@login_required
@require_http_methods(["POST"])
def copy_owner_financial_report(request, pk):
    """
    Copy an owner financial report into a new draft for the next
    reporting period, so a project manager doesn't have to re-type the
    whole report from scratch every month. Carries over: the contract
    terms (re-snapshotted from the project's current values, in case they
    changed), the narrative text fields (as an editable starting point),
    and the phase status rows and price-comparison items (with each
    item's "new price" becoming the new report's "old price" baseline,
    and quantity carried forward as the running cumulative total -- the
    PM then uses "Add Quantity" on the new report to add just this
    period's usage on top of it, rather than re-typing the whole running
    total each month). Site photos are deliberately NOT copied -- they
    document that specific period.
    """
    source = get_object_or_404(OwnerFinancialReport, pk=pk)
    project = source.project

    if not (request.user.is_admin() or (request.user.is_project_manager() and project.manager_id == request.user.id)):
        messages.error(request, 'You do not have permission to copy this report.')
        return redirect('reports:owner_financial_report_detail', pk=pk)

    new_from = source.reporting_period_to + timedelta(days=1)
    new_to = (new_from + relativedelta(months=1)) - timedelta(days=1)

    with transaction.atomic():
        new_report = OwnerFinancialReport.objects.create(
            project=project,
            site_engineer=source.site_engineer,
            reporting_period_from=new_from,
            reporting_period_to=new_to,
            contract_value_snapshot=project.contract_value or source.contract_value_snapshot,
            advance_payment_value_snapshot=project.advance_payment_value or source.advance_payment_value_snapshot,
            performance_retention_rate_snapshot=project.performance_retention_rate,
            # Last period's amount due becomes part of this period's
            # "previous payments" once it's actually paid; pre-filling it
            # saves re-typing, and the PM can adjust it if it wasn't paid
            # in full (or at all) before submitting.
            previous_payments_total=source.previous_payments_total + source.amount_due(),
            progress_summary=source.progress_summary,
            next_month_expected_works=source.next_month_expected_works,
            next_month_expected_completion_pct=source.next_month_expected_completion_pct,
            material_price_note=source.material_price_note,
            closing_note=source.closing_note,
            status='draft',
        )

        for update in source.phase_updates.all():
            OwnerReportPhaseUpdate.objects.create(
                report=new_report, phase=update.phase, status=update.status,
                work_performed=update.work_performed, order=update.order,
            )

        for item in source.price_comparison_items.all():
            OwnerReportPriceComparisonItem.objects.create(
                report=new_report, item_type=item.item_type, item_name=item.item_name, unit=item.unit,
                # The table is cumulative from the start of the project: the quantity is carried forward as the running total
                # (the PM adds the new period's usage with "Add Quantity") and the OLD price stays the contract price the
                # difference is measured against. Only the NEW (current) price is carried as it stands; the PM changes it when
                # the market price moves. (Resetting the old price to the new one would show a zero difference.)
                quantity=item.quantity, old_unit_price=item.old_unit_price, new_unit_price=item.new_unit_price,
            )

    messages.success(
        request,
        f'New draft report {new_report.report_number} created for '
        f'{new_from.strftime("%d/%m/%Y")} – {new_to.strftime("%d/%m/%Y")}. Review and update it before submitting.'
    )
    return redirect('reports:owner_financial_report_detail', pk=new_report.pk)


class OwnerFinancialReportUpdateView(LoginRequiredMixin, UpdateView):
    """Update an owner financial report (draft only)"""
    model = OwnerFinancialReport
    form_class = OwnerFinancialReportForm
    template_name = 'reports/owner_financial_report_form.html'

    def get_queryset(self):
        if self.request.user.is_admin():
            return OwnerFinancialReport.objects.filter(status='draft')
        return OwnerFinancialReport.objects.filter(site_engineer=self.request.user, status='draft')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Owner financial report updated successfully.')
        return response

    def get_success_url(self):
        return reverse_lazy('reports:owner_financial_report_detail', kwargs={'pk': self.object.pk})


@login_required
@require_http_methods(["POST"])
def submit_owner_financial_report(request, pk):
    """Submit an owner financial report for approval"""
    report = get_object_or_404(OwnerFinancialReport, pk=pk)

    if not (report.site_engineer == request.user or request.user.is_admin()):
        messages.error(request, 'Only the report\'s author (or an admin) can submit it.')
        return redirect('reports:owner_financial_report_detail', pk=pk)

    if report.status != 'draft':
        messages.error(request, 'Only draft reports can be submitted.')
        return redirect('reports:owner_financial_report_detail', pk=pk)

    report.status = 'submitted'
    report.save()

    UserAuditLog.objects.create(
        user=request.user,
        action='submit',
        content_type='OwnerFinancialReport',
        object_id=report.id,
        description=f'Submitted owner financial report {report.report_number}',
        ip_address=get_client_ip(request),
    )

    messages.success(request, 'Owner financial report submitted for approval.')
    return redirect('reports:owner_financial_report_detail', pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def review_owner_financial_report(request, pk):
    """Engineering manager's review stage for an owner financial report"""
    return _review_report(request, pk, 'owner_financial')


@login_required
@require_http_methods(["GET", "POST"])
def approve_owner_financial_report(request, pk):
    """General manager's final approval stage for an owner financial report"""
    return _final_approve_report(request, pk, 'owner_financial')


@login_required
def export_owner_financial_pdf(request, pk):
    """Export the owner financial & technical report to PDF."""
    report = get_object_or_404(OwnerFinancialReport, pk=pk)

    # Check permissions (is_admin() always bypasses -- see the note on the
    # shared _scoped() helper above about why it must be checked first)
    if request.user.is_admin():
        pass
    elif request.user.is_site_engineer() and report.site_engineer != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:owner_financial_report_detail', pk=pk)
    elif request.user.is_project_manager() and report.project.manager != request.user:
        messages.error(request, 'You do not have permission to export this report.')
        return redirect('reports:owner_financial_report_detail', pk=pk)

    from .utils import generate_owner_financial_report_pdf

    pdf_content = generate_owner_financial_report_pdf(report)

    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="OFR-{report.report_number}.pdf"'

    return response


# ==================== APPROVALS DASHBOARD ====================

@login_required
@require_http_methods(["GET"])
def approvals_dashboard(request):
    """
    Single consolidated view of every report -- across Daily, Monthly,
    and Owner Financial, across every project -- awaiting action from
    the Engineering Manager or General Manager. This is the "see and
    control every required approval" view: neither role is scoped to
    one project like site engineers/PMs are.
    """
    user = request.user
    if not (user.is_engineering_manager() or user.is_general_manager() or user.is_admin()):
        messages.error(request, 'You do not have permission to view approvals.')
        return redirect('reports:report_type_selection')

    report_models = [
        ('daily', DailyReport, 'reports:daily_report_detail', 'reports:review_daily_report', 'reports:approve_daily_report'),
        ('monthly', MonthlyReport, 'reports:monthly_report_detail', 'reports:review_monthly_report', 'reports:approve_monthly_report'),
        ('owner_financial', OwnerFinancialReport, 'reports:owner_financial_report_detail', 'reports:review_owner_financial_report', 'reports:approve_owner_financial_report'),
    ]

    pending_review = []   # status='submitted' -- Engineering Manager's queue
    pending_approval = []  # status='engineering_approved' -- General Manager's queue

    for type_key, model, detail_url, review_url, approve_url in report_models:
        for report in model.objects.filter(status='submitted').select_related('project', 'site_engineer'):
            pending_review.append({
                'report': report, 'type': type_key, 'detail_url': detail_url, 'action_url': review_url,
            })
        for report in model.objects.filter(status='engineering_approved').select_related('project', 'site_engineer', 'reviewed_by'):
            pending_approval.append({
                'report': report, 'type': type_key, 'detail_url': detail_url, 'action_url': approve_url,
            })

    pending_review.sort(key=lambda row: row['report'].created_at, reverse=True)
    pending_approval.sort(key=lambda row: row['report'].review_date or row['report'].created_at, reverse=True)

    context = {
        'pending_review': pending_review,
        'pending_approval': pending_approval,
        'can_review': user.is_engineering_manager() or user.is_admin(),
        'can_give_final_approval': user.is_general_manager() or user.is_admin(),
    }
    return render(request, 'reports/approvals_dashboard.html', context)


# ==================== PROJECT PHASE PHOTO GALLERY ====================

@login_required
@require_http_methods(["GET"])
def phase_photo_gallery(request, project_id):
    """
    Photo gallery organized by project phase -- shared by the daily
    report, the EDGE monthly report ("Photographic Record") and the
    owner financial report ("صور المشروع") sections, since a phase photo
    isn't tied to any single report (see progress_models.ProjectPhasePhoto).
    """
    project = get_object_or_404(Project, pk=project_id)
    phases = ProjectPhase.objects.filter(project=project).prefetch_related('photos', 'sub_items')
    return render(request, 'reports/phase_photo_gallery.html', {
        'project': project,
        'phases': phases,
    })


# ==================== BOQ EDITOR ====================

@login_required
@require_http_methods(["GET"])
def boq_editor(request, project_id):
    """
    In-app editor for a project's BOQ / schedule-of-values breakdown
    (ProjectPhase + ProjectPhaseSubItem, and recording new execution %
    readings) -- the same structure that feeds the "الجدول الزمني المنجز"
    table in the Monthly and Owner Financial report PDFs. Available to the
    project's own manager (or an admin); previously only reachable through
    Django Admin, which regular project managers have no access to.
    """
    project = get_object_or_404(Project, pk=project_id)

    if not (request.user.is_admin() or request.user.is_engineering_manager()
            or (request.user.is_project_manager() and project.manager_id == request.user.id)):
        messages.error(request, 'You do not have permission to edit this project\'s BOQ.')
        return redirect('projects:project_detail', pk=project_id)

    phases = list(
        ProjectPhase.objects.filter(project=project)
        .prefetch_related('sub_items__progress_entries')
        .order_by('order', 'code')
    )
    total_weight = sum((p.weight_percentage for p in phases), Decimal('0'))
    for phase in phases:
        phase.budget_sum, phase.contract_sum = phase.budget_total(), phase.contract_total()
        phase.has_real_sub_items = any(not s.is_whole for s in phase.sub_items.all())
    total_budget = sum((p.budget_sum for p in phases), Decimal('0'))
    total_contract = sum((p.contract_sum for p in phases), Decimal('0'))

    return render(request, 'reports/boq_editor.html', {
        'project': project,
        'phases': phases,
        'total_weight': total_weight,
        'total_budget': total_budget,
        'total_contract': total_contract,
        'total_margin': total_contract - total_budget,
    })


# ==================== MILESTONE EDITOR ====================

@login_required
@require_http_methods(["GET"])
def project_schedule(request, project_id):
    """The project's schedule as a Primavera-style Gantt chart (drawn in the browser from services.schedule_view)."""
    from projects.views_workflow import can_view_project
    from django.http import HttpResponseForbidden
    from .services.schedule_view import build_schedule

    from projects.views_workflow import can_manage_workflow
    project = get_object_or_404(Project, pk=project_id)
    if not can_view_project(request.user, project):
        return HttpResponseForbidden("You can't see this project.")
    return render(request, 'reports/schedule.html', {
        'project': project, 'schedule': build_schedule(project), 'can_edit_schedule': can_manage_workflow(request.user, project),
    })


REPORT_KINDS = {
    # url kind: (model, label, list url name, detail url name)
    'daily': ('DailyReport', 'Daily report', 'reports:daily_report_list', 'reports:daily_report_detail'),
    'monthly': ('MonthlyReport', 'Monthly report', 'reports:monthly_report_list', 'reports:monthly_report_detail'),
    'owner-financial': ('OwnerFinancialReport', 'Owner financial report', 'reports:owner_financial_report_list',
                        'reports:owner_financial_report_detail'),
}


@login_required
@require_http_methods(["GET", "POST"])
def delete_report(request, kind, pk):
    """
    Permanently delete one report (daily, monthly or owner financial) -- ADMIN ONLY, whatever its status. GET shows what goes with
    it and asks for confirmation; POST deletes it and records the deletion in the audit log. Progress entries, phase photos and
    site events that point at a daily / monthly report are kept (they just lose the link to it). Uploaded files stay on disk.
    """
    from django.contrib.admin.utils import NestedObjects
    from django.db import transaction
    from django.db.models import SET_NULL
    from django.http import Http404, HttpResponseForbidden
    from django.urls import reverse
    from accounts.models import UserAuditLog

    if kind not in REPORT_KINDS:
        raise Http404
    if not request.user.is_admin():
        return HttpResponseForbidden('Only an administrator can delete a report.')
    model_name, label, list_url, detail_url = REPORT_KINDS[kind]
    model = {'DailyReport': DailyReport, 'MonthlyReport': MonthlyReport, 'OwnerFinancialReport': OwnerFinancialReport}[model_name]
    report = get_object_or_404(model, pk=pk)

    if request.method == 'POST':
        if request.POST.get('confirm') != 'yes':
            messages.error(request, 'Tick the confirmation box to delete the report.')
            return redirect(request.path)
        description = (f'{label} {report.report_number} ({report.project.project_symbol}, status {report.status}, '
                       f'{getattr(report, "report_date", "")}) deleted')
        ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR') or None)
        with transaction.atomic():
            number = report.report_number
            report.delete()
            UserAuditLog.objects.create(user=request.user, action='delete', content_type=f'reports.{model_name}', object_id=pk,
                                        description=description, ip_address=ip, user_agent=request.META.get('HTTP_USER_AGENT', '')[:500])
        messages.success(request, f'{label} {number} was deleted.')
        return redirect(list_url)

    collector = NestedObjects(using='default')
    collector.collect([report])
    removed = sorted(((m._meta.verbose_name_plural, len(objs)) for m, objs in collector.model_objs.items() if m is not model),
                     key=lambda row: -row[1])
    kept = []
    for relation in model._meta.related_objects:
        if getattr(relation.field.remote_field, 'on_delete', None) is SET_NULL:
            count = relation.related_model.objects.filter(**{relation.field.name: report}).count()
            if count:
                kept.append((relation.related_model._meta.verbose_name_plural, count))
    return render(request, 'reports/report_confirm_delete.html', {
        'report': report, 'label': label, 'removed': removed, 'kept': kept, 'back_url': reverse(detail_url, args=[pk]),
    })


@login_required
def plan_vs_actual_page(request, project_id):
    """The MS Project plan against the actual BOQ progress, phase by phase, as of a chosen date (default today)."""
    from datetime import date as _date
    from django.http import HttpResponseForbidden
    from projects.views_workflow import can_view_project
    from .services.plan_vs_actual import plan_vs_actual

    project = get_object_or_404(Project, pk=project_id)
    if not can_view_project(request.user, project):
        return HttpResponseForbidden("You can't see this project.")
    try:
        as_of = _date.fromisoformat(request.GET.get('date', ''))
    except ValueError:
        as_of = _date.today()
    return render(request, 'reports/plan_vs_actual.html', {'project': project, 'result': plan_vs_actual(project, as_of), 'as_of': as_of})


@login_required
@require_http_methods(["GET", "POST"])
def schedule_editor(request, project_id):
    """Type the project's schedule in by hand (one table); the Gantt page draws it. Same people as the workflow pages may edit."""
    from projects.views_workflow import can_manage_workflow
    from django.http import HttpResponseForbidden
    from .services import schedule_editor as editor

    project = get_object_or_404(Project, pk=project_id)
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden("Only an admin, the engineering manager or this project's manager can edit its schedule.")

    if request.method == 'POST':
        rows = editor.rows_from_post(request.POST)
        cleaned, errors = editor.clean_rows(rows, project)
        if not rows:
            errors.append('The schedule has no rows. Add at least one, or go back without saving.')
        if not errors:
            count = editor.save_rows(project, cleaned)
            messages.success(request, f'Schedule saved ({count} rows).')
            return redirect('reports:project_schedule', project_id=project.pk)
        for error in errors:
            messages.error(request, error)
    else:
        rows = editor.editor_rows(project)
    return render(request, 'reports/schedule_editor.html', {'project': project, 'rows': rows})


@login_required
@require_http_methods(["GET"])
def milestone_editor(request, project_id):
    """
    In-app editor for a project's key milestones (ProjectMilestone), each
    tied to a BOQ phase -- feeds the "Project Key Milestones" table in the
    internal monthly report PDF. Same permission model as the BOQ editor:
    the project's own manager (or an admin).
    """
    project = get_object_or_404(Project, pk=project_id)

    if not (request.user.is_admin() or (request.user.is_project_manager() and project.manager_id == request.user.id)):
        messages.error(request, 'You do not have permission to edit this project\'s milestones.')
        return redirect('projects:project_detail', pk=project_id)

    phases = (
        ProjectPhase.objects.filter(project=project)
        .prefetch_related('milestones')
        .order_by('order', 'code')
    )

    return render(request, 'reports/milestone_editor.html', {
        'project': project,
        'phases': phases,
    })


# ==================== UTILITY FUNCTIONS ====================

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
