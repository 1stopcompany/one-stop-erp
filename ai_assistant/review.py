"""
The project review agent. Claude is given read-only tools over ONE project's data (fixed when the run is
created, so it can't wander into other projects), gathers facts, looks for inconsistencies across areas, and
reports its findings through `submit_review`. It can't change anything: none of the tools writes.
"""
import json
from decimal import Decimal

from django.utils import timezone

from cost_control.services import project_cost_summary
from procurement.models import PurchaseOrder, PurchaseRequisition
from projects import workflow
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

from . import llm
from .health import project_health
from . import edge, takeoff
from .importer import compare_with_boq

MAX_TURNS = 24

SYSTEM_PROMPT = """You review a construction project for a contractor's management, using read-only tools over the company's ERP data \
for ONE project. You cannot change anything.

How to work:
1. Start with get_health_checks (exact, rule-based facts), then read what you need: get_project_overview, get_boq, get_cost_summary, \
get_purchasing, get_progress, get_document_extractions, get_drawing_takeoffs.
2. Look for problems and for INCONSISTENCIES BETWEEN areas: the BOQ against what tender documents say (get_document_extractions), \
spending against measured progress, project status against its start-up stages, insurance against status, unassigned purchases, \
unpriced or zero-quantity items, weights that don't add up, stale progress, overdue orders.
3. Every finding must rest on data a tool returned. Quote numbers and item codes exactly as returned. Do not guess causes you cannot \
see; if you suggest a possible cause, say it is a possibility. Amounts are in the project's currency.
4. Prioritise by impact on money, safety and schedule. Merge related problems into one finding. At most 15 findings; if there are \
no real problems, say so in the summary and return no findings.
5. Finish by calling submit_review exactly once, then stop.

Severity: "error" = money is being lost or a hard requirement is broken; "warning" = needs attention soon; "info" = worth knowing.
Write for a project manager: plain language, short, each finding with a concrete suggested action. Write the summary and findings in \
English unless the project's own data is in Arabic and a name must be quoted."""


def _json(data, limit=60000):
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[:limit] + '... [truncated: ask for a narrower slice, e.g. a single section]'
    return text


def _num(value):
    return None if value is None else float(value)


