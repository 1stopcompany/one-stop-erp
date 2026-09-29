"""
Starting a drawing analysis. Used by the "Analyze" button and, when AI_AUTO_ANALYZE_DRAWINGS is on and an AI provider is set up,
right after a drawing is uploaded. Nothing here ever makes an upload fail: a problem starting the analysis is logged and skipped.
"""
import logging
import os

from django.conf import settings

from . import jobs, llm
from .documents import CAD
from .models import AIRun

logger = logging.getLogger(__name__)


def revision_label(revision) -> str:
    blueprint = revision.blueprint
    return f"Drawing {blueprint.drawing_number} rev {revision.revision}: {blueprint.title}"


def start_takeoff(project, user, *, revision=None, tender=None, instructions=""):
    """Create and start a materials / quantities / green-data analysis of a drawing revision or a tender document."""
    if revision is not None:
        label, fields = revision_label(revision), {"source_revision": revision}
    else:
        label, fields = f"{tender.get_category_display()}: {tender.title}", {"source_tender": tender}
    run = AIRun.objects.create(
        project=project, kind=AIRun.DRAWING_TAKEOFF, created_by=user, source_label=label, model_name=llm.model_name(),
        instructions=instructions[:1000], **fields,
    )
    return jobs.start_run(run)     # the finished run when it ran right away, else the run just created


def auto_analyze_revision(revision, user):
    """Called right after a drawing revision is saved. Returns the started run, or None (feature off, no provider, unreadable format)."""
    try:
        if not getattr(settings, "AI_AUTO_ANALYZE_DRAWINGS", False) or not llm.is_configured():
            return None
        if os.path.splitext(revision.file.name)[1].lower() in CAD:
            return None     # DWG etc.: the person is told to export a PDF when they press Analyze
        return start_takeoff(revision.blueprint.project, user, revision=revision)
    except Exception:
        logger.exception("Automatic analysis of drawing revision %s could not be started", getattr(revision, "pk", "?"))
        return None
