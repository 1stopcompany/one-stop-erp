"""
Green-building (EDGE) data.

EDGE (Excellence in Design for Greater Efficiencies, from the IFC / World Bank Group) certifies a building that uses at least 20%
less energy, less water and less energy embodied in its materials than a local reference building. The savings themselves are
calculated inside the official EDGE app against local baselines -- this module does NOT calculate or promise any EDGE result.
What it does is the step before: it collects, from the drawings and specifications, the design facts the EDGE app asks for
(envelope, systems, fixtures, materials), shows which ones the documents state, and lists the ones still missing so the designer
can be asked for them.

The list of facts is fixed here (not invented by the model): the model can only fill these points, and "missing" is worked out in
code from what it did not find.
"""
from decimal import Decimal, InvalidOperation

ENERGY, WATER, MATERIALS = "energy", "water", "materials"
DOMAIN_LABELS = {ENERGY: "Energy", WATER: "Water", MATERIALS: "Materials"}

# (id, domain, label, what to look for)
POINTS = [
    # ---- energy: building and envelope
    ("gross_floor_area", ENERGY, "Gross floor area and number of floors", "total built area (m2), floors above and below ground"),
    ("wall_construction", ENERGY, "External wall construction", "layers, materials and thickness of external walls"),
    ("wall_insulation", ENERGY, "External wall insulation", "insulation material and thickness in external walls"),
    ("wall_finish_colour", ENERGY, "External wall finish and colour", "paint / cladding colour or reflectance of external walls"),
    ("roof_construction", ENERGY, "Roof construction", "roof build-up: slab, layers, thickness"),
    ("roof_insulation", ENERGY, "Roof insulation", "insulation material and thickness on the roof"),
    ("roof_finish_colour", ENERGY, "Roof finish and colour", "roof finish, colour, reflective coating or reflectance (SRI)"),
    ("floor_insulation", ENERGY, "Ground floor insulation", "insulation under or over the ground floor slab"),
    ("glazing_type", ENERGY, "Glazing type", "single / double glazing, low-E or tinted, glass thickness and gap"),
    ("window_frame", ENERGY, "Window frame material", "frame material (aluminium, uPVC, wood) and thermal break"),
    ("window_performance", ENERGY, "Window U-value and SHGC", "printed U-value and solar heat gain coefficient of windows / glass"),
    ("window_areas", ENERGY, "Window areas or window-to-wall ratio", "printed glazed areas per facade or a stated window-to-wall ratio"),
    ("shading", ENERGY, "External shading", "overhangs, fins, louvres, shutters and their dimensions"),
    ("natural_ventilation", ENERGY, "Natural ventilation and ceiling fans", "operable windows, cross-ventilation, ceiling fans"),
    # ---- energy: systems
    ("cooling_system", ENERGY, "Cooling system and efficiency", "air-conditioning type and efficiency (COP / EER / SEER)"),
    ("heating_system", ENERGY, "Space heating system and efficiency", "heating source and efficiency"),
    ("hot_water", ENERGY, "Hot water system", "solar water heater, heat pump, electric or gas heater"),
    ("ventilation_recovery", ENERGY, "Mechanical ventilation and heat recovery", "fresh-air units, heat-recovery ventilators"),
    ("lighting_fixtures", ENERGY, "Lighting fixtures", "LED / fluorescent, wattage, lighting power density"),
    ("lighting_controls", ENERGY, "Lighting controls", "occupancy sensors, daylight sensors, timers"),
    ("renewable_energy", ENERGY, "On-site renewable energy", "solar PV capacity (kWp), solar collectors area, wind"),
    ("energy_metering", ENERGY, "Energy metering and controls", "sub-meters, building management system"),
    # ---- water
    ("wc_flush", WATER, "WC flush volume", "litres per flush, single or dual flush"),
    ("basin_taps", WATER, "Basin tap flow rate", "litres per minute, aerators"),
    ("kitchen_taps", WATER, "Kitchen tap flow rate", "litres per minute, aerators"),
    ("shower_heads", WATER, "Shower flow rate", "litres per minute"),
    ("urinals", WATER, "Urinals", "flush volume or waterless"),
    ("irrigation", WATER, "Landscape and irrigation", "landscaped area, irrigation type (drip, sprinkler), plant types"),
    ("rainwater_harvesting", WATER, "Rainwater harvesting", "collection area, tank capacity"),
    ("greywater_recycling", WATER, "Greywater recycling", "treatment plant and reuse"),
    ("water_metering", WATER, "Water metering and leak detection", "sub-meters, leak detection"),
    # ---- materials
    ("floor_slab", MATERIALS, "Floor slab", "type (reinforced concrete, ribbed, flat) and thickness"),
    ("roof_structure", MATERIALS, "Roof structure", "type and thickness of the roof slab or structure"),
    ("internal_walls", MATERIALS, "Internal walls", "material (block, drywall, brick) and thickness"),
    ("floor_finish", MATERIALS, "Floor finish", "tiles, marble, terrazzo, wood, carpet, screed"),
    ("insulation_material", MATERIALS, "Insulation material", "type of insulation used (XPS, EPS, rockwool, PUR)"),
]
POINT_IDS = [p[0] for p in POINTS]
POINT_BY_ID = {p[0]: {"id": p[0], "domain": p[1], "label": p[2], "hint": p[3]} for p in POINTS}


