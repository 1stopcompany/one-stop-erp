"""
Cost control maths in one place, built on the project's own BOQ (its phases and sub-items --
"Manage BOQ"), NOT on the item catalogue. Every priced sub-item is a line, and each phase
rolls its sub-items up:

    Budget (BAC)      quantity x budget unit price
    Contract          quantity x contract unit price (what the owner pays)
    Progress %        the sub-item's latest measured execution %
    Earned (EV)       Budget x progress %          (Earned revenue = Contract x progress %)
    Committed         purchase orders issued (sent / confirmed / received) that are assigned to it
    Actual (AC)       goods received against those orders, valued at their PO prices
    Cost variance     EV - AC          (negative = spending more than the work done is worth)
    CPI               EV / AC          (below 0.95 = over cost)
    Forecast (EAC)    Budget / CPI, never below what is already committed
    Quantities        planned quantity, executed quantity (planned x progress %), and the actual
                      cost per executed unit against the budgeted unit price

A purchase is charged to a sub-item through its requisition / order line ("BOQ item"). Purchases
with no BOQ item are shown separately as unassigned -- they are real spending, but nothing can be
compared against them.

Nothing is stored: it is recalculated on every view, so it can't go stale when an order changes
or a progress report comes in.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from procurement.models import POReceipt, PurchaseOrderLine
from reports.progress_models import ProjectPhase, calculate_project_progress
from subcontractors.services import spending_by_sub_item as subcontractor_spending_by_sub_item

ZERO = Decimal("0")
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.05")  # +/-5% of cost performance is "on track"

# A PO counts as committed once it has left draft, until it is cancelled.
COMMITTED_STATUSES = ["sent", "confirmed", "partial_received", "received"]

STATUS_LABELS = {
    "not_started": "Not started",
    "ordered": "Ordered, not received",
    "on_track": "On track",
    "overrun": "Over cost",
    "saving": "Under cost",
    "no_progress": "Spent, no progress recorded",
    "over_committed": "Ordered more than budget",
}
# The three buckets the dashboard charts have always used.
BUCKET = {
    "not_started": "on_budget", "ordered": "on_budget", "on_track": "on_budget",
    "overrun": "over_budget", "over_committed": "over_budget", "no_progress": "over_budget",
    "saving": "under_budget",
}


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT)


def _po_line_allocation(project):
    """{po_line_id: sub_item_id or None} -- the line's own BOQ item, else the one on its requisition line."""
    rows = PurchaseOrderLine.objects.filter(po__project=project).values("id", "sub_item_id", "pr_line__sub_item_id")
    return {r["id"]: (r["sub_item_id"] or r["pr_line__sub_item_id"]) for r in rows}


def spending_by_sub_item(project):
    """
    (committed, actual) as {sub_item_id or None: value} -- purchase orders and subcontractor
    (Musana'a) agreements together. None collects PO purchases that are not assigned to any BOQ
    item (an agreement line always has one, so it never contributes to the None bucket).
    """
    allocation = _po_line_allocation(project)
    committed, actual = {}, {}

    issued = PurchaseOrderLine.objects.filter(po__project=project, po__status__in=COMMITTED_STATUSES)
    for line_id, value in issued.values_list("id", "total_price"):
        key = allocation.get(line_id)
        committed[key] = committed.get(key, ZERO) + value

    receipts = POReceipt.objects.filter(po_line__po__project=project).values_list(
        "po_line_id", "quantity_received", "po_line__unit_price",
    )
    for line_id, qty, unit_price in receipts:
        key = allocation.get(line_id)
        actual[key] = actual.get(key, ZERO) + qty * unit_price

    sc_committed, sc_actual = subcontractor_spending_by_sub_item(project)
    for key, value in sc_committed.items():
        committed[key] = committed.get(key, ZERO) + value
    for key, value in sc_actual.items():
        actual[key] = actual.get(key, ZERO) + value
    return committed, actual


def _status(budget, committed, actual, earned):
    if actual == 0 and committed == 0:
        return "not_started", None
    cpi = (earned / actual) if actual > 0 else None
    if committed > budget * (1 + TOLERANCE):
        return "over_committed", cpi
    if actual == 0:
        return "ordered", cpi
    if earned == 0:
        return "no_progress", cpi
    if cpi < 1 - TOLERANCE:
        return "overrun", cpi
    if cpi > 1 + TOLERANCE:
        return "saving", cpi
    return "on_track", cpi


def _measures(budget, contract, committed, actual, earned, eac=None):
    """The figures every row (a sub-item, a phase, a section, the project) shares."""
    budget, contract, committed, actual, earned = q2(budget), q2(contract), q2(committed), q2(actual), q2(earned)
    status, cpi = _status(budget, committed, actual, earned)
    if eac is None:
        eac = q2(budget * actual / earned) if (actual > 0 and earned > 0) else budget
        eac = max(eac, committed)
    return {
        "budget": budget, "contract": contract, "committed": committed, "actual": actual, "earned": earned,
        "cost_variance": earned - actual, "cpi": cpi.quantize(Decimal("0.01")) if cpi is not None else None,
        "eac": q2(eac), "vac": budget - q2(eac), "uncommitted": budget - committed,
        "status": status, "status_label": STATUS_LABELS[status], "bucket": BUCKET[status],
    }


