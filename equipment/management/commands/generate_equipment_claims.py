"""
Create the monthly rental claims of the rented heavy equipment when a payment cycle (26th .. 25th) is closed.

    python manage.py generate_equipment_claims                      # the last closed cycle (run it every day: it only acts once per cycle)
    python manage.py generate_equipment_claims --date 2026-10-25    # a given cycle (the 25th it ends on)
    python manage.py generate_equipment_claims --dry-run            # show what would be created

Schedule it once a day (cPanel cron, around 02:00): on the 26th it creates the claims and posts them to the accounting page; the rest of
the month it finds nothing new. Running it again is harmless.
"""
import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from equipment import claims


class Command(BaseCommand):
    help = 'Create the rental claims of the closed payment cycle (26th .. 25th) of the rented heavy equipment.'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='The 25th the cycle ends on (YYYY-MM-DD); default: the last closed cycle')
        parser.add_argument('--project', help='Only this project symbol')
        parser.add_argument('--dry-run', action='store_true', help='Show without creating')

    def handle(self, *args, **options):
        end = datetime.date.fromisoformat(options['date']) if options['date'] else None
        project = None
        if options['project']:
            from projects.models import Project
            project = Project.objects.filter(project_symbol=options['project']).first()
            if not project:
                raise CommandError(f"No project {options['project']}.")
        try:
            made = claims.generate_claims(end=end, project=project, dry_run=options['dry_run'])
        except ValidationError as error:
            raise CommandError('; '.join(error.messages))
        cycle = f'{(end or claims.last_closed_cycle_end()):%d/%m/%Y}'
        for claim in made:
            self.stdout.write(f'  {claim.tool.code} {claim.project.project_symbol}: {claim.days_worked} days, {claim.hours_worked} h -> {claim.amount}'
                              + ('' if claim.rate else '  (no rental rate set on the equipment!)'))
        self.stdout.write(self.style.SUCCESS(f'Cycle ending {cycle}: {len(made)} claim(s) ' + ('would be created.' if options['dry_run'] else 'created.')))
