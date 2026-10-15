"""
Read a zip made by export_monthly_reports and create its reports here as DRAFTS -- but only when you add --apply. Without it nothing is written: it prints what
would happen (project found? period already there? which rows and files) so it can be checked first.

    python manage.py import_monthly_reports monthly_TAB.zip            # preview only
    python manage.py import_monthly_reports monthly_TAB.zip --apply    # create the drafts

A report whose project and period already exist here is never touched or duplicated. The author of the new drafts is the project's manager (or --author USERNAME).
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Preview (default) or create (--apply) the monthly reports of a zip made by export_monthly_reports.'

    def add_arguments(self, parser):
        parser.add_argument('package', help='the zip file')
        parser.add_argument('--apply', action='store_true', help='really create the drafts (without it: preview only)')
        parser.add_argument('--author', default='', help='username that becomes the author of the drafts (default: the project manager)')

    def handle(self, *args, **options):
        from reports.services import monthly_package as mp

        try:
            with open(options['package'], 'rb') as handle:
                payload, files = mp.read_package(handle.read())
        except (OSError, ValueError, KeyError) as error:
            raise CommandError(f'Cannot read the package: {error}')
        results = mp.plan(payload, options['author'])
        for result in results:
            item = result['item']
            self.stdout.write(f'\n{item["source_number"]}  {item["project_symbol"]}  {item["fields"]["reporting_period_from"]} - {item["fields"]["reporting_period_to"]}')
            counts = ', '.join(f'{name}: {len(rows)}' for name, rows in item['tables'].items() if rows) or 'no table rows'
            self.stdout.write(f'  rows: {counts}')
            self.stdout.write(f'  attachments: {len([a for a in item["attachments"] if a.get("archive_name")])} file(s)')
            if result['author']:
                self.stdout.write(f'  author of the draft: {result["author"].username}')
            for text in result['warnings']:
                self.stdout.write(self.style.WARNING(f'  ! {text}'))
            for text in result['problems']:
                self.stdout.write(self.style.ERROR(f'  X {text}'))
            self.stdout.write(self.style.SUCCESS('  will be created as a draft') if result['ok'] else '  will be SKIPPED')
        todo = [r for r in results if r['ok']]
        if not options['apply']:
            self.stdout.write(self.style.NOTICE(f'\nPreview only: nothing was written. {len(todo)} of {len(results)} report(s) would be created. Add --apply to create them.'))
            return
        created = mp.apply(results, files)
        for source, report in created:
            self.stdout.write(self.style.SUCCESS(f'Created {report.report_number} (from {source}) as a draft: /reports/monthly/{report.pk}/'))
        self.stdout.write(f'{len(created)} report(s) created, {len(results) - len(created)} skipped.')
