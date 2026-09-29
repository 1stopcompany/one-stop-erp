"""Project start-up flow pages: insurance -> tender documents -> approved drawings -> schedule -> plans."""
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import workflow
from .forms_workflow import (
    ProjectInsuranceForm, ProjectTenderDocumentForm, ProjectRegulatoryApprovalForm,
    ProjectManagementPlanForm, SiteManagementChecklistForm,
)
from .models import (
    Project, ProjectInsurance, ProjectStage, ProjectTenderDocument,
    ProjectRegulatoryApproval, ProjectManagementPlan,
)

MANAGE_DENIED = "Only the project manager, engineering manager or an admin can do this."


def can_view_project(user, project):
    if user.is_admin():
        return True
    if user.is_project_manager():
        return project.manager_id == user.id
    if user.is_site_engineer():
        return project.site_engineer_id == user.id
    return True  # engineering / general managers, procurement: company-wide, like the project detail page


def can_manage_workflow(user, project):
    """Add insurance/tender documents and complete stages: admin, engineering manager, the project's manager."""
    return user.is_admin() or user.is_engineering_manager() or (
        user.is_project_manager() and project.manager_id == user.id
    )


def _visible_project(request, pk):
    """(project, None) if the user may see it, else (project, 403 response)."""
    project = get_object_or_404(Project, pk=pk)
    if can_view_project(request.user, project):
        return project, None
    return project, HttpResponseForbidden("You can't see this project.")


@login_required
def workflow_view(request, pk):
    project, denied = _visible_project(request, pk)
    if denied:
        return denied
    board = workflow.stage_board(project)
    Blueprint = apps.get_model("blueprints", "Blueprint")
    ScheduleTask = apps.get_model("reports", "ScheduleTask")
    blueprints = list(Blueprint.objects.filter(project=project).prefetch_related("revisions"))
    plans_by_category = {p.category: p for p in project.management_plans.all()}
    plan_rows = [
        {"category": category, "label": label, "plan": plans_by_category.get(category)}
        for category, label in ProjectManagementPlan.CATEGORIES
    ]
    site_plan = plans_by_category.get(ProjectManagementPlan.SITE_MANAGEMENT)
    return render(request, "projects/workflow.html", {
        "project": project,
        "board": board,
        "insurances": project.insurances.all(),
        "tender_documents": project.tender_documents.all(),
        "drawings_total": len(blueprints),
        "drawings_approved": sum(1 for b in blueprints if any(r.status == "approved" for r in b.revisions.all())),
        "regulatory_approvals": project.regulatory_approvals.all(),
        "regulatory_bodies": ProjectRegulatoryApproval.BODIES,
        "missing_regulatory_bodies": workflow.missing_regulatory_bodies(project),
        "schedule_task_count": ScheduleTask.objects.filter(project=project).count(),
        "plan_rows": plan_rows,
        "site_plan": site_plan,
        "checklist_form": SiteManagementChecklistForm(instance=site_plan) if site_plan else None,
        "can_manage": can_manage_workflow(request.user, project),
        "flow_complete": all(row["done"] for row in board),
    })


def _document_form_page(request, project, form_class, title, key):
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden(MANAGE_DENIED)
    try:
        workflow.require_unlocked(project, key)
    except workflow.WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect("projects:workflow", pk=project.pk)
    form = form_class(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.project = project
        obj.uploaded_by = request.user
        obj.save()
        messages.success(request, f"{title} saved.")
        return redirect("projects:workflow", pk=project.pk)
    return render(request, "projects/workflow_form.html", {"form": form, "project": project, "title": title})


@login_required
def insurance_add(request, pk):
    project, denied = _visible_project(request, pk)
    return denied or _document_form_page(request, project, ProjectInsuranceForm, "Insurance policy", ProjectStage.INSURANCE)


@login_required
def tender_add(request, pk):
    project, denied = _visible_project(request, pk)
    return denied or _document_form_page(request, project, ProjectTenderDocumentForm, "Tender document", ProjectStage.TENDER)


@login_required
def regulatory_add(request, pk):
    project, denied = _visible_project(request, pk)
    return denied or _document_form_page(request, project, ProjectRegulatoryApprovalForm, "Regulatory approval", ProjectStage.DRAWINGS)


@login_required
def plan_add(request, pk):
    project, denied = _visible_project(request, pk)
    return denied or _document_form_page(request, project, ProjectManagementPlanForm, "Project management plan", ProjectStage.PLANS)


@login_required
@require_POST
def plan_checklist_update(request, pk, plan_pk):
    project, denied = _visible_project(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden(MANAGE_DENIED)
    plan = get_object_or_404(ProjectManagementPlan, pk=plan_pk, project=project, category=ProjectManagementPlan.SITE_MANAGEMENT)
    stage = next(s for s in workflow.ensure_stages(project) if s.key == ProjectStage.PLANS)
    if stage.is_complete:
        messages.error(request, "This stage is already complete, so its checklist can't be changed.")
        return redirect("projects:workflow", pk=project.pk)
    form = SiteManagementChecklistForm(request.POST, instance=plan)
    if form.is_valid():
        form.save()
        messages.success(request, "Site logistics checklist updated.")
    else:
        messages.error(request, "Couldn't save the checklist.")
    return redirect("projects:workflow", pk=project.pk)


def _delete_document(request, pk, model, doc_pk, key):
    project, denied = _visible_project(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden(MANAGE_DENIED)
    doc = get_object_or_404(model, pk=doc_pk, project=project)
    stage = next(s for s in workflow.ensure_stages(project) if s.key == key)
    if stage.is_complete:
        messages.error(
            request,
            "This stage is already complete, so its documents can't be deleted. Upload the new document instead.",
        )
    else:
        doc.document.delete(save=False)
        doc.delete()
        messages.success(request, "Document deleted.")
    return redirect("projects:workflow", pk=project.pk)


@login_required
@require_POST
def insurance_delete(request, pk, doc_pk):
    return _delete_document(request, pk, ProjectInsurance, doc_pk, ProjectStage.INSURANCE)


@login_required
@require_POST
def tender_delete(request, pk, doc_pk):
    return _delete_document(request, pk, ProjectTenderDocument, doc_pk, ProjectStage.TENDER)


@login_required
@require_POST
def regulatory_delete(request, pk, doc_pk):
    return _delete_document(request, pk, ProjectRegulatoryApproval, doc_pk, ProjectStage.DRAWINGS)


@login_required
@require_POST
def plan_delete(request, pk, doc_pk):
    return _delete_document(request, pk, ProjectManagementPlan, doc_pk, ProjectStage.PLANS)


@login_required
@require_POST
def stage_complete(request, pk, key):
    project, denied = _visible_project(request, pk)
    if denied:
        return denied
    if not can_manage_workflow(request.user, project):
        return HttpResponseForbidden(MANAGE_DENIED)
    if key not in workflow.ORDER:
        return redirect("projects:workflow", pk=project.pk)
    try:
        stage = workflow.complete_stage(project, key, request.user)
    except workflow.WorkflowError as exc:
        messages.error(request, str(exc))
    else:
        if key == workflow.ORDER[-1]:
            messages.success(request, f"{project.name} is now Active -- work can start and reports can be created.")
        else:
            messages.success(request, f"'{stage.get_key_display()}' complete. The next stage is now open.")
    return redirect("projects:workflow", pk=project.pk)
