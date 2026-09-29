"""
Reading a tender document / specification / drawing set into a DRAFT bill of quantities.

The model is asked to transcribe, not to estimate: quantities that are not written in the
document stay empty. Its answer is forced into a fixed JSON shape, then cleaned (`clean_draft`)
before it is ever shown or imported, so nothing it says can put a malformed value into the BOQ.
"""
from decimal import Decimal, InvalidOperation

from . import llm
from .documents import source_of

SYSTEM_PROMPT = """You are a quantity surveyor's assistant for a construction contractor in Palestine. You read tender documents \
(bills of quantities, specifications) and drawing sets, and turn them into a draft bill of quantities (BOQ) that a person will \
review before anything is used.

Rules:
- TRANSCRIBE, do not estimate. Copy item numbers, descriptions, units and quantities exactly as the document shows them. \
If a quantity, unit or price is blank or unreadable, use null. Never invent or calculate a quantity that is not written in the document.
- For DRAWINGS: extract only what is written on them (schedules such as door / window / finish / fixture schedules, quantities in \
notes, room areas that are printed). Do NOT measure quantities off the geometry. Set confidence to "low" for anything you had to infer.
- Keep the document's own structure: sections (e.g. Civil works, Electrical works, Mechanical works), main items, and sub-items \
(lines such as 1.17.1, 2.4.3, or lettered a/b/c under a main item). A main item that has its own unit and quantity and no sub-items \
is a "whole" item: give it unit and quantity and leave sub_items empty. A main item that is only a heading over sub-items has no \
unit or quantity of its own.
- Keep the original item number in "code" even when it looks wrong. Report numbering slips, duplicated numbers, skipped numbers, \
unreadable items, blank quantities, and any inconsistency you notice in "issues" - do not silently fix them.
- Names: put the item's title in name_ar if the document is in Arabic (short, one line, not the whole specification paragraph) and \
give a short English translation in name_en; if the document is in English, put it in name_en and translate to name_ar. \
Put long specification text in "notes" only if it contains something a buyer needs (brand, size, standard).
- unit_price is the price printed in the document if it has one (a priced BOQ), else null.
- source_page is the page number where the line appears, if you can tell.
- confidence: "high" when the line is clear, "medium" when you had to interpret, "low" when you are unsure.
- If the document is not a BOQ or schedule of quantities (for example a contract, or a drawing with no schedules), say so in \
document_summary and return few or no items rather than guessing."""

def _nullable(kind):
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


ITEM = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "name_ar": {"type": "string"},
        "name_en": {"type": "string"},
        "unit": _nullable("string"),
        "quantity": _nullable("number"),
        "unit_price": _nullable("number"),
        "source_page": _nullable("integer"),
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["code", "name_ar", "name_en", "unit", "quantity", "unit_price", "source_page", "confidence", "notes"],
    "additionalProperties": False,
}
MAIN_ITEM = {
    **ITEM,
    "properties": {**ITEM["properties"], "sub_items": {"type": "array", "items": ITEM}},
    "required": ITEM["required"] + ["sub_items"],
}
BOQ_SCHEMA = {
    "type": "object",
    "properties": {
        "document_summary": {"type": "string"},
        "currency": _nullable("string"),
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "items": {"type": "array", "items": MAIN_ITEM}},
                "required": ["name", "items"],
                "additionalProperties": False,
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                    "message": {"type": "string"},
                    "item_code": _nullable("string"),
                },
                "required": ["severity", "message", "item_code"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["document_summary", "currency", "sections", "issues"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------ cleaning

def _text(value, limit):
    return (str(value) if value is not None else "").strip()[:limit]


def _number(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number >= 0 else None


def _item(raw, key):
    return {
        "key": key,
        "code": _text(raw.get("code"), 20),
        "name_ar": _text(raw.get("name_ar"), 255) or _text(raw.get("name_en"), 255),
        "name_en": _text(raw.get("name_en"), 255),
        "unit": _text(raw.get("unit"), 20),
        "quantity": None if _number(raw.get("quantity")) is None else str(_number(raw.get("quantity"))),
        "unit_price": None if _number(raw.get("unit_price")) is None else str(_number(raw.get("unit_price"))),
        "source_page": raw.get("source_page") if isinstance(raw.get("source_page"), int) else None,
        "confidence": raw.get("confidence") if raw.get("confidence") in ("high", "medium", "low") else "medium",
        "notes": _text(raw.get("notes"), 500),
    }


def clean_draft(raw: dict) -> dict:
    """
    The model's answer, made safe: lengths capped, numbers parsed as non-negative decimals (kept as strings so
    they survive JSON), every item given a stable `key`, repeated item numbers made visible instead of colliding.
    """
    sections = []
    seen_codes, duplicates = {}, []
    for si, section in enumerate(raw.get("sections") or []):
        items = []
        for ii, main in enumerate(section.get("items") or []):
            item = _item(main, f"s{si}-i{ii}")
            item["sub_items"] = [_item(sub, f"s{si}-i{ii}-c{ci}") for ci, sub in enumerate(main.get("sub_items") or [])]
            code = item["code"]  # only main item numbers must be unique (they become phase codes)
            if code:
                if code in seen_codes:
                    duplicates.append(code)
                seen_codes[code] = True
            items.append(item)
        sections.append({"name": _text(section.get("name"), 100), "items": items})

    issues = [
        {"severity": i.get("severity") if i.get("severity") in ("info", "warning", "error") else "info",
         "message": _text(i.get("message"), 500), "item_code": _text(i.get("item_code"), 20) or None}
        for i in (raw.get("issues") or []) if i.get("message")
    ]
    for code in sorted(set(duplicates)):
        issues.append({"severity": "warning", "message": f"Item number {code} appears more than once in this document.", "item_code": code})

    return {
        "document_summary": _text(raw.get("document_summary"), 2000),
        "currency": _text(raw.get("currency"), 20) or None,
        "sections": sections,
        "issues": issues,
    }


def draft_totals(draft: dict) -> dict:
    main = sum(len(s["items"]) for s in draft["sections"])
    subs = sum(len(i["sub_items"]) for s in draft["sections"] for i in s["items"])
    return {"sections": len(draft["sections"]), "items": main, "sub_items": subs}


# ------------------------------------------------------------------ the run

def extract_boq(run, client=None):
    """Read the run's document and store the cleaned draft on it. Returns the draft."""
    name, file_obj = source_of(run)
    note = f"Project: {run.project.name} ({run.project.project_symbol}).\nFile: {name}."
    if run.instructions:
        note += f"\nInstructions from the user: {run.instructions}"
    raw, tokens_in, tokens_out = llm.read_document(
        name, file_obj, system=SYSTEM_PROMPT, schema=BOQ_SCHEMA, note=note + "\n\nRead the document and return the draft BOQ.", client=client,
    )
    draft = clean_draft(raw)
    draft["totals"] = draft_totals(draft)
    run.result = draft
    run.input_tokens, run.output_tokens = tokens_in, tokens_out
    return draft
