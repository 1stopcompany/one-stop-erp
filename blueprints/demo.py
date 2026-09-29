"""
Demo data for the drawings side of a project: insurance policies, tender documents, engineering drawings with revisions in every
status, and the AI analyses of them -- so the Workflow, Drawings, AI Assistant and green-building (EDGE) pages have something real to show.

The drawings and documents are REAL PDFs generated here (a plan sketch, a schedule and notes each), so the "Analyze" button works
on them with a live AI too. The AI analyses stored with them are built from the very same schedules (`takeoff.clean_takeoff`), so what a
page shows always matches what the PDF says. They are marked as demo data (model name "demo-data"): nothing was sent to any AI.

The item codes the schedules point at (1.1, 1.2, 2.1 ...) are the demo project's BOQ from `seed_costing_demo`.
"""
from datetime import timedelta
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ai_assistant import takeoff
from ai_assistant.models import AIRun

from .models import Blueprint, BlueprintRevision

DEMO_NOTE = "[DEMO]"
MODEL_NAME = "demo-data"

# ---------------------------------------------------------------------------------------------------- the drawings
# Schedule rows: (mark, description, specification, location, unit, quantity or None, BOQ code or None, category)
# Green facts:   (EDGE point, value as printed, number or None, unit or None, location)
SHEETS = [
    {
        "number": "A-01", "title": "Ground floor plan and finishes schedule", "discipline": "architectural",
        "revisions": [("0", "superseded", ""), ("A", "approved", "")],
        "rooms": [("Lobby", 0, 0, 40, 30), ("Offices", 40, 0, 70, 50), ("Toilets", 0, 30, 25, 20), ("Corridor", 25, 30, 15, 20)],
        "schedule": [
            ("F1", "Ceramic floor tiles 60x60", "PEI 4, matt", "Lobby and corridors", "m2", 180, "3.1", "finish"),
            ("F2", "Ceramic floor tiles 60x60", "PEI 4, matt", "Offices", "m2", 340, "3.1", "finish"),
            ("F3", "Anti-slip porcelain tiles 30x30", "R11", "Toilets", "m2", 48, "3.1", "finish"),
            ("W1", "Emulsion paint, 3 coats", "Washable, low VOC", "All internal walls", "m2", 1320, "3.2", "finish"),
            ("C1", "Suspended gypsum board ceiling", "12.5 mm, moisture resistant in toilets", "Offices and toilets", "m2", 388, None, "finish"),
            ("R1", "Waterproofing membrane", "Bituminous, 4 mm", "Roof and wet areas", "", None, None, "material"),
        ],
        "notes": [
            "Gross floor area 2,450 m2 on 5 floors above ground.",
            "External wall: 20 cm hollow concrete block, 5 cm XPS insulation, 2 cm cement plaster.",
            "External wall finish: light beige paint, solar reflectance 0.60.",
            "Internal walls: 10 cm hollow block, plastered both sides.",
            "Floor finish: ceramic and porcelain tiles on 5 cm screed.",
            "Insulation material throughout: extruded polystyrene (XPS).",
        ],
        "green": [
            ("gross_floor_area", "Gross floor area 2,450 m2, 5 floors above ground", 2450, "m2", "Whole building"),
            ("wall_construction", "20 cm hollow concrete block with 2 cm cement plaster", 20, "cm", "External walls"),
            ("wall_insulation", "5 cm XPS insulation", 5, "cm", "External walls"),
            ("wall_finish_colour", "Light beige paint, solar reflectance 0.60", 0.6, "", "External walls"),
            ("internal_walls", "10 cm hollow block, plastered both sides", 10, "cm", "Internal walls"),
            ("floor_finish", "Ceramic and porcelain tiles on 5 cm screed", None, "", "All floors"),
            ("insulation_material", "Extruded polystyrene (XPS)", None, "", "Walls and roof"),
        ],
    },
    {
        "number": "A-02", "title": "Door and window schedule", "discipline": "architectural",
        "revisions": [("0", "approved", "")],
        "rooms": [("South facade", 0, 0, 90, 8), ("North facade", 0, 42, 90, 8)],
        "schedule": [
            ("W1", "Aluminium window, double glazed", "Low-E 6-12-6 mm, thermal break frame", "Offices, south and north", "no.", 42, None, "opening"),
            ("W2", "Aluminium window, double glazed", "Low-E 6-12-6 mm, thermal break frame", "Toilets", "no.", 8, None, "opening"),
            ("D1", "Timber door 0.9 x 2.1 m", "Solid core, veneered", "Offices", "no.", 60, None, "opening"),
            ("D2", "Fire door 1.0 x 2.1 m", "60 minutes, steel", "Stairs and plant room", "no.", 8, None, "opening"),
        ],
        "notes": [
            "Window-to-wall ratio: 24 %.",
            "Glazing: double glazed low-E 6-12-6 mm. Frames: aluminium with thermal break.",
            "External shading: horizontal overhang 0.60 m on the south facade.",
        ],
        "green": [
            ("glazing_type", "Double glazing low-E 6-12-6 mm", 6, "mm", "All windows"),
            ("window_frame", "Aluminium frame with thermal break", None, "", "All windows"),
            ("window_areas", "Window-to-wall ratio 24 %", 24, "%", "Whole building"),
            ("shading", "Horizontal overhang 0.60 m", 0.6, "m", "South facade"),
        ],
    },
    {
        "number": "S-01", "title": "Foundation plan", "discipline": "structural",
        "revisions": [("0", "approved", "")],
        "rooms": [("Footing F1", 0, 0, 30, 20), ("Footing F2", 40, 0, 30, 20), ("Footing F3", 0, 30, 30, 20), ("Footing F4", 40, 30, 30, 20)],
        "schedule": [
            ("EX", "Excavation to formation level", "Machine, including disposal", "Building footprint", "m3", 310, "1.1", "structural"),
            ("BL", "Blinding concrete C15", "10 cm thick", "Under footings", "m3", 18, None, "material"),
            ("FT", "Reinforced concrete footings C30", "Sulphate resistant cement", "Foundations", "m3", 130, "1.2", "structural"),
            ("RB", "Reinforcement steel B500", "Deformed bars", "Footings", "ton", 9.5, None, "material"),
        ],
        "notes": [
            "Ground floor slab: 15 cm reinforced concrete on 10 cm compacted base.",
            "Floor slab type for all upper floors: see S-02.",
        ],
        "green": [
            ("floor_slab", "Ground floor slab 15 cm reinforced concrete on 10 cm compacted base", 15, "cm", "Ground floor"),
        ],
    },
    {
        "number": "S-02", "title": "Columns, slabs and blockwork", "discipline": "structural",
        "revisions": [("0", "approved", "")],
        "rooms": [("Grid A-D", 0, 0, 90, 50)],
        "schedule": [
            ("CS", "Reinforced concrete columns and slabs C30", "Ribbed slab 22 cm", "Floors 1 to 5", "m3", 262, "2.1", "structural"),
            ("BW", "Hollow concrete block 20 cm", "Load bearing and external walls", "All floors", "m2", 790, "2.2", "material"),
        ],
        "notes": [
            "Typical floor slab: 22 cm ribbed reinforced concrete slab.",
            "Roof slab: 25 cm reinforced concrete with 8 cm XPS insulation, white reflective finish (SRI 78).",
        ],
        "green": [
            ("floor_slab", "Typical floor slab 22 cm ribbed reinforced concrete", 22, "cm", "Floors 1 to 5"),
            ("roof_structure", "Roof slab 25 cm reinforced concrete", 25, "cm", "Roof"),
            ("roof_insulation", "8 cm XPS insulation on the roof", 8, "cm", "Roof"),
            ("roof_finish_colour", "White reflective finish, SRI 78", 78, "SRI", "Roof"),
            ("roof_construction", "25 cm reinforced concrete slab, 8 cm XPS, white reflective finish", None, "", "Roof"),
        ],
    },
    {
        "number": "M-01", "title": "HVAC layout and equipment schedule", "discipline": "mechanical",
        "revisions": [("0", "pending", "")],
        "rooms": [("Plant room", 0, 0, 20, 20), ("Offices", 25, 0, 65, 50)],
        "schedule": [
            ("OU", "VRF outdoor unit", "Cooling COP 4.2", "Roof", "no.", 2, None, "mep"),
            ("IU", "Ceiling cassette indoor unit", "Inverter", "Offices", "no.", 24, None, "mep"),
            ("FA", "Fresh air unit with heat recovery", "Enthalpy wheel, 75 % recovery", "Roof", "no.", 2, None, "mep"),
        ],
        "notes": [
            "Cooling: VRF system, cooling COP 4.2.",
            "Mechanical ventilation with heat recovery in all office floors.",
        ],
        "green": [
            ("cooling_system", "VRF system, cooling COP 4.2", 4.2, "COP", "Whole building"),
            ("ventilation_recovery", "Fresh air units with heat recovery, 75 % recovery", 75, "%", "Office floors"),
        ],
    },
    {
        "number": "E-01", "title": "Lighting and small power plan", "discipline": "electrical",
        "revisions": [("0", "rejected", "Fixture wattages and lighting power density are missing. Reissue with the complete lighting schedule.")],
        "rooms": [("Offices", 0, 0, 60, 40), ("Corridor", 60, 0, 30, 40)],
        "schedule": [
            ("L1", "LED panel 600x600", "36 W", "Offices", "no.", 180, None, "equipment"),
            ("OS", "Occupancy sensor", "Ceiling mounted", "Toilets and corridors", "no.", 24, None, "equipment"),
            ("P1", "Power outlet points", "13 A double socket", "All floors", "No.", 96, "4", "equipment"),
        ],
        "notes": [
            "All luminaires are LED. Occupancy sensors control lighting in toilets and corridors.",
            "Rooftop photovoltaic system: 30 kWp.",
        ],
        "green": [
            ("lighting_fixtures", "LED panels 36 W", 36, "W", "Offices"),
            ("lighting_controls", "Occupancy sensors in toilets and corridors", None, "", "Toilets and corridors"),
            ("renewable_energy", "Rooftop photovoltaic system 30 kWp", 30, "kWp", "Roof"),
        ],
    },
    {
        "number": "P-01", "title": "Plumbing and sanitary layout", "discipline": "plumbing",
        "revisions": [("0", "pending", "")],
        "rooms": [("Toilets", 0, 0, 30, 20), ("Roof tank", 40, 0, 25, 20)],
        "schedule": [
            ("WC", "Water closet, dual flush", "3 / 6 litres", "Toilets", "no.", 28, None, "equipment"),
            ("LB", "Wash basin with aerated tap", "6 litres per minute", "Toilets", "no.", 30, None, "equipment"),
            ("UR", "Waterless urinal", "", "Toilets", "no.", 6, None, "equipment"),
            ("RW", "Rainwater harvesting tank", "40 m3", "Basement", "no.", 1, None, "equipment"),
            ("SW", "Solar water heater", "Roof mounted, 4 panels", "Roof", "no.", 1, None, "equipment"),
        ],
        "notes": [
            "WC dual flush 3 / 6 litres. Basin taps 6 litres per minute with aerators. Waterless urinals.",
            "Rainwater harvesting: roof catchment to a 40 m3 tank, used for irrigation.",
            "Landscape irrigation: drip system.",
            "Hot water: roof-mounted solar water heater with electric backup.",
        ],
        "green": [
            ("wc_flush", "Dual flush 3 / 6 litres", 6, "L", "Toilets"),
            ("basin_taps", "Basin taps 6 litres per minute with aerators", 6, "L/min", "Toilets"),
            ("urinals", "Waterless urinals", None, "", "Toilets"),
            ("rainwater_harvesting", "Roof catchment to a 40 m3 tank", 40, "m3", "Basement"),
            ("irrigation", "Drip irrigation system", None, "", "Landscape"),
            ("hot_water", "Roof-mounted solar water heater with electric backup", None, "", "Roof"),
        ],
    },
    {
        "number": "C-01", "title": "Site layout and external paving", "discipline": "civil",
        "revisions": [("0", "pending", "")],
        "cad": True,      # a CAD source file: the AI can't read it, which shows the "AI failed" state
        "schedule": [("PV", "Interlocking paving", "8 cm, grey", "Car park", "m2", 300, "5", "finish")],
        "notes": [],
        "green": [],
    },
]

