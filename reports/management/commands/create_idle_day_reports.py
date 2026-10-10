"""
Create the idle-day draft reports for Fridays and public holidays that have none yet (see reports.services.idle_days).

    python manage.py create_idle_day_reports                       # last 14 days, every ready project that has a site engineer
    python manage.py create_idle_day_reports --project TAB --from 2026-09-15 --dry-run
    python manage.py create_idle_day_reports --days 30

Nothing runs it by itself: schedule it (Windows Task Scheduler / cron) once a day or once a week, or press the button on the Daily
Reports page.
"""
import datetime

from django.core.management.base import BaseCommand

from projects import readiness
from reports.services.idle_days import create_idle_reports


class Command(BaseCommand):
    help = "Create idle-day draft reports for the Fridays and public holidays that have no daily report."

    def add_arguments(self, parser):
        parser.add_argument('--project', help='Only this project symbol')
        parser.add_argument('--from', dest='start', help='First day (YYYY-MM-DD); default: today minus --days')
        parser.add_argument('--days', type=int, default=14, help='How many days back to look when --from is not given (default 14)')
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be created')

    def handle(self, *args, **options):
        projects = readiness.ready_projects().filter(site_engineer__isnull=False)
        if options['project']:
            projects = projects.filter(project_symbol=options['project'])
        start = datetime.date.fromisoformat(options['start']) if options['start'] else None
        total = 0
        for project in projects:
            made = create_idle_reports(project, start=start, days=options['days'], dry_run=options['dry_run'])
            total += len(made)
            if made:
                self.stdout.write(f"{project.project_symbol}: " + ', '.join(f"{d:%d/%m} ({reason})" for d, reason in made))
        self.stdout.write(self.style.SUCCESS(f"{total} idle-day report(s) " + ('would be created.' if options['dry_run'] else 'created.')))
