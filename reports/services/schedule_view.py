"""
Everything the project schedule (Gantt) page needs, as plain data: the imported / seeded schedule tasks with their WBS parents,
parsed predecessor links, baseline and actual dates, plus the project's key milestones and headline statistics.

The page only draws what is here: no scheduling happens in the browser. Dates and float are whatever the scheduling program (or
reports.services.cpm) computed and stored on ScheduleTask.
"""
import re
from datetime import date

from ..progress_models import ProjectMilestone
from ..schedule_models import ScheduleTask

LINK = re.compile(r"^(?P<id>.+?)(?P<type>FS|SS|FF|SF)?(?P<lag>[+-]\s*\d+(?:[.,]\d+)?\s*[a-zA-Z%]*)?$", re.IGNORECASE)
LAG = re.compile(r"^(?P<sign>[+-])\s*(?P<n>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z%]*)$")
UNIT_DAYS = {"": 1, "d": 1, "day": 1, "days": 1, "ed": 1, "edays": 1, "w": 7, "wk": 7, "wks": 7, "week": 7, "weeks": 7}


def _iso(value):
    return value.isoformat() if value else None


def parse_lag(text) -> float:
    """"+14 days" -> 14, "-2d" -> -2, "+1 wk" -> 7. Anything else (hours, percent) -> 0: it isn't drawn anyway."""
    match = LAG.match((text or "").strip())
    if not match:
        return 0
    days = UNIT_DAYS.get(match.group("unit").lower())
    if days is None:
        return 0
    value = float(match.group("n").replace(",", ".")) * days
    return -value if match.group("sign") == "-" else value


def parse_predecessors(text, by_uid, by_activity):
    """
    "5,7FS+3 days,A1010SS" -> [{"from": task pk, "type": "FS", "lag": 3.0}, ...]. A token names a task by its scheduling-program ID
    or by its activity ID; tokens that name nothing in this schedule are ignored.
    """
    links = []
    for token in re.split(r"[;,]", text or ""):
        token = token.strip()
        if not token:
            continue
        match = LINK.match(token)
        if not match:
            continue
        name = match.group("id").strip()
        target = by_activity.get(name.upper()) or (by_uid.get(int(name)) if name.isdigit() else None)
        if target is None:
            continue
        links.append({"from": target, "type": (match.group("type") or "FS").upper(), "lag": parse_lag(match.group("lag"))})
    return links


def _duration_label(task) -> str:
    if task.is_milestone:
        return "0d"
    if task.duration_text:
        return task.duration_text.replace(" days", "d").replace(" day", "d")
    if task.duration_days is not None:
        return f"{task.duration_days:g}d"
    if task.start_date and task.finish_date:
        return f"{(task.finish_date - task.start_date).days + 1}d"
    return ""


