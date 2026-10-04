"""
Engineering drawings per project, with revisions and approval. A drawing can only be
built from once one of its revisions is 'Approved for construction' -- and the first
approved drawing is what lets a project's last start-up stage (start work) be completed.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from projects import workflow
from projects.models import Project
from projects.views_workflow import can_manage_workflow, can_view_project

from .forms import BlueprintForm, RevisionForm
from .models import Blueprint, BlueprintRevision


def can_upload_drawings(user, project):
    """Upload drawings/revisions: whoever manages the project, plus its own site engineer."""
    return can_manage_workflow(user, project) or (user.is_site_engineer() and project.site_engineer_id == user.id)


def can_approve_drawings(user, project):
    return can_manage_workflow(user, project)


def _locked_redirect(request, project):
    """If drawings aren't open yet (earlier start-up stages incomplete), explain and bounce to the workflow page."""
    try:
        workflow.require_unlocked(project, "drawings")
    except workflow.WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect("projects:workflow", pk=project.pk)
    return None


@login_required
def manual_pdf(request):
    """The illustrated Arabic user guide for drawings (same idea as the Procurement / HR / Pricing guides)."""
    from .manual_pdf import generate_blueprints_manual_pdf

    response = HttpResponse(generate_blueprints_manual_pdf(), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="blueprints-user-guide.pdf"'
    return response


@login_required
def blueprints_dashboard(request):
    projects = [p for p in Project.objects.all().order_by("name") if can_view_project(request.user, p)]
    rows = []
    for project in projects:
        blueprints = list(project.blueprints.prefetch_related("revisions"))
        rows.append({
            "project": project,
            "total": len(blueprints),
            "approved": sum(1 for b in blueprints if any(r.status == "approved" for r in b.revisions.all())),
            "pending": sum(1 for b in blueprints for r in b.revisions.all() if r.status == "pending"),
            "open": workflow.is_unlocked(project, "drawings"),
        })
    return render(request, "blueprints/dashboard.html", {"rows": rows})


def _attach_ai_runs(blueprints):
    """Give every revision its latest AI analysis (materials, quantities, green data), as `revision.ai_run`."""
    from ai_assistant.models import AIRun

    revisions = [rev for bp in blueprints for rev in bp.revisions.all()]
    latest = {}
    for run in AIRun.objects.filter(source_revision__in=revisions, kind=AIRun.DRAWING_TAKEOFF).order_by("created_at"):
        latest[run.source_revision_id] = run
    for rev in revisions:
        rev.ai_run = latest.get(rev.pk)


def _analyze_on_upload(request, revision):
    """Right after a drawing is saved: read it for materials and quantities when the AI is set up (never blocks the upload)."""
    from ai_assistant import triggers

    if triggers.auto_analyze_revision(revision, request.user):
        messages.info(request, "The AI Assistant is reading this drawing for materials, quantities and green-building data. The result will show next to it here.")


@login_required
def project_drawings(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_view_project(request.user, project):
        return HttpResponseForbidden("You can't see this project.")
    blueprints = list(project.blueprints.prefetch_related("revisions__uploaded_by", "revisions__reviewed_by"))
    from ai_assistant import jobs, llm, views as ai_views
    jobs.recover_stale_runs(minutes=15)  # an analysis whose worker died must not show "Analyzing..." forever
    _attach_ai_runs(blueprints)
    return render(request, "blueprints/project_drawings.html", {
        "project": project,
        "blueprints": blueprints,
        "can_analyze": ai_views.can_import(request.user, project),
        "ai_configured": llm.is_configured(),
        "unlocked": workflow.is_unlocked(project, "drawings"),
        "can_upload": can_upload_drawings(request.user, project),
        "can_approve": can_approve_drawings(request.user, project),
    })


@login_required
def blueprint_add(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    if not can_view_project(request.user, project) or not can_upload_drawings(request.user, project):
        return HttpResponseForbidden("You can't upload drawings to this project.")
    locked = _locked_redirect(request, project)
    if locked:
        return locked
    form = BlueprintForm(request.POST or None, request.FILES or None, project=project)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            blueprint = form.save(commit=False)
            blueprint.project = project
            blueprint.created_by = request.user
            blueprint.save()
            BlueprintRevision.objects.create(
                blueprint=blueprint, revision=form.cleaned_data["revision"], file=form.cleaned_data["file"],
                notes=form.cleaned_data["notes"], uploaded_by=request.user,
            )
        messages.success(request, f"Drawing {blueprint.drawing_number} uploaded and waiting for approval.")
        _analyze_on_upload(request, blueprint.revisions.first())
        return redirect("blueprints:project_drawings", project_pk=project.pk)
    return render(request, "blueprints/form.html", {"form": form, "project": project, "title": "Upload a drawing"})


@login_required
def revision_add(request, blueprint_pk):
    blueprint = get_object_or_404(Blueprint.objects.select_related("project"), pk=blueprint_pk)
    project = blueprint.project
    if not can_view_project(request.user, project) or not can_upload_drawings(request.user, project):
        return HttpResponseForbidden("You can't upload drawings to this project.")
    locked = _locked_redirect(request, project)
    if locked:
        return locked
    form = RevisionForm(request.POST or None, request.FILES or None, blueprint=blueprint)
    if request.method == "POST" and form.is_valid():
        revision = form.save(commit=False)
        revision.blueprint = blueprint
        revision.uploaded_by = request.user
        revision.save()
        messages.success(request, f"Revision {revision.revision} of {blueprint.drawing_number} uploaded and waiting for approval.")
        _analyze_on_upload(request, revision)
        return redirect("blueprints:project_drawings", project_pk=project.pk)
    return render(request, "blueprints/form.html", {
        "form": form, "project": project, "title": f"New revision of {blueprint.drawing_number}",
    })


@login_required
@require_POST
def revision_review(request, revision_pk):
    revision = get_object_or_404(BlueprintRevision.objects.select_related("blueprint__project"), pk=revision_pk)
    project = revision.blueprint.project
    if not can_view_project(request.user, project) or not can_approve_drawings(request.user, project):
        return HttpResponseForbidden("Only the project manager, engineering manager or an admin can approve drawings.")
    if revision.status != "pending":
        messages.error(request, "Only a revision that is awaiting approval can be reviewed.")
        return redirect("blueprints:project_drawings", project_pk=project.pk)
    locked = _locked_redirect(request, project)
    if locked:
        return locked

    action = request.POST.get("action")
    now = timezone.now()
    if action == "approve":
        with transaction.atomic():
            # Only one revision of a drawing may be "the one to build from".
            revision.blueprint.revisions.filter(status="approved").update(status="superseded")
            revision.status = "approved"
            revision.reviewed_by, revision.reviewed_at, revision.rejection_reason = request.user, now, ""
            revision.save()
        messages.success(request, f"{revision.blueprint.drawing_number} rev {revision.revision} approved for construction.")
    elif action == "reject":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Give a reason when rejecting a drawing.")
            return redirect("blueprints:project_drawings", project_pk=project.pk)
        revision.status = "rejected"
        revision.reviewed_by, revision.reviewed_at, revision.rejection_reason = request.user, now, reason[:255]
        revision.save()
        messages.warning(request, f"{revision.blueprint.drawing_number} rev {revision.revision} rejected.")
    return redirect("blueprints:project_drawings", project_pk=project.pk)