# Documents analysed for tender / specifications: what the spec adds to the EDGE picture.
SPEC_GREEN = [
    ("window_performance", "Window U-value 2.1 W/m2K, solar heat gain coefficient 0.40", 2.1, "W/m2K", "All windows"),
    ("shower_heads", "Shower heads 9 litres per minute", 9, "L/min", "Bathrooms"),
    ("kitchen_taps", "Kitchen taps 6 litres per minute", 6, "L/min", "Pantries"),
    ("energy_metering", "Energy sub-metering per floor and a building management system", None, "", "Whole building"),
]
TENDER_DOCS = [
    ("contract", "[DEMO] Contract agreement", ["Contract agreement between the Client and the Contractor.", "Contract period: 18 months from the start date."]),
    ("conditions", "[DEMO] General conditions of contract", ["General and particular conditions of contract.", "Retention: 10 % of each certified payment."]),
    ("specifications", "[DEMO] Technical specifications",
     ["Technical specifications, sections 1 to 12.", "Windows: U-value 2.1 W/m2K, solar heat gain coefficient 0.40.",
      "Shower heads: 9 litres per minute. Kitchen taps: 6 litres per minute.",
      "Energy sub-metering per floor and a building management system are required."]),
    ("boq", "[DEMO] Bill of quantities", ["Bill of quantities for the works.", "See the priced BOQ in the project."]),
    ("addendum", "[DEMO] Addendum 1", ["Addendum 1: clarification of finishes in the ground floor lobby."]),
]
INSURANCES = [
    ("car", "Demo Insurance Co.", "CAR-DEMO-001", 4_500_000, 30, 335),
    ("third_party", "Demo Insurance Co.", "TPL-DEMO-002", 1_000_000, 30, 335),
    ("performance_bond", "Demo Bank", "PB-DEMO-003", 450_000, 200, 21),      # expires in 21 days: the "expiring" warning
    ("workers", "Demo Insurance Co.", "WC-DEMO-004", 500_000, 400, -35),      # ended 35 days ago: the "expired" state
]