def make_tools(project, sink: dict, include_submit: bool = True, max_chars: int = 60000):
    """The read-only tool functions (plain callables with docstrings; decorated for the API by the caller).

    `max_chars` caps one tool result (local models have far less room than Claude).
    """

    def j(data):
        return _json(data, max_chars)

    def get_health_checks() -> str:
        """Rule-based health checks for the project (BOQ completeness, insurance, progress, cost, overdue orders). Exact facts; start here."""
        return j(project_health(project))

    def get_project_overview() -> str:
        """Project details, start-up stages, insurance policies, tender documents and drawings with their approval status."""
        board = workflow.stage_board(project)
        blueprints = []
        for bp in project.blueprints.prefetch_related("revisions"):
            blueprints.append({"number": bp.drawing_number, "title": bp.title, "discipline": bp.discipline,
                               "revisions": [{"rev": r.revision, "status": r.status} for r in bp.revisions.all()]})
        return j({
            "name": project.name, "symbol": project.project_symbol, "status": project.status, "client": project.client_name,
            "contract_number": project.contract_number, "start_date": project.start_date, "end_date": project.end_date,
            "manager": getattr(project.manager, "username", None), "site_engineer": getattr(project.site_engineer, "username", None),
            "stages": [{"stage": row["label"], "done": row["done"], "locked": row["locked"], "requirement_met": row["requirement_met"]} for row in board],
            "insurance": [{"type": i.get_policy_type_display(), "insurer": i.insurer, "policy": i.policy_number,
                           "amount": _num(i.insured_amount), "start": i.start_date, "end": i.end_date, "state": i.state} for i in project.insurances.all()],
            "tender_documents": [{"category": d.get_category_display(), "title": d.title, "uploaded": d.uploaded_at.date()} for d in project.tender_documents.all()],
            "drawings": blueprints,
        })

    def get_boq(section: str = "") -> str:
        """The project BOQ as a tree of phases and sub-items with unit, quantity, budget and contract prices and weights.

        Args:
            section: Only this section (e.g. "Civil Works"). Leave empty for everything; a big BOQ returns a section list first.
        """
        phases = list(ProjectPhase.objects.filter(project=project).prefetch_related("sub_items").order_by("order", "code"))
        if section:
            phases = [p for p in phases if p.section == section]
        elif len(phases) > 60:
            counts = {}
            for p in phases:
                counts[p.section or "(no section)"] = counts.get(p.section or "(no section)", 0) + 1
            return j({"note": "Large BOQ: call get_boq again with section=<name>.", "sections": counts})
        return j([{
            "code": p.code, "section": p.section, "name": p.name_ar or p.name_en, "weight": _num(p.weight_percentage),
            "budget_total": _num(p.budget_total()), "contract_total": _num(p.contract_total()),
            "items": [{"code": s.code, "name": s.name_ar, "unit": s.unit, "quantity": _num(s.quantity),
                       "budget_price": _num(s.budget_unit_price), "contract_price": _num(s.contract_unit_price),
                       "whole_item": s.is_whole} for s in p.sub_items.all()],
        } for p in phases])

    def get_cost_summary() -> str:
        """Budget vs committed vs actual vs earned for the project: totals, per-phase rows, items with problems, unassigned purchases."""
        summary = project_cost_summary(project)
        totals = {k: _num(v) if isinstance(v, Decimal) else v for k, v in summary["totals"].items()}
        phases = [{k: (_num(v) if isinstance(v, Decimal) else v) for k, v in row.items()
                   if k in ("code", "name", "budget", "contract", "committed", "actual", "earned", "cpi", "eac", "progress_pct", "status_label")}
                  for row in summary["phases"]]
        problems = [{"code": r["code"], "name": r["name"], "status": r["status_label"], "budget": _num(r["budget"]), "committed": _num(r["committed"]),
                     "actual": _num(r["actual"]), "earned": _num(r["earned"]), "cpi": _num(r["cpi"]), "progress_pct": _num(r["progress_pct"])}
                    for r in summary["lines"] if r["status"] in ("overrun", "over_committed", "no_progress")][:60]
        return j({"totals": totals, "phases": phases, "items_needing_attention": problems,
                      "unassigned_purchases": {k: _num(v) for k, v in summary["unassigned"].items()}, "weighted_progress": _num(summary["weighted_progress"])})

    def get_purchasing() -> str:
        """Recent purchase requisitions and purchase orders for the project with status, supplier, value and delivery dates."""
        prs = PurchaseRequisition.objects.filter(project=project).order_by("-created_date")[:25]
        pos = PurchaseOrder.objects.filter(project=project).select_related("vendor").order_by("-po_date")[:40]
        return j({
            "requisitions": [{"number": p.pr_number, "status": p.status, "required_date": p.required_date, "lines": p.lines.count()} for p in prs],
            "orders": [{"number": o.po_number, "supplier": o.vendor.name, "status": o.status, "total": _num(o.total_price),
                        "delivery_date": o.delivery_date, "lines_without_boq_item": o.lines.filter(sub_item__isnull=True, pr_line__sub_item__isnull=True).count()} for o in pos],
        })

    def get_progress() -> str:
        """Latest measured progress % and its date for every priced BOQ item."""
        rows = []
        for sub in ProjectPhaseSubItem.objects.filter(phase__project=project, quantity__isnull=False).select_related("phase").prefetch_related("progress_entries")[:200]:
            entry = sub.latest_progress_entry()
            rows.append({"code": sub.code or sub.phase.code, "name": sub.name_ar, "progress_pct": _num(entry.execution_percentage) if entry else None,
                         "as_of": entry.report_date if entry else None})
        return j(rows)

    def get_document_extractions() -> str:
        """Documents the AI assistant has already read into draft BOQs for this project, and how their items compare with the current BOQ."""
        from .models import AIRun

        runs = AIRun.objects.filter(project=project, kind=AIRun.BOQ_EXTRACT, status=AIRun.DONE).order_by("-created_at")[:4]
        return j([{
            "document": r.source_label, "read_on": r.created_at.date(), "imported_into_boq": bool(r.imported_at),
            "summary": r.result.get("document_summary"), "totals": r.result.get("totals"),
            "issues_reported": r.result.get("issues", [])[:15], "compared_with_current_boq": compare_with_boq(project, r.result),
        } for r in runs])

    def get_drawing_takeoffs() -> str:
        """What the AI read from drawings and specifications: the materials and quantities they call for (against the BOQ and priced at BOQ cost prices), and the green-building (EDGE) data found and still missing."""
        from .models import AIRun

        documents, seen = [], set()
        for run in AIRun.objects.filter(project=project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE).order_by("-created_at"):
            key = (run.source_revision_id, run.source_tender_id, run.source_label)
            if key in seen or not run.result:
                continue
            seen.add(key)
            linked = takeoff.link_to_boq(project, run.result)
            documents.append({
                "document": run.source_label, "read_on": run.created_at.date(), "summary": run.result.get("drawing_summary"),
                "totals": linked["totals"],
                "boq_lines_compared": [{"code": l["code"], "name": l["name"], "unit": l["unit"], "boq_quantity": _num(l["boq_quantity"]),
                                        "in_document": _num(l["drawing_quantity"]), "difference": _num(l["difference"])} for l in linked["lines"]][:40],
                "items_without_a_boq_line": [r["description"] for r in linked["rows"] if not r["boq"]][:25],
                "issues": run.result.get("issues", [])[:10],
            })
            if len(documents) >= 6:
                break
        green = edge.project_edge_data(project)
        return j({"documents": documents, "green_building_edge": {
            "note": "Design facts an EDGE assessment needs, found in the analyzed documents. The EDGE savings themselves are calculated in the official EDGE app.",
            "found": green["found"], "total": green["total"], "missing": [m["label"] for m in green["missing"]],
            "stated": [{"point": e["point"], "value": e["value"], "source": e["source"]} for d in green["domains"] for p in d["points"] for e in p["entries"]][:60],
        }})

    def submit_review(summary: str, findings: list[dict]) -> str:
        """Submit the finished review. Call exactly once, at the end.

        Args:
            summary: Two to four sentences: the project's overall condition and the most important thing to act on.
            findings: The findings. Each is an object with: severity ("error", "warning" or "info"), area (e.g. "Cost", "BOQ", "Insurance"), title (one line), detail (what the data shows, with exact numbers/codes), action (the concrete next step).
        """
        sink["review"] = clean_review({"summary": summary, "findings": findings})
        return "Review recorded. You can stop now."

    tools = [get_health_checks, get_project_overview, get_boq, get_cost_summary, get_purchasing, get_progress,
             get_document_extractions, get_drawing_takeoffs]
    return tools + [submit_review] if include_submit else tools


