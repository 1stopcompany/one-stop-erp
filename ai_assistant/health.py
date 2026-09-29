"""
Rule-based project health checks. Plain database questions with exact answers -- no AI involved, so they
work without an API key, cost nothing, and give the review agent solid facts to reason from rather than
something it might misread.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from cost_control.services import project_cost_summary
from procurement.models import PurchaseOrder, PurchaseRequisition
from projects import readiness, workflow
from projects.models import ProjectStage
from reports.progress_models import ProjectPhase, ProjectPhaseProgressEntry, ProjectPhaseSubItem

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
ZERO = Decimal("0")


def _finding(severity, area, title, detail="", items=None):
    return {"severity": severity, "area": area, "title": title, "detail": detail, "items": list(items or [])[:8]}


def _examples(subs, limit=5):
    return [f"{s.code or s.phase.code} {s.name_ar}" for s in subs[:limit]]


def boq_checks(project):
    findings = []
    phases = list(ProjectPhase.objects.filter(project=project).prefetch_related("sub_items"))
    if not phases:
        return [_finding("info", "BOQ", "The project has no BOQ yet", "Add phases and items in Manage BOQ, or read a tender document with the AI assistant.")]

    subs = [s for p in phases for s in p.sub_items.all()]
    total_weight = sum((p.weight_percentage for p in phases), ZERO)
    if abs(total_weight - 100) > Decimal("0.01"):
        findings.append(_finding("warning", "BOQ", f"Phase weights add up to {total_weight:.1f}%, not 100%",
                                 "Progress and the owner's financial report use the weights. Once items are priced, use 'Weights from prices'."))

    unpriced = [s for s in subs if s.quantity and not s.budget_unit_price and not s.contract_unit_price]
    if unpriced:
        findings.append(_finding("warning", "BOQ", f"{len(unpriced)} item(s) have a quantity but no price", "", _examples(unpriced)))
    no_qty = [s for s in subs if s.quantity is None]
    if no_qty:
        findings.append(_finding("info", "BOQ", f"{len(no_qty)} item(s) have no quantity yet", "", _examples(no_qty)))
    losing = [s for s in subs if s.budget_unit_price and s.contract_unit_price and s.contract_unit_price < s.budget_unit_price]
    if losing:
        findings.append(_finding("error", "BOQ", f"{len(losing)} item(s) are priced below their cost",
                                 "The contract price is lower than the budget (cost) price, so each unit loses money.", _examples(losing)))
    empty_phases = [p for p in phases if not p.sub_items.all()]
    if empty_phases:
        findings.append(_finding("info", "BOQ", f"{len(empty_phases)} phase(s) have no items or price",
                                 "", [f"{p.code} {p.name_ar}" for p in empty_phases]))
    return findings


def workflow_checks(project):
    findings = []
    board = workflow.stage_board(project)
    if project.status == "planning":
        open_stage = next((row for row in board if not row["done"]), None)
        if open_stage:
            findings.append(_finding("info", "Start-up", f"Project is in Planning; next stage: {open_stage['label']}", open_stage["requirement"]))

    today = timezone.localdate()
    insurances = list(project.insurances.all())
    for ins in insurances:
        state = ins.state
        if state == "expired":
            findings.append(_finding("error", "Insurance", f"{ins.get_policy_type_display()} ({ins.policy_number}) expired on {ins.end_date}"))
        elif state == "expiring":
            findings.append(_finding("warning", "Insurance", f"{ins.get_policy_type_display()} ({ins.policy_number}) expires in {(ins.end_date - today).days} day(s)"))
    if project.status == "active" and not insurances:
        findings.append(_finding("warning", "Insurance", "The project is active but has no insurance policy on file"))
    return findings


def progress_checks(project):
    if project.status != "active":
        return []
    priced = ProjectPhaseSubItem.objects.filter(phase__project=project, quantity__isnull=False)
    if not priced.exists():
        return []
    latest = ProjectPhaseProgressEntry.objects.filter(sub_item__phase__project=project).order_by("-report_date").first()
    if not latest:
        return [_finding("warning", "Progress", "No progress has ever been recorded", "Earned value and CPI can't be calculated until item progress is entered.")]
    age = (timezone.localdate() - latest.report_date).days
    if age > 45:
        return [_finding("warning", "Progress", f"The last progress reading is {age} days old ({latest.report_date})")]
    return []


def cost_checks(project):
    summary = project_cost_summary(project)
    findings = []
    if not summary["lines"]:
        return findings
    labels = {"overrun": ("error", "over cost"), "over_committed": ("error", "ordered more than the budget"),
              "no_progress": ("warning", "spent with no progress recorded")}
    for status, (severity, text) in labels.items():
        rows = [r for r in summary["lines"] if r["status"] == status]
        if rows:
            findings.append(_finding(severity, "Cost", f"{len(rows)} item(s) {text}", "", [f"{r['code']} {r['name']}" for r in rows]))
    cpi = summary["totals"]["cpi"]
    if cpi is not None and cpi < Decimal("0.95"):
        findings.append(_finding("error", "Cost", f"Overall cost performance is {cpi} (below 0.95)",
                                 "The project is spending more than the work done is worth."))
    unassigned = summary["unassigned"]
    if unassigned["committed"] or unassigned["actual"]:
        findings.append(_finding("warning", "Cost", "Purchases are not assigned to a BOQ item",
                                 f"{unassigned['committed']} ordered and {unassigned['actual']} received can't be compared with any budget."))
    return findings


def procurement_checks(project):
    findings = []
    today = timezone.localdate()
    stale = PurchaseRequisition.objects.filter(
        project=project, status="submitted", submitted_date__lt=timezone.now() - timedelta(days=7),
    )
    if stale.exists():
        findings.append(_finding("warning", "Procurement", f"{stale.count()} requisition(s) waiting for approval for over a week",
                                 "", [pr.pr_number for pr in stale[:8]]))
    late = PurchaseOrder.objects.filter(
        project=project, status__in=["sent", "confirmed", "partial_received"], delivery_date__lt=today,
    )
    if late.exists():
        findings.append(_finding("warning", "Procurement", f"{late.count()} purchase order(s) are past their delivery date and not fully received",
                                 "", [f"{po.po_number} (due {po.delivery_date})" for po in late[:8]]))
    return findings


def readiness_checks(project):
    """Why work can't be recorded on the project at all (the rule in projects.readiness)."""
    return [_finding("error", "Readiness", "Work is blocked on this project", p.message, p.detail) for p in readiness.check(project).problems]


def project_health(project):
    """Every check, worst first."""
    findings = (readiness_checks(project) + boq_checks(project) + workflow_checks(project) + progress_checks(project)
                + cost_checks(project) + procurement_checks(project))
    return sorted(findings, key=lambda f: SEVERITY_ORDER[f["severity"]])
