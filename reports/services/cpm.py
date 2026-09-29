"""
A small critical-path (CPM) engine: forward and backward pass over activities with Finish-to-Start, Start-to-Start,
Finish-to-Finish and Start-to-Finish links (with lag), on the company's work calendar.

Why it exists: the schedule pages show what a scheduling program computed (see reports.schedule_models). This engine is for the
cases where the app has to produce a schedule itself with consistent dates and float -- the demo schedule today, and any later
in-app editing -- and it is a pure function so it can be tested against hand-worked examples.

Conventions:
  * Work week Saturday to Thursday, Friday off (the company's payroll calendar); extra non-working dates can be passed in.
  * Durations and lags are in WORK days. Internally an activity occupies work-day slots [start, finish) (finish exclusive).
  * An activity starting on day S with duration D finishes (inclusively) on the D-th work day counting S as the first.
  * A milestone has duration 0 and sits on the first work day after what it waits for.
"""
from collections import defaultdict, deque
from datetime import date, timedelta

WORK_WEEKDAYS = frozenset({5, 6, 0, 1, 2, 3})     # Saturday, Sunday, Monday..Thursday; Python: Monday is 0, Friday is 4
LINK_TYPES = ("FS", "SS", "FF", "SF")


class ScheduleError(ValueError):
    """The network can't be scheduled (a loop, a link to nothing, a bad duration)."""


def is_workday(day: date, holidays=()) -> bool:
    return day.weekday() in WORK_WEEKDAYS and day not in holidays


def next_workday(day: date, holidays=()) -> date:
    """`day` itself if it is a work day, else the next one."""
    while not is_workday(day, holidays):
        day += timedelta(days=1)
    return day


class Calendar:
    """Work days counted from a start date: slot 0 is the first work day on or after `start`."""

    def __init__(self, start: date, holidays=()):
        self.holidays = frozenset(holidays)
        self.days = [next_workday(start, self.holidays)]

    def date_of(self, slot: int) -> date:
        while len(self.days) <= slot:
            self.days.append(next_workday(self.days[-1] + timedelta(days=1), self.holidays))
        return self.days[slot]

    def slot_of(self, day: date) -> int:
        """The slot of the first work day on or after `day` (0 for anything before the start)."""
        day = next_workday(day, self.holidays)
        if day <= self.days[0]:
            return 0
        slot = 0
        while self.date_of(slot) < day:
            slot += 1
        return slot


def schedule(activities, project_start: date, holidays=()):
    """
    activities: list of {"id", "duration" (work days, 0 = milestone), "links": [(predecessor id, "FS"|"SS"|"FF"|"SF", lag work days)],
                         "not_before": optional date}
    Returns {"activities": {id: {start, finish, late_start, late_finish, float, critical}}, "start", "finish"}
    where float is in work days and dates are calendar dates (finish inclusive; milestones have start == finish).
    """
    by_id = {}
    for act in activities:
        if act["id"] in by_id:
            raise ScheduleError(f"Activity {act['id']} appears twice.")
        if act["duration"] < 0 or act["duration"] != int(act["duration"]):
            raise ScheduleError(f"Activity {act['id']} needs a whole number of work days (0 for a milestone).")
        by_id[act["id"]] = act

    successors = defaultdict(list)          # pred -> [(succ, type, lag)]
    indegree = {i: 0 for i in by_id}
    for act in by_id.values():
        for pred, kind, lag in act.get("links", []):
            if pred not in by_id:
                raise ScheduleError(f"Activity {act['id']} waits for {pred}, which isn't in the schedule.")
            if kind not in LINK_TYPES:
                raise ScheduleError(f"Unknown link type {kind}.")
            successors[pred].append((act["id"], kind, int(lag)))
            indegree[act["id"]] += 1

    order, queue = [], deque(i for i, n in indegree.items() if n == 0)
    while queue:
        node = queue.popleft()
        order.append(node)
        for succ, _, _ in successors[node]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                queue.append(succ)
    if len(order) != len(by_id):
        raise ScheduleError("The links form a loop, so the schedule can't be calculated.")

    calendar = Calendar(project_start, holidays)
    duration = {i: int(a["duration"]) for i, a in by_id.items()}
    start, finish = {}, {}

    # ---- forward pass (finish is exclusive: an activity fills slots start .. finish-1)
    for node in order:
        earliest = calendar.slot_of(by_id[node]["not_before"]) if by_id[node].get("not_before") else 0
        for pred, kind, lag in by_id[node].get("links", []):
            if kind == "FS":
                earliest = max(earliest, finish[pred] + lag)
            elif kind == "SS":
                earliest = max(earliest, start[pred] + lag)
            elif kind == "FF":
                earliest = max(earliest, finish[pred] + lag - duration[node])
            else:  # SF
                earliest = max(earliest, start[pred] + lag - duration[node])
        start[node] = max(earliest, 0)
        finish[node] = start[node] + duration[node]

    project_finish = max(finish.values()) if finish else 0

    # ---- backward pass
    late_start, late_finish = {}, {}
    for node in reversed(order):
        latest_finish = project_finish
        for succ, kind, lag in successors[node]:
            if kind == "FS":
                latest_finish = min(latest_finish, late_start[succ] - lag)
            elif kind == "SS":
                latest_finish = min(latest_finish, late_start[succ] - lag + duration[node])
            elif kind == "FF":
                latest_finish = min(latest_finish, late_finish[succ] - lag)
            else:  # SF
                latest_finish = min(latest_finish, late_finish[succ] - lag + duration[node])
        late_finish[node] = latest_finish
        late_start[node] = latest_finish - duration[node]

    result = {}
    for node in by_id:
        milestone = duration[node] == 0
        first = calendar.date_of(start[node])
        last = first if milestone else calendar.date_of(finish[node] - 1)
        late_first = calendar.date_of(max(late_start[node], 0))
        late_last = late_first if milestone else calendar.date_of(max(late_finish[node] - 1, 0))
        total_float = late_start[node] - start[node]
        result[node] = {"start": first, "finish": last, "late_start": late_first, "late_finish": late_last,
                        "float": total_float, "critical": total_float <= 0}
    end = calendar.date_of(project_finish - 1) if project_finish else calendar.date_of(0)
    return {"activities": result, "start": calendar.date_of(0), "finish": end}
