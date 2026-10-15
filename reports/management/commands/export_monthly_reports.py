"""
Write the monthly (EDGE) reports of one project into a single zip that import_monthly_reports can read on another installation (the company server).

    python manage.py export_monthly_reports --project TAB --months 2026-08,2026-09 --out monthly_TAB.zip
    python manage.py export_monthly_reports --ids 4,21 --out monthly_TAB.zip

Nothing is changed here; the zip carries each report's data and its attached files (see reports/services/monthly_package.py).
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Export monthly reports (data + attachments) into a zip for import_monthly_reports.'

    def add_arguments(self, parser):
        parser.add_argument('--project', help='project symbol, e.g. TAB')
        parser.add_argument('--months', help='comma separated YYYY-MM of the period end, e.g. 2026-08,2026-09')
        parser.add_argument('--ids', help='or the report ids, comma separated')
        parser.add_argument('--out', required=True, help='the zip file to write')

    def handle(self, *args, **options):
        from reports.models import MonthlyReport
        from reports.services.monthly_package import export_package

        if options['ids']:
            reports = list(MonthlyReport.objects.filter(pk__in=[int(i) for i in options['ids'].split(',') if i.strip()]).select_related('project').order_by('reporting_period_to'))
        elif options['project'] and options['months']:
            reports = []
            for month in options['months'].split(','):
                year, mon = (int(part) for part in month.strip().split('-'))
                found = list(MonthlyReport.objects.filter(project__project_symbol=options['project'], reporting_period_to__year=year, reporting_period_to__month=mon)
                             .select_related('project').order_by('-id'))
                if not found:
                    raise CommandError(f'No monthly report of {options["project"]} ends in {month}.')
                if len(found) > 1:
                    self.stdout.write(self.style.WARNING(f'{len(found)} reports end in {month}: taking the newest ({found[0].report_number}). Use --ids to choose another.'))
                reports.append(found[0])
        else:
            raise CommandError('Give --ids, or --project and --months.')
        if not reports:
            raise CommandError('Nothing to export.')
        data = export_package(reports)
        with open(options['out'], 'wb') as handle:
            handle.write(data)
        for report in reports:
            self.stdout.write(f'  {report.report_number}  {report.project.project_symbol}  {report.reporting_period_from} - {report.reporting_period_to}  ({report.status})')
        self.stdout.write(self.style.SUCCESS(f'Wrote {options["out"]} ({len(data) / 1024:.0f} KB, {len(reports)} report(s)).'))
