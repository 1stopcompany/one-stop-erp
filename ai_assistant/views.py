"""
AI assistant pages. Who may do what:
  * admin, engineering manager, the project's own manager: read documents, start reviews, import drafts;
  * general manager: see results and start a review (read-only over the project's data);
  * everyone else: no access -- the assistant reads contract documents.
"""
import csv
import json
import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserAuditLog
from blueprints.models import BlueprintRevision
from projects.models import Project, ProjectTenderDocument
from projects.views_workflow import can_manage_workflow

from . import chat, edge, jobs, llm, takeoff, triggers
from .health import project_health
from .importer import compare_with_boq, import_draft, mark_conflicts
from .models import AIRun

logger = logging.getLogger(__name__)

CHAT_LIMIT_PER_HOUR = 40
DENIED = "Only the project manager, engineering manager, general manager or an admin can use the AI assistant."
UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".xlsx", ".xlsm", ".csv", ".txt"}


def can_use_assistant(user, project):
    return can_manage_workflow(user, project) or user.is_general_manager()


def can_import(user, project):
    return can_manage_workflow(user, project)


def _audit(request, action, run, description):
    UserAuditLog.objects.create(
        user=request.user, action=action, content_type="AIRun", object_id=run.pk,
        description=description[:500], ip_address=request.META.get("REMOTE_ADDR") or None,
    )


