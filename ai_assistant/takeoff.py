"""
Reading an engineering drawing for the MATERIALS and QUANTITIES it calls for, and tying them to the project's priced BOQ.

Two rules keep this honest:
  * The model only transcribes what the sheet WRITES (schedules, legends, notes, printed areas). It is told not to measure
    with a scale, count symbols, multiply dimensions or add rows up -- an item with no printed quantity is still listed
    (the buyer needs to know it is required) but with the quantity left empty.
  * Everything numeric after that is plain code, not AI: which BOQ line an item belongs to is checked against the real
    BOQ, quantities are summed per line, compared with the BOQ quantity, and priced at the BOQ's own unit price.
"""
import re
from decimal import Decimal, InvalidOperation

from . import edge, llm
from .documents import source_of

CATEGORIES = ["material", "finish", "opening", "structural", "mep", "equipment", "other"]
CATEGORY_LABELS = {
    "material": "Materials", "finish": "Finishes", "opening": "Doors, windows & openings", "structural": "Structural",
    "mep": "Mechanical / electrical / plumbing", "equipment": "Equipment & fixtures", "other": "Other",
}
BOQ_REFERENCE_LIMIT = 400

_BASE_PROMPT = """You are a quantity surveyor's assistant for a construction contractor in Palestine. You read ONE engineering drawing \
sheet (architectural, structural, mechanical, electrical, finishing...), or a specification / tender document with the same rules, and list the materials and elements it calls for, with the \
quantities the sheet itself states. A person reviews your list; it is then compared with the project's priced bill of quantities (BOQ).

Rules:
- WRITTEN, NOT MEASURED. Transcribe only quantities that are printed on the sheet: schedules (door, window, finish, fixture, \
equipment, reinforcement), legends, general notes, printed room areas and printed dimension values that ARE the quantity. Never measure \
with a scale, never count symbols, never multiply dimensions to get an area or volume, never add rows together yourself. If unsure, leave \
the quantity empty.
- Still LIST every material, finish, opening, structural element, fixture or equipment item the sheet clearly requires, even when no quantity \
is printed: then quantity is null and quantity_basis is "not_stated". A buyer needs to know it is required.
- One schedule row = one item. Keep the mark or tag (D1, W3, F2) in the description and put the room / floor / zone in location.
- specification: sizes, types, grades, brands and standards exactly as printed. description: the item's name as printed (keep the sheet's \
language, Arabic or English).
- unit: as printed (m2, m3, m, no., kg, L.S. ...), null if none.
- category: material | finish | opening | structural | mep | equipment | other.
- boq_code: ONLY from the BOQ list given with the request, and only when the item clearly is that BOQ line. Otherwise null. Never invent a \
code.
- source_page: the page where you read it, if you can tell. confidence: high = clear, medium = you interpreted, low = unsure.
- issues: unreadable areas, missing scale or legend, values that contradict each other, a sheet that isn't a drawing. Do not silently fix them.
- If the sheet holds no material or quantity information (for example a cover sheet), say so in drawing_summary and return few or no items \
rather than guessing."""

_GREEN_PROMPT = """

GREEN-BUILDING (EDGE) DATA. Besides the item list, look for the design facts an EDGE green-building assessment needs. They are a fixed \
checklist; report each one you find in green_data, using the point id below. One entry per fact (several entries for the same point are \
fine, e.g. different wall types). value = the fact as printed (for example "Double glazing 6-12-6 mm, low-E"); number and unit only when a \
number is printed (for example 6 with L/min); location = where it applies; source_page when you can tell. Report ONLY what is written on \
the sheet or in the document: do not assume, calculate or fill in typical values, and do not report a point you cannot find (missing ones \
are worked out afterwards).

"""
SYSTEM_PROMPT = _BASE_PROMPT + _GREEN_PROMPT + edge.prompt_section()


