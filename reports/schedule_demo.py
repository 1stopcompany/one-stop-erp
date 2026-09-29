"""
A demo schedule for the demo project (DEMOCC), so the Schedule page has a Primavera-style network to show: a three-level WBS,
milestones, all four link types with lags, a critical path, float, a baseline that the current schedule has slipped against, and
progress up to the data date.

Dates and float are calculated with reports.services.cpm (the company's Saturday-Thursday calendar), once for the baseline and once
for the current schedule (a few durations grew), so they are consistent with each other and with the links.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from .schedule_models import ScheduleTask
from .services import cpm

SOURCE = "[DEMO] Primavera-style demo schedule"

# (key, name, level, kind, baseline duration in work days, current duration, links [(predecessor key, type, lag)], resources)
#   kind: "summary" | "task" | "milestone"; a summary's dates come from the rows nested under it.
ROWS = [
    ("PRE", "Pre-construction", 1, "summary", 0, 0, [], ""),
    ("A1000", "Mobilization and site setup", 2, "task", 10, 10, [], "Site team"),
    ("A1010", "Survey and set-out", 2, "task", 5, 5, [("A1000", "FS", 0)], "Surveyor"),
    ("A1020", "Excavation", 2, "task", 20, 20, [("A1010", "FS", 0)], "Excavators"),
    ("FND", "Foundations", 1, "summary", 0, 0, [], ""),
    ("A2000", "Blinding and waterproofing", 2, "task", 6, 6, [("A1020", "FS", 0)], "Civil crew"),
    ("A2010", "Footings reinforcement", 2, "task", 12, 12, [("A2000", "FS", 0)], "Steel fixers"),
    ("A2020", "Footings concrete", 2, "task", 8, 12, [("A2010", "FS", 0)], "Concrete crew"),
    ("A2030", "Backfill and compaction", 2, "task", 7, 7, [("A2020", "FS", 2)], "Civil crew"),
    ("M2000", "Foundations complete", 2, "milestone", 0, 0, [("A2030", "FS", 0)], ""),
    ("STR", "Structure", 1, "summary", 0, 0, [], ""),
    ("GF", "Ground floor", 2, "summary", 0, 0, [], ""),
    ("A3000", "Ground floor columns and slab", 3, "task", 25, 25, [("M2000", "FS", 0)], "Concrete crew"),
    ("A3005", "Ground floor blockwork", 3, "task", 18, 18, [("A3000", "SS", 15)], "Masons"),
    ("FF1", "First floor", 2, "summary", 0, 0, [], ""),
    ("A3010", "First floor columns and slab", 3, "task", 25, 29, [("A3000", "FS", 0)], "Concrete crew"),
    ("A3015", "First floor blockwork", 3, "task", 18, 18, [("A3010", "SS", 15), ("A3005", "FS", 0)], "Masons"),
    ("SF2", "Second floor", 2, "summary", 0, 0, [], ""),
    ("A3020", "Second floor columns and slab", 3, "task", 25, 25, [("A3010", "FS", 0)], "Concrete crew"),
    ("A3025", "Second floor blockwork", 3, "task", 18, 18, [("A3020", "SS", 15), ("A3015", "FS", 0)], "Masons"),
    ("A3040", "Roof slab", 2, "task", 22, 22, [("A3020", "FS", 0)], "Concrete crew"),
    ("M3000", "Structure complete", 2, "milestone", 0, 0, [("A3040", "FS", 0), ("A3025", "FS", 0)], ""),
    ("FIN", "Finishes and services", 1, "summary", 0, 0, [], ""),
    ("A4000", "Internal plastering", 2, "task", 35, 35, [("A3015", "FS", 0), ("A3025", "FF", 0)], "Plasterers"),
    ("A4010", "Electrical first fix", 2, "task", 30, 30, [("A3015", "SS", 10)], "Electricians"),
    ("A4020", "Plumbing first fix", 2, "task", 25, 25, [("A3015", "SS", 10)], "Plumbers"),
    ("A4050", "Windows and doors", 2, "task", 18, 18, [("A4000", "FS", 0)], "Carpenters"),
    ("A4030", "Floor tiling", 2, "task", 30, 30, [("A4000", "FS", 3)], "Tilers"),
    ("A4040", "Painting", 2, "task", 28, 28, [("A4030", "SS", 10), ("A4050", "FS", 0)], "Painters"),
    ("A4060", "Electrical second fix", 2, "task", 20, 20, [("A4030", "FF", 0), ("A4010", "FS", 10)], "Electricians"),
    ("A4070", "HVAC installation", 2, "task", 25, 25, [("A4010", "FS", 0), ("A4020", "FS", 0)], "HVAC crew"),
    ("A4080", "External paving", 2, "task", 15, 15, [("M3000", "FS", 20)], "Paving crew"),
    ("HND", "Handover", 1, "summary", 0, 0, [], ""),
    ("A5000", "Testing and commissioning", 2, "task", 12, 12, [("A4060", "FS", 0), ("A4070", "FS", 0), ("A4040", "FS", 0)], "Commissioning team"),
    ("A5010", "Snagging and cleaning", 2, "task", 10, 10, [("A5000", "FS", 0), ("A4080", "FS", 0)], "Site team"),
    ("M5000", "Practical completion", 2, "milestone", 0, 0, [("A5010", "FS", 0)], ""),
]


def _network(durations_index, project_start):
    """Run the CPM engine over the leaf rows with the chosen duration column (4 = baseline, 5 = current)."""
    activities = [{"id": key, "duration": row[durations_index], "links": row[6]} for row in ROWS for key in [row[0]] if row[3] != "summary"]
    return cpm.schedule(activities, project_start)


def _progress(start: date, finish: date, today: date) -> float:
    if today < start:
        return 0.0
    if today >= finish:
        return 100.0
    return round((today - start).days + 1, 0) / max((finish - start).days + 1, 1) * 100


def _lag_text(lag):
    return "" if not lag else f"{lag:+d} days"


def seed(project, today=None) -> int:
    """Create the demo schedule for `project`. Returns the number of rows."""
    today = today or date.today()
    project_start = project.start_date
    baseline = _network(4, project_start)["activities"]
    current = _network(5, project_start)["activities"]

    ids = {row[0]: index for index, row in enumerate(ROWS, start=1)}
    rows = {}
    for key, name, level, kind, _b, _d, links, resources in ROWS:
        rows[key] = {"key": key, "name": name, "level": level, "kind": kind, "links": links, "resources": resources}

    # summaries take their dates / progress from the rows nested under them
    for position, row in enumerate(ROWS):
        if row[3] != "summary":
            continue
        nested = []
        for later in ROWS[position + 1:]:
            if later[2] <= row[2]:
                break
            if later[3] != "summary":
                nested.append(later[0])
        rows[row[0]]["nested"] = nested

    def dates(source, key):
        if rows[key]["kind"] != "summary":
            return source[key]["start"], source[key]["finish"]
        spans = [(source[k]["start"], source[k]["finish"]) for k in rows[key]["nested"]]
        return min(s for s, _ in spans), max(f for _, f in spans)

    created = 0
    with transaction.atomic():
        ScheduleTask.objects.filter(project=project, source_file_name=SOURCE).delete()
        for key, name, level, kind, _b, duration, links, resources in ROWS:
            start, finish = dates(current, key)
            base_start, base_finish = dates(baseline, key)
            if kind == "summary":
                nested = rows[key]["nested"]
                weights = [(max((current[k]["finish"] - current[k]["start"]).days + 1, 1), current[k]) for k in nested if next(r for r in ROWS if r[0] == k)[3] != "milestone"]
                percent = sum(w * _progress(c["start"], c["finish"], today) for w, c in weights) / sum(w for w, _ in weights)
                critical, slack = False, None
            else:
                percent = 100.0 if kind == "milestone" and finish <= today else (0.0 if kind == "milestone" else _progress(start, finish, today))
                critical, slack = current[key]["critical"], current[key]["float"]
            percent = round(percent, 1)
            ScheduleTask.objects.create(
                project=project, source_task_id=ids[key], unique_id=ids[key], name=name, outline_level=level,
                is_summary=kind == "summary", is_milestone=kind == "milestone", start_date=start, finish_date=finish,
                duration_days=None if kind == "summary" else Decimal(duration), duration_text="" if kind == "summary" else f"{duration} days",
                percent_complete=Decimal(str(percent)), total_slack_days=None if slack is None else Decimal(slack), is_critical=critical,
                predecessors=",".join(f"{ids[p]}{t}{_lag_text(lag)}" if t != "FS" or lag else str(ids[p]) for p, t, lag in links),
                resource_names=resources, source_file_name=SOURCE, activity_id=key if kind != "summary" else f"S{ids[key]:03d}",
                baseline_start=base_start, baseline_finish=base_finish,
                actual_start=start if kind != "summary" and start <= today and percent > 0 else None,
                actual_finish=finish if kind != "summary" and percent >= 100 else None,
            )
            created += 1
    return created


def clear(project) -> int:
    deleted, _ = ScheduleTask.objects.filter(project=project, source_file_name=SOURCE).delete()
    return deleted
