"""
Auto-created reports for the days the site is idle by the calendar: every Friday (the weekly rest day) and every public holiday
(timesheets.Holiday) gets an "idle day" daily report as a DRAFT for the project's site engineer, so the day is counted as a project
day without anyone typing it. The engineer reviews it, adds the weather if he likes, and submits it like any other report.

A day is skipped when the project already has a report for it (any status, including a draft waiting for deletion approval).
By default only the last 14 days are looked at, so a report an engineer deleted on purpose does not come back months later.
"""
from datetime import date, timedelta

from reports.models import DailyReport

FRIDAY = 4


def missing_idle_days(project, start, end):
    """[(date, reason)] of the Fridays / holidays in [start, end] that have no daily report yet for the project."""
    from timesheets.models import Holiday
    holidays = {h.date: h.name for h in Holiday.objects.filter(date__gte=start, date__lte=end)}
    existing = set(DailyReport.all_objects.filter(project=project, report_date__gte=start, report_date__lte=end)
                   .exclude(status='rejected').values_list('report_date', flat=True))
    days, day = [], start
    while day <= end:
        if day not in existing and (day in holidays or day.weekday() == FRIDAY):
            days.append((day, 'public_holiday' if day in holidays else 'weekly_rest', holidays.get(day, '')))
        day += timedelta(days=1)
    return days


def create_idle_reports(project, start=None, end=None, days=14, dry_run=False):
    """Creates the missing Friday / holiday idle-day drafts. Returns the list of (date, reason) created (or that would be)."""
    end = end or date.today()
    start = start or (end - timedelta(days=days - 1))
    if not project.site_engineer_id:
        return []
    todo = missing_idle_days(project, start, end)
    if dry_run:
        return [(d, r) for d, r, _ in todo]
    created = []
    for day, reason, holiday_name in todo:
        DailyReport.objects.create(
            project=project, site_engineer=project.site_engineer, report_date=day, status='draft', weather_conditions='',
            site_status='idle', idle_reason=reason,
            remarks=('Created automatically: ' + (f'public holiday - {holiday_name}' if reason == 'public_holiday' else 'weekly rest day (Friday)')),
        )
        created.append((day, reason))
    return created