def build_schedule(project, today=None) -> dict:
    today = today or date.today()
    tasks = list(ScheduleTask.objects.filter(project=project).order_by("source_task_id"))
    rows = []

    # ---- WBS parents from the outline levels
    stack = []          # [(level, index)]
    for index, task in enumerate(tasks):
        while stack and stack[-1][0] >= task.outline_level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        stack.append((task.outline_level, index))
        rows.append({"task": task, "parent": parent, "children": []})
    for index, row in enumerate(rows):
        if row["parent"] is not None:
            rows[row["parent"]]["children"].append(index)

    def span(index):
        """Start / finish of a row, rolled up from its children when its own dates are missing."""
        row = rows[index]
        start, finish = row["task"].start_date, row["task"].finish_date
        if (start is None or finish is None) and row["children"]:
            child_spans = [span(c) for c in row["children"]]
            starts = [s for s, _ in child_spans if s]
            finishes = [f for _, f in child_spans if f]
            start = start or (min(starts) if starts else None)
            finish = finish or (max(finishes) if finishes else None)
        return start, finish

    by_uid = {t.source_task_id: t.pk for t in tasks}
    by_activity = {t.activity_id.upper(): t.pk for t in tasks if t.activity_id}

    output = []
    for index, row in enumerate(rows):
        task = row["task"]
        start, finish = span(index)
        summary = task.is_summary or bool(row["children"])
        output.append({
            "id": task.pk, "uid": task.source_task_id, "activity_id": task.activity_id or str(task.source_task_id),
            "name": task.name, "level": task.outline_level, "summary": summary, "milestone": task.is_milestone,
            "parent": tasks[row["parent"]].pk if row["parent"] is not None else None, "synthetic": False,
            "start": _iso(start), "finish": _iso(finish),
            "baseline_start": _iso(task.baseline_start), "baseline_finish": _iso(task.baseline_finish),
            "actual_start": _iso(task.actual_start), "actual_finish": _iso(task.actual_finish),
            "duration": _duration_label(task), "percent": float(task.percent_complete or 0),
            "float": None if task.total_slack_days is None else float(task.total_slack_days),
            "critical": bool(task.is_critical), "predecessors": task.predecessors,
            "links": parse_predecessors(task.predecessors, by_uid, by_activity), "resources": task.resource_names,
        })

    # ---- the project's key milestones, as one more group at the bottom
    milestones = list(ProjectMilestone.objects.filter(phase__project=project).select_related("phase").order_by("baseline_date", "order"))
    if milestones:
        group_id = "milestones"
        dates = [d for m in milestones for d in (m.baseline_date, m.forecast_date, m.actual_date) if d]
        output.append({
            "id": group_id, "uid": None, "activity_id": "MS", "name": "Key milestones", "level": 1, "summary": True, "milestone": False,
            "parent": None, "synthetic": True, "start": _iso(min(dates)), "finish": _iso(max(dates)), "baseline_start": None,
            "baseline_finish": None, "actual_start": None, "actual_finish": None, "duration": "", "percent": 0.0, "float": None,
            "critical": False, "predecessors": "", "links": [], "resources": "",
        })
        for m in milestones:
            current = m.actual_date or m.forecast_date or m.baseline_date
            output.append({
                "id": f"m{m.pk}", "uid": None, "activity_id": f"M{m.pk}", "name": m.name_en or m.name_ar, "level": 2, "summary": False,
                "milestone": True, "parent": group_id, "synthetic": True, "start": _iso(current), "finish": _iso(current),
                "baseline_start": _iso(m.baseline_date), "baseline_finish": _iso(m.baseline_date), "actual_start": None,
                "actual_finish": _iso(m.actual_date), "duration": "0d", "percent": 100.0 if m.actual_date else 0.0, "float": None,
                "critical": False, "predecessors": "", "links": [], "resources": "", "phase": m.phase.name_en or m.phase.name_ar,
            })

    return {"tasks": output, "stats": _stats(output, today), "data_date": today.isoformat()}


def _stats(rows, today) -> dict:
    leaves = [r for r in rows if not r["summary"] and not r["synthetic"] and r["start"] and r["finish"]]
    starts = [r["start"] for r in rows if r["start"]]
    finishes = [r["finish"] for r in rows if r["finish"]]
    baseline_finishes = [r["baseline_finish"] for r in rows if r["baseline_finish"] and not r["synthetic"]]
    weight_total = weight_done = 0.0
    for r in leaves:
        if r["milestone"]:
            continue
        weight = max((date.fromisoformat(r["finish"]) - date.fromisoformat(r["start"])).days + 1, 1)
        weight_total += weight
        weight_done += weight * r["percent"] / 100.0
    finish = max(finishes) if finishes else None
    baseline_finish = max(baseline_finishes) if baseline_finishes else None
    variance = (date.fromisoformat(finish) - date.fromisoformat(baseline_finish)).days if finish and baseline_finish else None
    return {
        "activities": len(leaves), "completed": sum(1 for r in leaves if r["percent"] >= 100),
        "in_progress": sum(1 for r in leaves if 0 < r["percent"] < 100), "critical": sum(1 for r in leaves if r["critical"]),
        "start": min(starts) if starts else None, "finish": finish, "baseline_finish": baseline_finish, "finish_variance_days": variance,
        "percent_complete": round(weight_done / weight_total * 100, 1) if weight_total else 0.0,
        "remaining_days": (date.fromisoformat(finish) - today).days if finish else None,
    }
