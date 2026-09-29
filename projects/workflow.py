"""
The project start-up flow: insurance -> tender documents -> work starts from an
approved engineering drawing. All rules live here; views only call these functions.

Stages are strict: a stage can be worked on (its documents added, or itself
completed) only once every earlier stage is complete. Projects that were already
running when this flow was introduced -- or that are created outside the "New
project" form with a non-planning status -- get all their stages marked complete
(see ensure_stages), so nothing already in progress is suddenly locked.
"""
from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from .models import Project, ProjectStage, ProjectInsurance, ProjectRegulatoryApproval, ProjectManagementPlan

ORDER = [key for key, _ in ProjectStage.KEYS]


class WorkflowError(Exception):
    """A stage action that the flow doesn't allow (locked, or its requirement isn't met)."""


def ensure_stages(project):
    """Make sure the project has its three stage rows; returns them in flow order."""
    existing = {s.key: s for s in project.stages.all()}
    if len(existing) < len(ORDER):
        legacy = project.status != "planning"  # already running -> nothing to gate
        now = timezone.now()
        for key in ORDER:
            if key not in existing:
                existing[key] = ProjectStage.objects.create(
                    project=project, key=key, completed_at=now if legacy else None,
                )
    return [existing[key] for key in ORDER]


def _approved_drawings(project):
    BlueprintRevision = apps.get_model("blueprints", "BlueprintRevision")
    return BlueprintRevision.objects.filter(blueprint__project=project, status="approved")


def missing_regulatory_bodies(project):
    """Which of government/municipality/civil defense have no approval document on file yet."""
    have = set(project.regulatory_approvals.values_list("body", flat=True))
    return [body for body, _ in ProjectRegulatoryApproval.BODIES if body not in have]


def missing_plan_categories(project):
    """Which management-plan categories still need a document (or, for site_management, a completed checklist)."""
    plans = {p.category: p for p in project.management_plans.all()}
    return [
        category for category, _ in ProjectManagementPlan.CATEGORIES
        if category not in plans or not plans[category].checklist_complete
    ]


def requirement(project, key):
    """(met, text) -- what a stage needs before it can be completed."""
    if key == ProjectStage.INSURANCE:
        valid = project.insurances.filter(end_date__gte=timezone.localdate()).exists()
        return valid, "At least one insurance policy that hasn't expired, with its document uploaded."
    if key == ProjectStage.TENDER:
        return project.tender_documents.exists(), "At least one tender document uploaded."
    if key == ProjectStage.DRAWINGS:
        # Starting the work also needs a fully priced BOQ (see projects.readiness): work can't be recorded without one.
        from . import readiness
        missing = missing_regulatory_bodies(project)
        met = _approved_drawings(project).exists() and readiness.boq_is_priced(project) and not missing
        text = "At least one engineering drawing approved for construction, a fully priced BOQ (every item with a quantity, " \
               "a cost price and a contract price), and an approval document on file from each of: government, municipality, civil defense."
        return met, text
    if key == ProjectStage.SCHEDULE:
        ScheduleTask = apps.get_model("reports", "ScheduleTask")
        return ScheduleTask.objects.filter(project=project).exists(), "A project schedule imported (Schedule page)."
    if key == ProjectStage.PLANS:
        missing = missing_plan_categories(project)
        return not missing, (
            "Every required project-management plan document uploaded: ESHS, Quality, Risk, Technical Approach and "
            "Methodology, Project Team, Code of Conduct, and Site Management and Logistics (with its 6-point checklist fully checked)."
        )
    raise ValueError(key)


def stage_board(project):
    """The three stages, in order, with what the page needs to show for each."""
    stages = ensure_stages(project)
    board, previous_done = [], True
    for stage in stages:
        met, text = requirement(project, stage.key)
        board.append({
            "stage": stage, "key": stage.key, "label": stage.get_key_display(), "done": stage.is_complete,
            "locked": not previous_done, "requirement_met": met, "requirement": text,
            "can_complete": previous_done and not stage.is_complete and met,
        })
        previous_done = previous_done and stage.is_complete
    return board


def is_unlocked(project, key):
    """True if `key` may be worked on: every stage before it is complete."""
    for stage in ensure_stages(project):
        if stage.key == key:
            return True
        if not stage.is_complete:
            return False
    return False


def require_unlocked(project, key):
    if not is_unlocked(project, key):
        label = dict(ProjectStage.KEYS)[key]
        raise WorkflowError(f"'{label}' is locked -- complete the earlier stages first.")


@transaction.atomic
def complete_stage(project, key, user):
    """Mark a stage complete. Completing the last one starts the work (planning -> active)."""
    require_unlocked(project, key)
    stage = next(s for s in ensure_stages(project) if s.key == key)
    if stage.is_complete:
        raise WorkflowError("This stage is already complete.")
    met, text = requirement(project, key)
    if not met:
        raise WorkflowError(f"Can't complete this stage yet: {text}")
    stage.completed_at = timezone.now()
    stage.completed_by = user
    stage.save(update_fields=["completed_at", "completed_by"])
    if key == ORDER[-1] and project.status == "planning":
        project.status = "active"
        project.save(update_fields=["status", "updated_at"])
    return stage


def flow_complete(project):
    return all(s.is_complete for s in ensure_stages(project))


def current_stage_label(project):
    for stage in ensure_stages(project):
        if not stage.is_complete:
            return stage.get_key_display()
    return None


def insurance_alerts(projects):
    """Policies that are expired or expire within the warning window, for the given projects."""
    horizon = timezone.localdate() + timedelta(days=ProjectInsurance.EXPIRY_WARNING_DAYS)
    return list(
        ProjectInsurance.objects.filter(project__in=projects, end_date__lte=horizon)
        .select_related("project").order_by("end_date")
    )