def _line_row(sub, phase, committed, actual, as_of):
    """One priced sub-item."""
    pct = sub.latest_execution_percentage(as_of)
    fraction = pct / Decimal("100")
    budget, contract = sub.budget_total, sub.contract_total
    earned = budget * fraction
    row = _measures(budget, contract, committed, actual, earned)

    qty = sub.quantity or ZERO
    executed = qty * fraction
    row.update({
        "kind": "item", "sub_item": sub, "phase": phase, "code": sub.code, "name": sub.name_ar, "name_en": sub.name_en,
        "unit": sub.unit, "quantity": qty, "executed_qty": executed, "progress_pct": q2(pct),
        "budget_price": sub.budget_unit_price, "contract_price": sub.contract_unit_price,
        "earned_revenue": q2(contract * fraction),
        # What each unit of work actually cost so far, against what it was budgeted at.
        "actual_unit_cost": q2(row["actual"] / executed) if executed > 0 else None,
        "unit_cost_variance": (q2(row["actual"] / executed) - sub.budget_unit_price) if executed > 0 else None,
    })
    return row


def _rollup(kind, rows, **extra):
    """A phase / section / project row: the sum of the rows beneath it."""
    total = lambda key: sum((r[key] for r in rows), ZERO)  # noqa: E731
    budget, contract, earned = total("budget"), total("contract"), total("earned")
    row = _measures(budget, contract, total("committed"), total("actual"), earned, eac=total("eac"))
    row.update({
        "kind": kind, "earned_revenue": total("earned_revenue"),
        "progress_pct": q2(earned / budget * 100) if budget else ZERO,
        "counts": {"on_budget": 0, "over_budget": 0, "under_budget": 0},
    })
    row.update(extra)
    return row


def project_cost_summary(project, as_of=None) -> dict:
    """
    The whole picture for one project. Returns:
        sections   [{"name", "row", "phases": [{"phase", "row", "lines": [item rows]}]}]
        lines      every priced sub-item row, flat
        phases     every phase row, flat
        totals     the project roll-up (assigned spending only)
        unassigned committed / actual spending not tied to any BOQ item
        staff_labor what the project is charged for employees' hours (cost, hours, overtime hours, per employee)
        counts     lines per status bucket
    """
    committed_by, actual_by = spending_by_sub_item(project)
    phases = (
        ProjectPhase.objects.filter(project=project)
        .prefetch_related("sub_items__progress_entries")
        .order_by("order", "code")
    )

    sections = OrderedDict()
    flat_lines, flat_phases = [], []
    for phase in phases:
        lines = []
        for sub in phase.sub_items.all():
            has_spending = committed_by.get(sub.pk) or actual_by.get(sub.pk)
            if not (sub.budget_total or sub.contract_total or has_spending):
                continue
            lines.append(_line_row(sub, phase, committed_by.get(sub.pk, ZERO), actual_by.get(sub.pk, ZERO), as_of))
        if not lines:
            continue
        phase_row = _rollup("phase", lines, phase=phase, code=phase.code, name=phase.name_ar, name_en=phase.name_en,
                            unit="", quantity=None)
        for line in lines:
            phase_row["counts"][line["bucket"]] += 1
        flat_lines.extend(lines)
        flat_phases.append(phase_row)
        section = sections.setdefault(phase.section or "", {"name": phase.section or "", "phases": []})
        section["phases"].append({"phase": phase, "row": phase_row, "lines": lines})

    for section in sections.values():
        section["row"] = _rollup("section", [p["row"] for p in section["phases"]], name=section["name"])

    totals = _rollup("project", flat_phases) if flat_phases else _rollup("project", [])
    counts = {"on_budget": 0, "over_budget": 0, "under_budget": 0}
    for line in flat_lines:
        counts[line["bucket"]] += 1

    contract, eac = totals["contract"], totals["eac"]
    totals.update({
        # Planned margin = what the owner pays minus what we plan to spend; forecast margin uses the EAC.
        "planned_margin": contract - totals["budget"] if contract else None,
        "forecast_margin": contract - eac if contract else None,
        "margin_to_date": totals["earned_revenue"] - totals["actual"] if contract else None,
    })

    overall = calculate_project_progress(project, as_of_date=as_of)["overall_percentage"]
    # Employees' hours on this project (Daily Time Record split / daily reports), costed at each one's salary rate. Shown next to the
    # BOQ figures, not inside them: the BOQ budget is for materials, subcontractors and the like, and staff salaries are paid anyway.
    from timesheets.services.project_hours import project_labor_cost
    return {
        "staff_labor": project_labor_cost(project, as_of),
        "project": project, "sections": list(sections.values()), "lines": flat_lines, "phases": flat_phases,
        "totals": totals, "counts": counts,
        "unassigned": {"committed": q2(committed_by.get(None, ZERO)), "actual": q2(actual_by.get(None, ZERO))},
        "overall_progress": q2(overall),
        "weighted_progress": totals["progress_pct"],
    }
