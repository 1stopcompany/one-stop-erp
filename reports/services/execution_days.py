"""
Execution days of a project, from its daily reports: how many days the site worked, how many it was idle (and why), and how many days
have no report at all. Every day counts as a day of the contract period (Fridays and holidays included), so an idle day needs its
report too; a day that has a working report and an idle one counts as working. Rejected reports are ignored.
"""
from collections import Counter
from datetime import date, timedelta

from reports.models import DailyReport


def execution_days(project, as_of=None):
    """
    {'start', 'as_of', 'calendar_days' (contract start -> as_of), 'since' (first report), 'days_since', 'working', 'idle',
     'idle_by_reason': [(label, n)], 'missing': [dates without a report since the first report], 'missing_count'}
    """
    as_of = as_of or date.today()
    reports = list(DailyReport.objects.filter(project=project, report_date__lte=as_of).exclude(status='rejected')
                   .only('report_date', 'site_status', 'idle_reason'))
    by_day = {}
    for report in reports:
        previous = by_day.get(report.report_date)
        if previous is None or (previous.site_status == 'idle' and report.site_status != 'idle'):
            by_day[report.report_date] = report            # a working report outranks an idle one on the same day
    working = sum(1 for r in by_day.values() if r.site_status != 'idle')
    idle_reports = [r for r in by_day.values() if r.site_status == 'idle']
    labels = dict(DailyReport.IDLE_REASON_CHOICES)
    idle_by_reason = Counter(labels.get(r.idle_reason, 'Other') for r in idle_reports)

    since = min(by_day) if by_day else None
    missing = []
    if since:
        day = since
        while day <= as_of:
            if day not in by_day:
                missing.append(day)
            day += timedelta(days=1)
    start = project.start_date
    return {
        'start': start, 'as_of': as_of,
        'calendar_days': ((as_of - start).days + 1) if start and start <= as_of else None,
        'since': since, 'days_since': ((as_of - since).days + 1) if since else 0,
        'working': working, 'idle': len(idle_reports), 'idle_by_reason': idle_by_reason.most_common(),
        'missing': missing, 'missing_count': len(missing), 'recorded': len(by_day),
    }
