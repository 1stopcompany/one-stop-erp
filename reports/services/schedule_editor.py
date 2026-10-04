"""
Typing a project's schedule in by hand (the "Edit schedule" page) instead of importing it from MS Project.

The editor shows the stored ScheduleTask rows as one table: name, indent level, start, finish, % complete, predecessors,
milestone / critical flags. Saving writes the whole table back; the Gantt page then draws it exactly as it draws an imported
schedule (reports.services.schedule_view.build_schedule), so nothing else needs to know where the rows came from.

Rules applied on save:
  * Row numbers are positions in the table (1, 2, 3 ...) and become each task's source_task_id, so reordering or inserting rows
    simply renumbers them. Predecessors are written with these numbers ("3", "3FS+2 days", "2,4SS"); a predecessor already stored
    against an old numbering is translated when the editor opens, so imported schedules keep their links.
  * A row followed by a deeper-indented row is a summary: its dates and % complete are rolled up from the rows beneath it
    (percent weighted by working days), whatever was typed.
  * Working days are Saturday-Thursday, like reports.services.cpm and the company's payroll week.
  * Fields the editor has no column for (baseline / actual dates, activity ID, float, resources) are kept on rows that already exist.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from ..schedule_models import ScheduleTask
from .schedule_view import LINK

MAX_LEVEL = 5
RENUMBER_OFFSET = 1_000_000


def working_days(start, finish):
    """Saturday-Thursday working days from start to finish, both included (a Friday-only span is 0)."""
    if not start or not finish or finish < start:
        return 0
    days, d = 0, start
    while d <= finish:
        days += d.weekday() != 4
        d += timedelta(days=1)
    return days


def _iso(value):
    return value.isoformat() if value else ""


def _translate_predecessors(text, old_to_position):
    """Rewrite the numeric task IDs in a predecessor list with the table positions; other tokens (activity IDs) are left alone."""
    out = []
    for token in re.split(r"[;,]", text or ""):
        token = token.strip()
        if not token:
            continue
        match = LINK.match(token)
        name = match.group("id").strip() if match else ""
        if match and name.isdigit() and int(name) in old_to_position:
            token = str(old_to_position[int(name)]) + token[len(match.group("id")):]
        out.append(token)
    return ",".join(out)


def editor_rows(project):
    """The project's stored tasks as plain dicts for the editor, in table order."""
    tasks = list(ScheduleTask.objects.filter(project=project).order_by("source_task_id"))
    old_to_position = {t.source_task_id: i for i, t in enumerate(tasks, start=1)}
    return [{
        "pk": t.pk, "name": t.name, "level": t.outline_level, "start": _iso(t.start_date), "finish": _iso(t.finish_date),
        "percent": float(t.percent_complete or 0), "pred": _translate_predecessors(t.predecessors, old_to_position),
        "milestone": t.is_milestone, "critical": t.is_critical,
    } for t in tasks]


def rows_from_post(post):
    """The table as the browser sent it (row order = order of the `idx` fields), without validating anything."""
    rows = []
    for idx in post.getlist("idx"):
        rows.append({
            "pk": post.get(f"pk_{idx}") or "", "name": (post.get(f"name_{idx}") or "").strip(),
            "level": post.get(f"level_{idx}") or "1", "start": post.get(f"start_{idx}") or "",
            "finish": post.get(f"finish_{idx}") or "", "percent": post.get(f"pct_{idx}") or "0",
            "pred": (post.get(f"pred_{idx}") or "").strip(), "milestone": bool(post.get(f"ms_{idx}")),
            "critical": bool(post.get(f"crit_{idx}")),
        })
    return rows