# ---------------------------------------------------------------------------------------------------- the PDFs

def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Heading1"], fontSize=15, spaceAfter=4),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#555555")),
        "note": ParagraphStyle("n", parent=base["Normal"], fontSize=9, leading=12),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8, leading=10),
    }


def _sketch(rooms, width_mm=250, height_mm=62):
    """A very simple plan sketch: labelled rectangles."""
    drawing = Drawing(width_mm * mm, height_mm * mm)
    drawing.add(Rect(0, 0, width_mm * mm, height_mm * mm, strokeColor=colors.HexColor("#999999"), fillColor=colors.HexColor("#fafafa")))
    for label, x, y, w, h in rooms:
        rx, ry = 6 * mm + x * 2.3 * mm, 4 * mm + y * 1.0 * mm
        drawing.add(Rect(rx, ry, w * 2.3 * mm, h * 1.0 * mm, strokeColor=colors.HexColor("#2c3e50"), fillColor=colors.HexColor("#eaf1fb")))
        drawing.add(String(rx + 2 * mm, ry + h * 0.5 * mm, label, fontSize=7, fillColor=colors.HexColor("#2c3e50")))
    return drawing


def sheet_pdf(sheet, revision, note="") -> bytes:
    """One drawing sheet as a real PDF: title block, plan sketch, schedule and general notes (all extractable text)."""
    S = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"{sheet['number']} rev {revision} - {sheet['title']}")
    story = [
        Paragraph(f"{sheet['number']} - {sheet['title']}", S["title"]),
        Paragraph(f"Project: [DEMO] Cost Control Tower &nbsp;|&nbsp; Discipline: {sheet['discipline'].title()} &nbsp;|&nbsp; Revision {revision} "
                  f"&nbsp;|&nbsp; Scale 1:100 &nbsp;|&nbsp; Demo drawing generated for training, not a real design", S["small"]),
        Spacer(1, 4 * mm),
    ]
    if sheet.get("rooms"):
        story += [_sketch(sheet["rooms"]), Spacer(1, 4 * mm)]
    if sheet["schedule"]:
        rows = [["Mark", "Description", "Specification", "Location", "Unit", "Quantity"]]
        for mark, description, spec, location, unit, quantity, _code, _cat in sheet["schedule"]:
            rows.append([mark, Paragraph(description, S["cell"]), Paragraph(spec, S["cell"]), Paragraph(location, S["cell"]), unit,
                         "" if quantity is None else f"{quantity:g}"])
        table = Table(rows, colWidths=[16 * mm, 78 * mm, 62 * mm, 52 * mm, 14 * mm, 22 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4788")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story += [Paragraph("Schedule", S["title"]), table, Spacer(1, 4 * mm)]
    if sheet["notes"]:
        story.append(Paragraph("General notes", S["title"]))
        story += [Paragraph(f"{i}. {text}", S["note"]) for i, text in enumerate(sheet["notes"], start=1)]
    if note:
        story += [Spacer(1, 3 * mm), Paragraph(f"Revision note: {note}", S["small"])]
    doc.build(story)
    return buffer.getvalue()


def text_pdf(title, lines) -> bytes:
    """A plain one-page document (certificate, contract, specification)."""
    S = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=title)
    story = [Paragraph(title, S["title"]), Paragraph("Demo document generated for training. Not a real document.", S["small"]), Spacer(1, 6 * mm)]
    story += [Paragraph(line, S["note"]) for line in lines]
    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------------------------------- the analyses

def takeoff_result(sheet) -> dict:
    """The AI-style analysis of a sheet, built from the same schedule the PDF prints."""
    items = [{
        "category": category, "description": description, "specification": spec, "location": location, "unit": unit or None,
        "quantity": quantity, "quantity_basis": "printed" if quantity is not None else "not_stated", "boq_code": code,
        "source_page": 1, "confidence": "high", "notes": "" if quantity is not None else "Quantity not printed on the sheet",
    } for _mark, description, spec, location, unit, quantity, code, category in sheet["schedule"]]
    green = [{"point": point, "value": value, "number": number, "unit": unit or None, "location": location, "source_page": 1,
              "confidence": "high", "notes": ""} for point, value, number, unit, location in sheet["green"]]
    issues = []
    if any(row[5] is None for row in sheet["schedule"]):
        issues.append({"severity": "info", "message": "Some items have no printed quantity; they are listed so the buyer knows they are required."})
    return takeoff.clean_takeoff({"drawing_summary": f"{sheet['title']} ({sheet['discipline']}). Demo analysis built from the printed schedule.",
                                  "items": items, "green_data": green, "issues": issues})


# ---------------------------------------------------------------------------------------------------- seed / clear

def _run(project, admin, label, result=None, *, revision=None, tender=None, error=""):
    now = timezone.now()
    return AIRun.objects.create(
        project=project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.FAILED if error else AIRun.DONE, source_label=label,
        source_revision=revision, source_tender=tender, instructions=DEMO_NOTE, result=result, error=error,
        model_name=MODEL_NAME, created_by=admin, started_at=now, finished_at=now,
    )


def is_seeded(project) -> bool:
    return Blueprint.objects.filter(project=project, drawing_number="A-01").exists()


def seed(project, admin, reviewer=None) -> dict:
    """Insurance, tender documents, drawings and analyses for `project`. Returns the counts."""
    today = timezone.localdate()
    counts = {"insurance": 0, "tender_documents": 0, "drawings": 0, "revisions": 0, "analyses": 0}

    for kind, insurer, number, amount, started_days_ago, days_left in INSURANCES:
        policy = project.insurances.create(
            policy_type=kind, insurer=insurer, policy_number=number, insured_amount=amount, uploaded_by=admin, notes=DEMO_NOTE,
            start_date=today - timedelta(days=started_days_ago), end_date=today + timedelta(days=days_left),
            document=ContentFile(text_pdf(f"Insurance certificate {number}", [f"Insurer: {insurer}.", f"Policy type: {kind}.", f"Insured amount: {amount:,}."]),
                                 name=f"{number}.pdf"),
        )
        counts["insurance"] += 1

    spec_document = None
    for category, title, lines in TENDER_DOCS:
        document = project.tender_documents.create(
            category=category, title=title, uploaded_by=admin, notes=DEMO_NOTE,
            document=ContentFile(text_pdf(title, lines), name=f"{category}.pdf"),
        )
        counts["tender_documents"] += 1
        if category == "specifications":
            spec_document = document
    spec_result = takeoff.clean_takeoff({
        "drawing_summary": "Technical specifications. Demo analysis: the design facts the specifications state for the green-building assessment.",
        "items": [], "issues": [],
        "green_data": [{"point": p, "value": v, "number": n, "unit": u or None, "location": loc, "source_page": 1, "confidence": "high", "notes": ""}
                       for p, v, n, u, loc in SPEC_GREEN],
    })
    _run(project, admin, f"{spec_document.get_category_display()}: {spec_document.title}", spec_result, tender=spec_document)
    counts["analyses"] += 1

    for sheet in SHEETS:
        blueprint = Blueprint.objects.create(project=project, drawing_number=sheet["number"], title=sheet["title"],
                                             discipline=sheet["discipline"], created_by=admin)
        counts["drawings"] += 1
        for revision, status, rejection in sheet["revisions"]:
            extension = "dwg" if sheet.get("cad") else "pdf"
            content = b"AC1027 demo CAD file - not a real drawing" if sheet.get("cad") else sheet_pdf(sheet, revision, rejection)
            rev = BlueprintRevision.objects.create(
                blueprint=blueprint, revision=revision, status=status, notes=DEMO_NOTE, uploaded_by=admin,
                file=ContentFile(content, name=f"{sheet['number']}-rev{revision}.{extension}"),
                reviewed_by=None if status == "pending" else (reviewer or admin),
                reviewed_at=None if status == "pending" else timezone.now(), rejection_reason=rejection if status == "rejected" else "",
            )
            counts["revisions"] += 1
            if status == "superseded":
                continue      # the older revision isn't analysed again once a newer one exists
            label = f"Drawing {sheet['number']} rev {revision}: {sheet['title']}"
            if sheet.get("cad"):
                _run(project, admin, label, revision=rev,
                     error="DWG files can't be read directly. Export the drawing to PDF from the CAD program and upload the PDF.")
            else:
                _run(project, admin, label, takeoff_result(sheet), revision=rev)
            counts["analyses"] += 1
    return counts


def clear(project) -> None:
    """Remove everything `seed` made for the project, including the stored files."""
    if project is None:
        return
    AIRun.objects.filter(project=project, model_name=MODEL_NAME).delete()
    revisions = BlueprintRevision.objects.filter(blueprint__project=project, notes=DEMO_NOTE)
    blueprint_ids = list(revisions.values_list("blueprint_id", flat=True))
    for revision in revisions:
        revision.file.delete(save=False)
    Blueprint.objects.filter(pk__in=blueprint_ids).delete()
    for policy in project.insurances.filter(notes=DEMO_NOTE):
        policy.document.delete(save=False)
    project.insurances.filter(notes=DEMO_NOTE).delete()
    for document in project.tender_documents.filter(notes=DEMO_NOTE):
        document.document.delete(save=False)
    project.tender_documents.filter(notes=DEMO_NOTE).delete()