def prompt_section() -> str:
    """The checklist as text for the model's instructions."""
    lines = []
    for domain in (ENERGY, WATER, MATERIALS):
        lines.append(f"{DOMAIN_LABELS[domain].upper()}:")
        lines += [f"  {pid} = {p['label']} ({p['hint']})" for pid, p in POINT_BY_ID.items() if p["domain"] == domain]
    return "\n".join(lines)


GREEN_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "point": {"type": "string", "enum": POINT_IDS},
        "value": {"type": "string"},
        "number": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "unit": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "location": {"type": "string"},
        "source_page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["point", "value", "number", "unit", "location", "source_page", "confidence", "notes"],
    "additionalProperties": False,
}


def _text(value, limit):
    return (str(value) if value is not None else "").strip()[:limit]


def _number(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return str(number) if number >= 0 else None


def clean_green(raw_items) -> list:
    """What the model found, made safe: only known points, an empty statement is dropped, lengths capped."""
    cleaned = []
    for entry in raw_items or []:
        if not isinstance(entry, dict) or entry.get("point") not in POINT_BY_ID:
            continue
        value = _text(entry.get("value"), 400)
        if not value:
            continue
        cleaned.append({
            "point": entry["point"], "value": value, "number": _number(entry.get("number")), "unit": _text(entry.get("unit"), 20),
            "location": _text(entry.get("location"), 120),
            "source_page": entry.get("source_page") if isinstance(entry.get("source_page"), int) else None,
            "confidence": entry.get("confidence") if entry.get("confidence") in ("high", "medium", "low") else "medium",
            "notes": _text(entry.get("notes"), 300),
        })
    return cleaned


def coverage(found_items, sources=None) -> dict:
    """
    Which of the fixed points the documents state and which they don't. `found_items` are cleaned entries (optionally carrying a
    "source" label). Returns {"domains": [{domain, label, found, total, points: [{id, label, hint, entries: [...]}]}], "missing": [...]}.
    """
    by_point = {}
    for entry in found_items:
        by_point.setdefault(entry["point"], []).append(entry)
    domains, missing = [], []
    for domain in (ENERGY, WATER, MATERIALS):
        points = []
        for pid, meta in POINT_BY_ID.items():
            if meta["domain"] != domain:
                continue
            entries = by_point.get(pid, [])
            points.append({**meta, "entries": entries})
            if not entries:
                missing.append(meta)
        found = sum(1 for p in points if p["entries"])
        domains.append({"domain": domain, "label": DOMAIN_LABELS[domain], "found": found, "total": len(points), "points": points})
    total = len(POINT_BY_ID)
    return {"domains": domains, "missing": missing, "found": total - len(missing), "total": total}


def project_edge_data(project) -> dict:
    """
    The green-building facts across ALL the documents analysed for a project (the latest finished analysis of each document),
    each entry labelled with where it came from, plus what is still missing.
    """
    from .models import AIRun

    runs, seen = [], set()
    for run in AIRun.objects.filter(project=project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE).order_by("-created_at"):
        key = (run.source_revision_id, run.source_tender_id, run.source_label)
        if key in seen or not run.result:
            continue
        seen.add(key)
        runs.append(run)
    found = []
    for run in runs:
        for entry in run.result.get("green_data", []):
            found.append({**entry, "source": run.source_label, "run_id": run.pk})
    data = coverage(found)
    data["documents"] = [{"label": r.source_label, "run_id": r.pk, "read_on": r.created_at} for r in runs]
    return data
