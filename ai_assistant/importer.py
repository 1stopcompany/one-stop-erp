"""
Putting a reviewed draft BOQ into the project. This is the only place AI output touches real data, and only when a
person presses Import: nothing is overwritten (item numbers that already exist in the project are skipped and
reported), and every phase it creates is marked in its notes so it can be traced back to the run.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max

from projects.models import Project
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

MARK = "[AI:run {run_id}]"


def existing_codes(project: Project):
    """(phase codes, {phase code: set of sub-item codes}) already in the project's BOQ."""
    phases = ProjectPhase.objects.filter(project=project)
    return {p.code for p in phases}


def mark_conflicts(project: Project, draft: dict) -> dict:
    """Adds `exists` to every main item of the draft whose item number is already a phase of this project."""
    codes = existing_codes(project)
    for section in draft["sections"]:
        for item in section["items"]:
            item["exists"] = bool(item["code"]) and item["code"] in codes
    return draft


def _decimal(value):
    return None if value in (None, "") else Decimal(str(value))


@transaction.atomic
def import_draft(run, selected_keys, use_printed_prices=False) -> dict:
    """
    Create phases / sub-items for the main items whose key is in `selected_keys` (a sub-item is
    imported with its main item). Returns {"created_phases", "created_sub_items", "skipped": [...]}.
    """
    project = run.project
    draft = run.result
    selected = set(selected_keys)
    codes = existing_codes(project)
    order = (ProjectPhase.objects.filter(project=project).aggregate(m=Max("order"))["m"] or 0)
    summary = {"created_phases": 0, "created_sub_items": 0, "skipped": []}

    for section in draft["sections"]:
        for item in section["items"]:
            if item["key"] not in selected:
                continue
            code = item["code"]
            if not code:
                summary["skipped"].append({"code": "", "name": item["name_ar"], "reason": "no item number"})
                continue
            if code in codes:
                summary["skipped"].append({"code": code, "name": item["name_ar"], "reason": "item number already in this project's BOQ"})
                continue

            order += 1
            has_children = bool(item["sub_items"])
            price = _decimal(item["unit_price"]) if use_printed_prices else None
            phase = ProjectPhase.objects.create(
                project=project, code=code, name_ar=item["name_ar"], name_en=item["name_en"], section=section["name"],
                order=order, weight_percentage=0, notes=MARK.format(run_id=run.pk) + (f" {item['notes']}" if item["notes"] else ""),
                unit="" if has_children else item["unit"], quantity=None if has_children else _decimal(item["quantity"]),
                contract_unit_price=0 if has_children or price is None else price,
            )
            codes.add(code)
            summary["created_phases"] += 1

            if has_children:
                seen_sub_codes = set()
                for position, sub in enumerate(item["sub_items"], start=1):
                    sub_code = sub["code"]
                    if sub_code in seen_sub_codes:
                        sub_code = f"{sub_code}-{position}"
                    seen_sub_codes.add(sub_code)
                    sub_price = _decimal(sub["unit_price"]) if use_printed_prices else None
                    ProjectPhaseSubItem.objects.create(
                        phase=phase, code=sub_code, name_ar=sub["name_ar"], name_en=sub["name_en"], weight_percentage=0,
                        unit=sub["unit"], quantity=_decimal(sub["quantity"]), order=position,
                        contract_unit_price=0 if sub_price is None else sub_price,
                    )
                    summary["created_sub_items"] += 1
            else:
                phase.sync_whole_item()
                summary["created_sub_items"] += 1
    return summary


def compare_with_boq(project: Project, draft: dict) -> dict:
    """
    How a document's items line up with what is already in the project's BOQ: numbers only in the document,
    numbers only in the BOQ, and quantities that differ. Exact comparison, no AI.
    """
    phases = {p.code: p for p in ProjectPhase.objects.filter(project=project).prefetch_related("sub_items")}
    boq_leaves = {}
    for phase in phases.values():
        for sub in phase.sub_items.all():
            boq_leaves[sub.code or phase.code] = sub.quantity
        boq_leaves.setdefault(phase.code, None)

    doc_codes, doc_leaves = set(), {}
    for section in draft["sections"]:
        for item in section["items"]:
            doc_codes.add(item["code"])
            if item["sub_items"]:
                for sub in item["sub_items"]:
                    doc_leaves[sub["code"]] = _decimal(sub["quantity"])
            else:
                doc_leaves[item["code"]] = _decimal(item["quantity"])

    differences = [
        {"code": code, "document": str(doc_qty), "boq": str(boq_leaves[code])}
        for code, doc_qty in doc_leaves.items()
        if doc_qty is not None and boq_leaves.get(code) is not None and Decimal(str(boq_leaves[code])) != doc_qty
    ]
    return {
        "only_in_document": sorted(c for c in doc_codes if c and c not in phases),
        "only_in_boq": sorted(c for c in phases if c not in doc_codes),
        "quantity_differences": differences,
    }