def _project_or_denied(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_use_assistant(request.user, project):
        return project, HttpResponseForbidden(DENIED)
    return project, None


def _run_or_denied(request, run_id):
    run = get_object_or_404(AIRun.objects.select_related("project", "source_tender", "source_revision"), pk=run_id)
    if not can_use_assistant(request.user, run.project):
        return run, HttpResponseForbidden(DENIED)
    return run, None


def _start(request, run):
    """Create-and-go: hands the run to the worker and sends the user to its page."""
    jobs.start_run(run)
    return redirect("ai_assistant:run_detail", run_id=run.pk)


@login_required
def project_ai(request, project_id):
    project, denied = _project_or_denied(request, project_id)
    if denied:
        return denied
    jobs.recover_stale_runs()
    revisions = (BlueprintRevision.objects.filter(blueprint__project=project).select_related("blueprint")
                 .order_by("blueprint__drawing_number", "-uploaded_at"))
    return render(request, "ai_assistant/project_ai.html", {
        "project": project,
        "configured": llm.is_configured(),
        "provider": llm.describe(),
        "provider_status": llm.status(),
        "hint": llm.setup_hint(),
        "can_import": can_import(request.user, project),
        "health": project_health(project),
        "tender_documents": project.tender_documents.all(),
        "revisions": revisions,
        "runs": project.ai_runs.select_related("created_by")[:15],
        "max_mb": settings.AI_MAX_UPLOAD_MB,
    })


def _new_run(request, project, kind, **fields):
    return AIRun.objects.create(
        project=project, kind=kind, created_by=request.user, model_name=llm.model_name(),
        instructions=request.POST.get("instructions", "").strip()[:1000], **fields,
    )


@login_required
@require_POST
def analyze(request, project_id):
    """Read one document into a draft BOQ, or into a materials / quantities / green-building take-off (mode=takeoff).
    The source is a tender document, a drawing revision, or an uploaded file."""
    project, denied = _project_or_denied(request, project_id)
    if denied:
        return denied
    if not can_import(request.user, project):
        return HttpResponseForbidden("Reading documents into the BOQ is for the project manager, engineering manager or an admin.")
    back = redirect("ai_assistant:project_ai", project_id=project.pk)
    if not llm.is_configured():
        messages.error(request, llm.setup_hint())
        return back

    source = request.POST.get("source", "")
    upload = request.FILES.get("file")
    kind = AIRun.DRAWING_TAKEOFF if request.POST.get("mode") == "takeoff" else AIRun.BOQ_EXTRACT
    if source.startswith("tender:"):
        doc = get_object_or_404(ProjectTenderDocument, pk=source.split(":", 1)[1], project=project)
        run = _new_run(request, project, kind, source_tender=doc, source_label=f"{doc.get_category_display()}: {doc.title}")
    elif source.startswith("revision:"):
        rev = get_object_or_404(BlueprintRevision, pk=source.split(":", 1)[1], blueprint__project=project)
        run = _new_run(request, project, kind, source_revision=rev, source_label=triggers.revision_label(rev))
    elif upload:
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in UPLOAD_EXTENSIONS:
            hint = " Export drawings from CAD to PDF first." if ext in {".dwg", ".dxf", ".rvt", ".ifc"} else ""
            messages.error(request, f"'{ext or upload.name}' files can't be read. Use PDF, an image, Excel, CSV or text.{hint}")
            return back
        if upload.size > settings.AI_MAX_UPLOAD_MB * 1024 * 1024:
            messages.error(request, f"The file is larger than {settings.AI_MAX_UPLOAD_MB} MB. Split it into parts.")
            return back
        run = _new_run(request, project, kind, source_file=upload, source_label=upload.name)
    else:
        messages.error(request, "Choose a document, or upload a file.")
        return back

    what = "materials, quantities and green-building data" if kind == AIRun.DRAWING_TAKEOFF else "a draft BOQ"
    _audit(request, "create", run, f"AI: read '{run.source_label}' into {what} for {project.project_symbol}")
    return _start(request, run)


@login_required
@require_POST
def start_review(request, project_id):
    project, denied = _project_or_denied(request, project_id)
    if denied:
        return denied
    if not llm.is_configured():
        messages.error(request, llm.setup_hint())
        return redirect("ai_assistant:project_ai", project_id=project.pk)
    run = _new_run(request, project, AIRun.PROJECT_REVIEW, source_label="Whole project")
    _audit(request, "create", run, f"AI: review of project {project.project_symbol}")
    return _start(request, run)


@login_required
def run_detail(request, run_id):
    run, denied = _run_or_denied(request, run_id)
    if denied:
        return denied
    context = {"run": run, "project": run.project, "can_import": can_import(request.user, run.project)}
    if run.status == AIRun.DONE and run.result:
        if run.kind == AIRun.BOQ_EXTRACT:
            draft = mark_conflicts(run.project, run.result)
            context.update(draft=draft, comparison=compare_with_boq(run.project, draft),
                           new_count=sum(1 for s in draft["sections"] for i in s["items"] if not i["exists"]))
        elif run.kind == AIRun.DRAWING_TAKEOFF:
            linked = takeoff.link_to_boq(run.project, run.result)
            context.update(takeoff=run.result, linked=linked, groups=takeoff.grouped(linked["rows"]),
                           green=edge.coverage(run.result.get("green_data", [])))
        else:
            context["review"] = run.result
    return render(request, "ai_assistant/run_detail.html", context)


@login_required
@require_POST
def analyze_drawing(request, revision_id):
    """The "Analyze" button on the drawings page: materials, quantities and green data from one drawing revision."""
    revision = get_object_or_404(BlueprintRevision.objects.select_related("blueprint__project"), pk=revision_id)
    project = revision.blueprint.project
    if not can_import(request.user, project):
        return HttpResponseForbidden("Analyzing drawings is for the project manager, engineering manager or an admin.")
    if not llm.is_configured():
        messages.error(request, llm.setup_hint())
        return redirect("blueprints:project_drawings", project_pk=project.pk)
    run = triggers.start_takeoff(project, request.user, revision=revision)
    _audit(request, "create", run, f"AI: analysis of {run.source_label} for {project.project_symbol}")
    return redirect("ai_assistant:run_detail", run_id=run.pk)


TAKEOFF_CSV_HEADER = ["Category", "Description", "Specification", "Location", "Unit", "Quantity", "BOQ code", "BOQ item",
                      "BOQ unit", "BOQ cost price", "Estimated cost", "Page", "Confidence", "Notes"]


def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = "attachment; filename=" + chr(34) + filename + chr(34)
    response.write(chr(0xFEFF))   # so Excel reads the Arabic correctly
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


@login_required
def run_takeoff_csv(request, run_id):
    """The materials and quantities of a take-off as a spreadsheet, for the buyer."""
    run, denied = _run_or_denied(request, run_id)
    if denied:
        return denied
    if run.kind != AIRun.DRAWING_TAKEOFF or run.status != AIRun.DONE or not run.result:
        return HttpResponse("This run has no take-off.", status=404)
    linked = takeoff.link_to_boq(run.project, run.result)
    rows = []
    for row in linked["rows"]:
        boq = row["boq"] or {}
        rows.append([
            takeoff.CATEGORY_LABELS[row["category"]], row["description"], row["specification"], row["location"], row["unit"],
            row["quantity"] or "", boq.get("code", ""), boq.get("name", ""), boq.get("unit", ""), boq.get("price", ""),
            row["est_cost"] or "", row["source_page"] or "", row["confidence"], row["notes"],
        ])
    return _csv_response(f"takeoff-{run.pk}.csv", TAKEOFF_CSV_HEADER, rows)


@login_required
def project_edge(request, project_id):
    """The green-building (EDGE) data found across every analyzed document of the project, and what is still missing."""
    project, denied = _project_or_denied(request, project_id)
    if denied:
        return denied
    return render(request, "ai_assistant/edge.html", {"project": project, "edge": edge.project_edge_data(project)})


@login_required
def project_edge_csv(request, project_id):
    project, denied = _project_or_denied(request, project_id)
    if denied:
        return denied
    data = edge.project_edge_data(project)
    rows = []
    for domain in data["domains"]:
        for point in domain["points"]:
            if point["entries"]:
                for entry in point["entries"]:
                    rows.append([domain["label"], point["label"], "Found", entry["value"], entry["number"] or "", entry["unit"], entry["location"],
                                 entry["source"], entry["source_page"] or "", entry["confidence"]])
            else:
                rows.append([domain["label"], point["label"], "MISSING", "", "", "", "", "", "", ""])
    header = ["Domain", "Data point", "Status", "Value", "Number", "Unit", "Applies to", "Source document", "Page", "Confidence"]
    return _csv_response(f"edge-data-{project.project_symbol}.csv", header, rows)


@login_required
def run_status(request, run_id):
    run, denied = _run_or_denied(request, run_id)
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse({"status": run.status, "finished": run.is_finished, "error": run.error})


@login_required
@require_POST
def run_import(request, run_id):
    run, denied = _run_or_denied(request, run_id)
    if denied:
        return denied
    if not can_import(request.user, run.project):
        return HttpResponseForbidden("Importing into the BOQ is for the project manager, engineering manager or an admin.")
    back = redirect("ai_assistant:run_detail", run_id=run.pk)
    if run.kind != AIRun.BOQ_EXTRACT or run.status != AIRun.DONE or not run.result:
        messages.error(request, "This run has no draft BOQ to import.")
        return back
    keys = request.POST.getlist("keys")
    if not keys:
        messages.error(request, "Tick at least one item to import.")
        return back

    summary = import_draft(run, keys, use_printed_prices=request.POST.get("use_prices") == "1")
    run.imported_at, run.imported_by, run.import_summary = timezone.now(), request.user, summary
    run.save(update_fields=["imported_at", "imported_by", "import_summary"])
    _audit(request, "update", run, f"AI: imported {summary['created_phases']} item(s) into the BOQ of {run.project.project_symbol} from '{run.source_label}'")

    text = f"Imported {summary['created_phases']} main item(s) with {summary['created_sub_items']} priced line(s) into the BOQ."
    if summary["skipped"]:
        text += f" Skipped {len(summary['skipped'])} (already in the BOQ or without an item number)."
    messages.success(request, text + " Next: set the prices and use 'Weights from prices' in Manage BOQ.")
    return back


# ------------------------------------------------------------------ chat bubble

def chat_projects(user):
    """The projects this user can talk to the assistant about."""
    if user.is_project_manager():
        return Project.objects.filter(manager=user).order_by("name")
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager():
        return Project.objects.all().order_by("name")
    return Project.objects.none()


def _chat_allowed(request):
    user = request.user
    return user.is_admin() or user.is_engineering_manager() or user.is_general_manager() or user.is_project_manager()


def _within_chat_limit(user):
    """A cheap brake on API spend: at most CHAT_LIMIT_PER_HOUR questions per user per hour (per server process)."""
    key = f"ai-chat:{user.pk}:{timezone.now():%Y%m%d%H}"
    cache.add(key, 0, 3600)
    return cache.incr(key) <= CHAT_LIMIT_PER_HOUR


@login_required
def chat_config(request):
    if not _chat_allowed(request):
        return JsonResponse({"enabled": False})
    return JsonResponse({
        "enabled": True, "configured": llm.is_configured(), "hint": llm.setup_hint(), "provider": llm.describe()["label"],
        "projects": [{"id": p.pk, "name": p.name, "symbol": p.project_symbol} for p in chat_projects(request.user)],
    })


@login_required
@require_POST
def chat_message(request):
    if not _chat_allowed(request):
        return JsonResponse({"error": DENIED}, status=403)
    try:
        body = json.loads(request.body or b"{}")
        project = chat_projects(request.user).get(pk=int(body.get("project_id")))
        history = chat.clean_history(body.get("messages"))
    except chat.ChatInputError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except (ValueError, TypeError, Project.DoesNotExist):
        return JsonResponse({"error": "Pick a project you manage, then ask again."}, status=400)
    if not llm.is_configured():
        return JsonResponse({"error": llm.setup_hint()}, status=503)
    if not _within_chat_limit(request.user):
        return JsonResponse({"error": f"You've reached {CHAT_LIMIT_PER_HOUR} questions this hour. Try again later."}, status=429)
    try:
        result = chat.answer(project, history)
    except llm.AIFailure as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception as exc:  # network, API status errors: readable message to the user, traceback to the log
        logger.exception("AI chat failed")
        return JsonResponse({"error": llm.friendly_error(exc)}, status=502)
    return JsonResponse({"reply": result["reply"]})
