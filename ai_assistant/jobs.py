"""
Running an AIRun. The work takes from tens of seconds to a few minutes, so it runs in a background thread
and the page polls the run's status (Celery is installed but has no broker configured here). Tests and
anyone who sets AI_RUN_IN_BACKGROUND = False get it synchronously.
"""
import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from . import llm
from .documents import UnsupportedSource
from .models import AIRun

logger = logging.getLogger(__name__)


def execute_run(run_id, client=None):
    """Do the run's work and record the outcome. Never raises: failures are stored on the run."""
    run = AIRun.objects.select_related("project", "source_tender", "source_revision").get(pk=run_id)
    run.status, run.started_at, run.error = AIRun.RUNNING, timezone.now(), ""
    run.model_name = llm.model_name()
    run.save(update_fields=["status", "started_at", "error", "model_name"])
    try:
        if run.kind == AIRun.BOQ_EXTRACT:
            from .extraction import extract_boq
            extract_boq(run, client=client)
        elif run.kind == AIRun.DRAWING_TAKEOFF:
            from .takeoff import extract_takeoff
            extract_takeoff(run, client=client)
        else:
            from .review import review_project
            review_project(run, client=client)
        run.status = AIRun.DONE
    except (llm.AINotConfigured, llm.AIFailure, UnsupportedSource) as exc:
        run.status, run.error = AIRun.FAILED, str(exc)
    except Exception as exc:  # network, API status errors, anything unforeseen: show a readable reason, keep the traceback in the log
        logger.exception("AI run %s failed", run_id)
        run.status, run.error = AIRun.FAILED, llm.friendly_error(exc)
    run.finished_at = timezone.now()
    run.save()
    return run


def start_run(run, client=None):
    """Hand the run to a worker thread (or do it now when background running is off)."""
    if not getattr(settings, "AI_RUN_IN_BACKGROUND", True) or client is not None:
        return execute_run(run.pk, client=client)
    threading.Thread(target=_thread_main, args=(run.pk,), daemon=True, name=f"ai-run-{run.pk}").start()
    return run


def _thread_main(run_id):
    """A worker thread has its own database connection, which must be closed when it ends."""
    try:
        execute_run(run_id)
    finally:
        connection.close()


def recover_stale_runs(minutes=30):
    """A run stuck in Waiting/Working (server restarted mid-run) is marked failed so it doesn't spin forever."""
    cutoff = timezone.now() - timedelta(minutes=minutes)
    stale = AIRun.objects.filter(status__in=[AIRun.PENDING, AIRun.RUNNING], created_at__lt=cutoff)
    stale.update(status=AIRun.FAILED, error="The run was interrupted (the server restarted or it took too long). Start it again.",
                 finished_at=timezone.now())