def clean_review(raw: dict) -> dict:
    findings = []
    for f in (raw.get("findings") or [])[:20]:
        if not isinstance(f, dict) or not f.get("title"):
            continue
        findings.append({
            "severity": f.get("severity") if f.get("severity") in ("error", "warning", "info") else "info",
            "area": str(f.get("area") or "")[:40], "title": str(f["title"])[:200],
            "detail": str(f.get("detail") or "")[:1500], "action": str(f.get("action") or "")[:600],
        })
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return {"summary": str(raw.get("summary") or "")[:2000], "findings": findings}


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["error", "warning", "info"]}, "area": {"type": "string"},
                "title": {"type": "string"}, "detail": {"type": "string"}, "action": {"type": "string"},
            },
            "required": ["severity", "area", "title", "detail", "action"], "additionalProperties": False,
        }},
    },
    "required": ["summary", "findings"], "additionalProperties": False,
}

FORMAT_SYSTEM = ("You turn a project reviewer's notes into the required JSON format. Use only what the notes say: don't add findings, "
                 "numbers or codes. Severity: error = money is being lost or a hard requirement is broken; warning = needs attention soon; info = worth knowing.")


def review_project(run, client=None):
    """Run the review and store it on the run. Returns the cleaned review."""
    sink = {}
    instruction = f"Review the project {run.project.name} ({run.project.project_symbol}). Today is {timezone.localdate()}."
    if run.instructions:
        instruction += f"\nFocus requested by the user: {run.instructions}"

    result = llm.run_agent(
        system=SYSTEM_PROMPT, messages=[{"role": "user", "content": instruction}],
        functions=make_tools(run.project, sink, max_chars=llm.tool_result_limit()),
        max_turns=MAX_TURNS, max_tokens=16000, stop_after="submit_review", client=client,
    )
    run.input_tokens, run.output_tokens = result.input_tokens, result.output_tokens
    if "review" not in sink:
        if not result.text:
            raise llm.AIFailure("The review didn't finish. Try again.")
        # The model wrote its findings as plain text instead of calling submit_review (common with smaller local models).
        raw, tokens_in, tokens_out = llm.structured(FORMAT_SYSTEM, result.text, REVIEW_SCHEMA, client=client)
        sink["review"] = clean_review(raw)
        run.input_tokens += tokens_in
        run.output_tokens += tokens_out
    run.result = {**sink["review"], "health_checks": project_health(run.project)}
    return run.result
