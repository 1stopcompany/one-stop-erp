"""
Project readiness: the one rule that decides whether ANY work may be recorded on a project.

A project is ready when all of these hold:
  * it is past the Planning start-up flow (status is not "planning"),
  * it has an insurance policy that hasn't expired, with its document uploaded,
  * its BOQ exists and is fully priced: every phase has priced items, and every item has a quantity,
    a budget (cost) unit price and a contract unit price above zero.

Closed projects (completed / archived) are not subject to the rule: their insurance has naturally ended.

How it is enforced (see projects/guard.py and projects/middleware.py): while a web request is being served, saving
any operational record of a project that isn't ready (reports, progress, purchasing, stock issues, check-ins, ...)
raises ProjectNotReady, which the middleware turns into a clear message. Setup records (the project itself, its
insurance, tender documents, drawings, BOQ and pricing) are never blocked -- they are how a project becomes ready.
Code that runs outside a request (management commands, shell, tests) is not blocked unless it opts in.
"""
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.exceptions import APIException

EXEMPT_STATUSES = ("completed", "archived")

_state = threading.local()


# ------------------------------------------------------------------ when the rule is enforced

def enforcing() -> bool:
    return getattr(_state, "requests", 0) > 0 and getattr(_state, "suspended", 0) == 0


@contextmanager
def request_scope():
    """Wrapped around every web request by the middleware: the rule is only enforced inside it."""
    _state.requests = getattr(_state, "requests", 0) + 1
    try:
        yield
    finally:
        _state.requests -= 1


@contextmanager
def suspended():
    """Explicitly switch the rule off for a block of code (for example a data import run from a web request)."""
    _state.suspended = getattr(_state, "suspended", 0) + 1
    try:
        yield
    finally:
        _state.suspended -= 1


# ------------------------------------------------------------------ the rule

@dataclass
class Problem:
    code: str          # "startup" | "insurance" | "boq"
    message: str
    detail: list = field(default_factory=list)


@dataclass
class Readiness:
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def __bool__(self):
        return self.ok

    def summary(self) -> str:
        return " ".join(p.message for p in self.problems)


def _insurance_problems(project):
    today = timezone.localdate()
    policies = list(project.insurances.values_list("end_date", "document"))
    if not policies:
        return [Problem("insurance", "No insurance policy is on file. Upload one, with its document, on the project's Workflow page.")]
    live = [(end, doc) for end, doc in policies if end >= today]
    if not live:
        latest = max(end for end, _ in policies)
        return [Problem("insurance", f"All insurance policies have expired (the latest ended on {latest}). Upload a valid policy on the Workflow page.")]
    if not any(doc for _, doc in live):
        return [Problem("insurance", "The insurance policy has no document uploaded. Attach it on the Workflow page.")]
    return []


def _boq_problems(project):
    from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

    phases = list(ProjectPhase.objects.filter(project=project).values_list("id", "code"))
    if not phases:
        return [Problem("boq", "The project has no BOQ. Add its phases and items in Manage BOQ (or read the tender document with the AI Assistant).")]
    items = list(ProjectPhaseSubItem.objects.filter(phase__project=project)
                 .values_list("phase_id", "code", "quantity", "budget_unit_price", "contract_unit_price"))
    with_items = {phase_id for phase_id, *_ in items}
    empty = [code for phase_id, code in phases if phase_id not in with_items]
    unpriced = [code or "?" for _, code, qty, budget, contract in items if not qty or qty <= 0 or budget <= 0 or contract <= 0]
    problems = []
    if unpriced:
        problems.append(Problem(
            "boq", f"The BOQ isn't fully priced: {len(unpriced)} item(s) are missing a quantity, a cost price or a contract price. Complete them in Manage BOQ.",
            unpriced[:8],
        ))
    if empty:
        problems.append(Problem("boq", f"{len(empty)} BOQ phase(s) have no priced item. Price them (or delete them) in Manage BOQ.", empty[:8]))
    return problems


def check(project) -> Readiness:
    """Everything that stops work on this project right now (empty when it is ready)."""
    if project.status in EXEMPT_STATUSES:
        return Readiness()
    problems = []
    if project.status == "planning":
        problems.append(Problem("startup", "The project is still in Planning. Finish its start-up steps (insurance, tender documents, approved drawings) first."))
    problems += _insurance_problems(project)
    problems += _boq_problems(project)
    return Readiness(problems)


def boq_is_priced(project) -> bool:
    return not _boq_problems(project)


def ready_projects():
    """
    A lazy queryset of the ready projects, for form pickers. The same rule as check(), written as SQL so it is
    evaluated when the form is shown, not when the module is imported.
    """
    from projects.models import Project, ProjectInsurance
    from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

    valid_policy = ProjectInsurance.objects.filter(project=OuterRef("pk"), end_date__gte=timezone.localdate()).exclude(document="")
    any_phase = ProjectPhase.objects.filter(project=OuterRef("pk"))
    bad_item = ProjectPhaseSubItem.objects.filter(phase__project=OuterRef("pk")).filter(
        Q(quantity__isnull=True) | Q(quantity__lte=0) | Q(budget_unit_price__lte=0) | Q(contract_unit_price__lte=0)
    )
    empty_phase = ProjectPhase.objects.filter(project=OuterRef("pk")).filter(
        ~Exists(ProjectPhaseSubItem.objects.filter(phase=OuterRef("pk")))
    )
    return Project.objects.filter(
        Q(status__in=EXEMPT_STATUSES)
        | (~Q(status="planning") & Exists(valid_policy) & Exists(any_phase) & ~Exists(bad_item) & ~Exists(empty_phase))
    )


# ------------------------------------------------------------------ the block

class ProjectNotReady(APIException):
    """Raised when work is recorded on a project that isn't ready. DRF views turn it into a 403 with the message."""
    status_code = 403
    default_code = "project_not_ready"

    def __init__(self, project, readiness):
        self.project = project
        self.readiness = readiness
        self.message = f"Work on '{project.name}' is blocked. {readiness.summary()}"
        super().__init__(detail=self.message)

    def __str__(self):
        return self.message


def enforce(project):
    """Raise ProjectNotReady if the rule is being enforced and `project` isn't ready. No-op for None."""
    if project is None or not enforcing():
        return
    readiness = check(project)
    if not readiness.ok:
        raise ProjectNotReady(project, readiness)
