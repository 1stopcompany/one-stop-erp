"""
Management Command: Check for Overdue Daily Reports

For every project that's actually able to have Daily Reports filed on it (past Planning, insurance
in order, BOQ priced -- see projects.readiness) and has a site engineer assigned, this looks at
that project's own most recent Daily Report date. If it's been at least --days (default 2)
calendar days since that date (or no Daily Report has ever been filed at all), the assigned site
engineer gets an "overdue" reminder email (reports.email_service.EmailService.send_overdue_report_reminder).

This does NOT run itself on a schedule -- Celery is not wired up with a broker in this project (see
CLAUDE.md), so it needs an OS-level scheduler (Windows Task Scheduler / cron) calling
`python manage.py check_overdue_daily_reports` once a day, or a manual run.

Usage:
    python manage.py check_overdue_daily_reports              # send real reminders
    python manage.py check_overdue_daily_reports --dry-run     # show who would be notified, send nothing
    python manage.py check_overdue_daily_reports --days 3      # use a different threshold
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects import readiness
from reports.models import DailyReport
from reports.email_models import ReminderTemplate
from reports.email_service import EmailService

OVERDUE_TEMPLATE_SUBJECT = 'Overdue: {report_type} needed for {project_name}'
OVERDUE_TEMPLATE_BODY = """
<p>Hello {{ engineer_name }},</p>
<p>No Daily Report has been filed for <strong>{{ project_name }}</strong> in the last {{ days_overdue }} day(s)
(last one on {{ last_report_date }}).</p>
<p>Please file today's report as soon as you can:</p>
<p><a href="{{ create_report_url }}">Create Daily Report</a></p>
<p>— {{ company_name }}</p>
"""


def _ensure_overdue_template():
    """The overdue email is only sent when an active ReminderTemplate(template_type='overdue') exists
    (EmailService.send_overdue_report_reminder silently no-ops otherwise) -- create a plain default
    one if nobody has set one up yet in Admin, so this command works out of the box."""
    template, created = ReminderTemplate.objects.get_or_create(
        template_type='overdue',
        is_active=True,
        defaults={
            'name': 'Overdue Daily Report (default)',
            'subject': OVERDUE_TEMPLATE_SUBJECT,
            'body_html': OVERDUE_TEMPLATE_BODY,
        },
    )
    return template, created


class Command(BaseCommand):
    help = 'Email each project\'s site engineer when its Daily Report has not been filed in N days'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=2, help='Days without a Daily Report before nagging (default: 2)')
        parser.add_argument('--dry-run', action='store_true', help='Show who would be notified without sending anything')

    def handle(self, *args, **options):
        days_threshold = options['days']
        dry_run = options['dry_run']
        today = timezone.localdate()

        template, created = _ensure_overdue_template()
        if created:
            self.stdout.write(self.style.WARNING(
                f'No active "overdue" email template existed -- created a default one (id={template.id}). '
                f'Edit it in Admin (Reminder Templates) to customize the wording.'
            ))

        projects = readiness.ready_projects().filter(site_engineer__isnull=False).select_related('site_engineer')
        notified = 0
        checked = 0

        for project in projects:
            checked += 1
            last_report_date = DailyReport.objects.filter(project=project).order_by('-report_date').values_list(
                'report_date', flat=True
            ).first()

            if last_report_date is None:
                days_overdue = None  # never filed one -- always overdue, no specific gap to report
                is_overdue = True
            else:
                days_overdue = (today - last_report_date).days
                is_overdue = days_overdue >= days_threshold

            if not is_overdue:
                continue

            engineer = project.site_engineer
            label = (
                f'{project.name} ({project.project_symbol}) -> {engineer.get_full_name() or engineer.username} '
                f'<{engineer.email}> -- '
                + (f'{days_overdue} day(s) since last report ({last_report_date})' if last_report_date else 'no report ever filed')
            )

            if dry_run:
                self.stdout.write(f'Would notify: {label}')
                notified += 1
                continue

            success = EmailService.send_overdue_report_reminder(
                engineer, report_type='daily',
                extra_context={
                    'project_name': project.name,
                    'days_overdue': str(days_overdue) if last_report_date else 'N/A',
                    'last_report_date': last_report_date.isoformat() if last_report_date else 'never',
                },
            )
            if success:
                self.stdout.write(self.style.SUCCESS(f'Notified: {label}'))
                notified += 1
            else:
                self.stdout.write(self.style.ERROR(f'Failed to notify: {label}'))

        verb = 'Would notify' if dry_run else 'Notified'
        self.stdout.write(self.style.SUCCESS(
            f'Checked {checked} ready project(s) with a site engineer. {verb} {notified}.'
        ))