def _parse_date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def clean_rows(rows, project):
    """Validate and normalise. Returns (cleaned rows, [error strings]); cleaned rows carry real dates / numbers and `summary`."""
    errors, cleaned = [], []
    known_activities = {
        a.upper() for a in ScheduleTask.objects.filter(project=project).exclude(activity_id="").values_list("activity_id", flat=True)
    }
    previous_level = 0
    for position, row in enumerate(rows, start=1):
        label = f"Row {position}"
        name = row["name"]
        if not name:
            errors.append(f"{label}: the name is empty.")
        try:
            level = int(row["level"])
        except (TypeError, ValueError):
            level = 1
        level = min(max(level, 1), MAX_LEVEL)
        if position == 1 and level != 1:
            errors.append(f"{label}: the first row must be at level 1.")
        elif level > previous_level + 1:
            errors.append(f"{label}: it is indented more than one level below the row above.")
        previous_level = level

        start, finish = _parse_date(row["start"]), _parse_date(row["finish"])
        try:
            percent = Decimal(str(row["percent"] or 0))
        except Exception:
            percent = Decimal("0")
            errors.append(f"{label}: % complete is not a number.")
        if not Decimal("0") <= percent <= Decimal("100"):
            errors.append(f"{label}: % complete must be between 0 and 100.")
            percent = min(max(percent, Decimal("0")), Decimal("100"))
        cleaned.append({
            "position": position, "pk": int(row["pk"]) if str(row["pk"]).isdigit() else None, "name": name, "level": level,
            "start": start, "finish": finish, "percent": percent, "pred": row["pred"], "milestone": row["milestone"],
            "critical": row["critical"], "raw_start": row["start"], "raw_finish": row["finish"],
        })

    total = len(cleaned)
    for i, row in enumerate(cleaned):
        row["summary"] = i + 1 < total and cleaned[i + 1]["level"] > row["level"]

    for row in cleaned:
        label = f"Row {row['position']}"
        if row["summary"]:
            continue  # its dates / percent are rolled up below
        if not row["start"]:
            errors.append(f"{label} ({row['name'] or '?'}): the start date is missing or not a date.")
            continue
        if row["milestone"]:
            row["finish"] = row["start"]
        elif not row["finish"]:
            errors.append(f"{label} ({row['name'] or '?'}): the finish date is missing or not a date.")
        elif row["finish"] < row["start"]:
            errors.append(f"{label} ({row['name'] or '?'}): it finishes before it starts.")

        cleaned_pred, bad = [], []
        for token in re.split(r"[;,]", row["pred"] or ""):
            token = token.strip()
            if not token:
                continue
            match = LINK.match(token)
            name_part = match.group("id").strip() if match else ""
            if match and name_part.isdigit() and 1 <= int(name_part) <= total and int(name_part) != row["position"]:
                cleaned_pred.append(token)
            elif match and name_part.upper() in known_activities:
                cleaned_pred.append(token)
            else:
                bad.append(token)
        row["pred"] = ",".join(cleaned_pred)
        if bad:
            errors.append(f"{label} ({row['name'] or '?'}): predecessor '{', '.join(bad)}' is not a row number of this table (1-{total}) or is the row itself.")

    # summaries: dates and percent from the leaves beneath, bottom-up
    for i in range(total - 1, -1, -1):
        row = cleaned[i]
        if not row["summary"]:
            continue
        leaves = []
        for later in cleaned[i + 1:]:
            if later["level"] <= row["level"]:
                break
            if not later["summary"]:
                leaves.append(later)
        starts = [r["start"] for r in leaves if r["start"]]
        finishes = [r["finish"] for r in leaves if r["finish"]]
        row["start"], row["finish"] = (min(starts) if starts else None), (max(finishes) if finishes else None)
        weighted = [(max(working_days(r["start"], r["finish"]), 1), r["percent"]) for r in leaves if r["start"] and r["finish"] and not r["milestone"]]
        weight = sum(w for w, _ in weighted)
        row["percent"] = (sum(w * p for w, p in weighted) / weight).quantize(Decimal("0.1")) if weight else Decimal("0")
        row["milestone"] = False
        row["pred"] = ""
    return cleaned, errors


@transaction.atomic
def save_rows(project, cleaned):
    """Write the cleaned table: update rows that exist, create new ones, delete the ones removed, number everything by position."""
    existing = {t.pk: t for t in ScheduleTask.objects.filter(project=project)}
    # move every stored number out of the way first, so renumbering never trips the (project, source_task_id) unique constraint
    ScheduleTask.objects.filter(project=project).update(source_task_id=F("source_task_id") + RENUMBER_OFFSET)
    return _write(project, cleaned, existing)


def _write(project, cleaned, existing):
    keep, next_unique = set(), max([t.unique_id for t in existing.values()] + [0]) + 1
    for row in cleaned:
        task = existing.get(row["pk"])
        if task is None:
            task = ScheduleTask(project=project, unique_id=next_unique)
            next_unique += 1
        duration = 0 if row["milestone"] else working_days(row["start"], row["finish"])
        task.source_task_id = row["position"]
        task.name = row["name"]
        task.outline_level = row["level"]
        task.is_summary = row["summary"]
        task.is_milestone = row["milestone"]
        task.start_date, task.finish_date = row["start"], row["finish"]
        task.duration_days = Decimal(duration)
        task.duration_text = f"{duration} days"
        task.percent_complete = row["percent"]
        task.is_critical = row["critical"] and not row["summary"]
        task.predecessors = row["pred"][:255]
        if not task.source_file_name:
            task.source_file_name = "Edited in the ERP"
        task.save()
        keep.add(task.pk)
    ScheduleTask.objects.filter(project=project).exclude(pk__in=keep).delete()
    return len(keep)