def _nullable(kind):
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "description": {"type": "string"},
        "specification": {"type": "string"},
        "location": {"type": "string"},
        "unit": _nullable("string"),
        "quantity": _nullable("number"),
        "quantity_basis": {"type": "string", "enum": ["printed", "not_stated"]},
        "boq_code": _nullable("string"),
        "source_page": _nullable("integer"),
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["category", "description", "specification", "location", "unit", "quantity", "quantity_basis", "boq_code",
                 "source_page", "confidence", "notes"],
    "additionalProperties": False,
}
TAKEOFF_SCHEMA = {
    "type": "object",
    "properties": {
        "drawing_summary": {"type": "string"},
        "items": {"type": "array", "items": ITEM_SCHEMA},
        "green_data": {"type": "array", "items": edge.GREEN_ITEM_SCHEMA},
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"severity": {"type": "string", "enum": ["info", "warning", "error"]}, "message": {"type": "string"}},
            "required": ["severity", "message"], "additionalProperties": False,
        }},
    },
    "required": ["drawing_summary", "items", "green_data", "issues"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------ cleaning what the model said

def _text(value, limit):
    return (str(value) if value is not None else "").strip()[:limit]


def _quantity(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return str(number) if number >= 0 else None


def clean_takeoff(raw: dict) -> dict:
    """The model's answer made safe: lengths capped, numbers parsed, categories checked, every item given a key."""
    items = []
    for index, entry in enumerate(raw.get("items") or []):
        if not isinstance(entry, dict) or not (entry.get("description") or "").strip():
            continue
        quantity = _quantity(entry.get("quantity"))
        items.append({
            "key": f"t{index}",
            "category": entry.get("category") if entry.get("category") in CATEGORIES else "other",
            "description": _text(entry.get("description"), 255),
            "specification": _text(entry.get("specification"), 300),
            "location": _text(entry.get("location"), 120),
            "unit": _text(entry.get("unit"), 20),
            "quantity": quantity,
            "quantity_basis": "printed" if quantity is not None else "not_stated",
            "boq_code": _text(entry.get("boq_code"), 20) or None,
            "source_page": entry.get("source_page") if isinstance(entry.get("source_page"), int) else None,
            "confidence": entry.get("confidence") if entry.get("confidence") in ("high", "medium", "low") else "medium",
            "notes": _text(entry.get("notes"), 400),
        })
    issues = [
        {"severity": i.get("severity") if i.get("severity") in ("info", "warning", "error") else "info", "message": _text(i.get("message"), 500)}
        for i in (raw.get("issues") or []) if isinstance(i, dict) and i.get("message")
    ]
    green = edge.clean_green(raw.get("green_data"))
    return {"drawing_summary": _text(raw.get("drawing_summary"), 2000), "items": items, "green_data": green, "issues": issues,
            "totals": {"items": len(items), "with_quantity": sum(1 for i in items if i["quantity"] is not None),
                       "green_points": len({g["point"] for g in green})}}


# ------------------------------------------------------------------ the BOQ side

def _boq_lines(project):
    """[(code, name, unit, sub_item)] for every BOQ line that has a number."""
    from reports.progress_models import ProjectPhaseSubItem

    lines = []
    for sub in ProjectPhaseSubItem.objects.filter(phase__project=project).select_related("phase").order_by("phase__order", "phase__code", "order", "id"):
        code = sub.code or sub.phase.code
        if code:
            lines.append((code, sub.name_ar or sub.name_en, sub.unit, sub))
    return lines


def boq_reference(project) -> str:
    """The project's BOQ lines as text for the prompt, so the model can say which line an item belongs to."""
    lines = _boq_lines(project)
    if not lines:
        return "The project's BOQ is empty: leave boq_code null for every item."
    shown = "\n".join(f"{code} | {name} | {unit or '-'}" for code, name, unit, _ in lines[:BOQ_REFERENCE_LIMIT])
    more = f"\n(+{len(lines) - BOQ_REFERENCE_LIMIT} more lines not shown)" if len(lines) > BOQ_REFERENCE_LIMIT else ""
    return f"The project's BOQ lines (code | description | unit):\n{shown}{more}"


_UNIT_ALIASES = {
    "m²": "m2", "sqm": "m2", "sq.m": "m2", "م2": "m2", "م²": "m2", "متر مربع": "m2",
    "m³": "m3", "cum": "m3", "cu.m": "m3", "م3": "m3", "م³": "m3", "متر مكعب": "m3",
    "lm": "m", "l.m": "m", "rm": "m", "م": "m", "م.ط": "m", "متر طولي": "m",
    "nos": "no", "no.": "no", "nr": "no", "pcs": "no", "pc": "no", "عدد": "no", "قطعة": "no",
    "l.s.": "ls", "l.s": "ls", "lump sum": "ls", "lumpsum": "ls", "مقطوع": "ls", "بالمقطوع": "ls",
}


def unit_key(unit) -> str:
    text = re.sub(r"\s+", " ", (unit or "").strip().lower())
    return _UNIT_ALIASES.get(text, text)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def link_to_boq(project, takeoff: dict) -> dict:
    """
    Tie the take-off to the priced BOQ. Returns the rows with their BOQ line, the per-BOQ-line comparison (drawing quantity against
    BOQ quantity, priced at the BOQ cost price), and totals. Only ever uses a BOQ code that really exists (and is unambiguous).
    """
    index = {}
    for code, name, unit, sub in _boq_lines(project):
        index.setdefault(code, []).append((name, unit, sub))

    rows, per_line = [], {}
    matched = estimated = 0
    total_cost = Decimal("0")
    for item in takeoff.get("items", []):
        row = dict(item)
        row.update(boq=None, unit_mismatch=False, est_cost=None)
        candidates = index.get(item.get("boq_code") or "", [])
        if len(candidates) == 1:
            name, unit, sub = candidates[0]
            matched += 1
            row["boq"] = {"code": item["boq_code"], "name": name, "unit": unit, "quantity": sub.quantity, "price": sub.budget_unit_price}
            if item["quantity"] is not None:
                if unit_key(item["unit"]) == unit_key(unit):
                    cost = Decimal(item["quantity"]) * sub.budget_unit_price
                    row["est_cost"] = _money(cost)
                    total_cost += cost
                    estimated += 1
                    line = per_line.setdefault(item["boq_code"], {
                        "code": item["boq_code"], "name": name, "unit": unit, "boq_quantity": sub.quantity, "price": sub.budget_unit_price,
                        "drawing_quantity": Decimal("0"), "rows": 0,
                    })
                    line["drawing_quantity"] += Decimal(item["quantity"])
                    line["rows"] += 1
                else:
                    row["unit_mismatch"] = True
        rows.append(row)

    lines = []
    for line in per_line.values():
        boq_quantity = line["boq_quantity"]
        line["difference"] = None if boq_quantity is None else line["drawing_quantity"] - boq_quantity
        line["cost"] = _money(line["drawing_quantity"] * line["price"])
        lines.append(line)

    return {
        "rows": rows,
        "lines": lines,
        "totals": {"items": len(rows), "with_quantity": sum(1 for r in rows if r["quantity"] is not None), "matched": matched,
                   "unmatched": len(rows) - matched, "priced": estimated, "estimated_cost": _money(total_cost)},
    }


def grouped(rows):
    """[(category label, [rows])] in a fixed category order, skipping empty categories."""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    groups = {}
    for row in rows:
        groups.setdefault(row["category"], []).append(row)
    return [(CATEGORY_LABELS[c], groups[c]) for c in sorted(groups, key=order.get)]


# ------------------------------------------------------------------ the run

def extract_takeoff(run, client=None):
    """Read the run's drawing and store the cleaned take-off on it. Returns it."""
    from . import ollama

    name, file_obj = source_of(run)
    note = f"Project: {run.project.name} ({run.project.project_symbol}).\nDrawing file: {name}."
    if run.source_revision:
        blueprint = run.source_revision.blueprint
        note += f"\nSheet: {blueprint.drawing_number} - {blueprint.title} ({blueprint.get_discipline_display()}), revision {run.source_revision.revision}."
    if run.instructions:
        note += f"\nInstructions from the user: {run.instructions}"
    note += f"\n\n{boq_reference(run.project)}\n\nRead the drawing and return the take-off."

    raw, tokens_in, tokens_out = llm.read_document(
        name, file_obj, system=SYSTEM_PROMPT, schema=TAKEOFF_SCHEMA, note=note, client=client, merge=ollama.merge_takeoffs,
    )
    result = clean_takeoff(raw)
    run.result = result
    run.input_tokens, run.output_tokens = tokens_in, tokens_out
    return result
