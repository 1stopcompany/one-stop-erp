"""
Run the "report submitted" delivery (e-mail + PDF copy in Dropbox + photos) for one daily report RIGHT NOW, in the terminal, and print what each part did and how
long it took -- the way to find out why a report's delivery stays on "Sending..." or fails on the server, with the real error on screen.

    python manage.py deliver_report <report id>            # the real thing: sends the e-mail and uploads to Dropbox, like the "Send again" button
    python manage.py deliver_report <report id> --pdf-only # only builds the PDF and tells the size and the time (no e-mail, no Dropbox)
"""
import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Deliver one submitted daily report (e-mail + Dropbox) in the foreground and print the result of every part.'

    def add_arguments(self, parser):
        parser.add_argument('report_id', type=int)
        parser.add_argument('--pdf-only', action='store_true', help='only build the PDF (to see whether that is what hangs)')

    def handle(self, *args, **options):
        from django.conf import settings
        from reports.models import DailyReport
        from reports.services import report_delivery as rd
        from reports.utils import generate_daily_report_pdf

        try:
            report = DailyReport.all_objects.select_related('project', 'site_engineer').get(pk=options['report_id'])
        except DailyReport.DoesNotExist:
            raise CommandError('No daily report with that id.')
        self.stdout.write(f'Report {report.report_number} ({report.project.project_symbol}, {report.report_date}), status {report.status}')
        self.stdout.write(f'E-mail backend: {settings.EMAIL_BACKEND.split(".")[-2]}  host: {settings.EMAIL_HOST or "-"}  port: {settings.EMAIL_PORT}  timeout: {settings.EMAIL_TIMEOUT}')
        self.stdout.write(f'Recipients: {", ".join(rd.recipients(report)) or "(none)"}')
        self.stdout.write(f'Dropbox folder: {report.project.report_dropbox_folder or "-"}   photos folder: {report.project.photos_dropbox_folder or "(inside the reports folder)"}')

        started = time.time()
        pdf = generate_daily_report_pdf(report)
        self.stdout.write(self.style.SUCCESS(f'PDF built in {time.time() - started:.1f} s, {len(pdf) / 1024:.0f} KB'))
        if options['pdf_only']:
            return

        started = time.time()
        delivery = rd.deliver(report.pk)
        self.stdout.write(f'Delivery finished in {time.time() - started:.1f} s (finished={delivery.finished})')
        self.stdout.write(f'  e-mail:   {"sent" if delivery.email_ok else "NOT sent"}  {delivery.email_to}  {delivery.email_error}')
        if delivery.dropbox_ok is None:
            self.stdout.write('  dropbox:  no folder set on the project')
        else:
            self.stdout.write(f'  dropbox:  {"saved to " + delivery.dropbox_path if delivery.dropbox_ok else "FAILED: " + delivery.dropbox_error}')
        if delivery.photos_total is not None:
            self.stdout.write(f'  photos:   {delivery.photos_copied} of {delivery.photos_total} copied  {delivery.photos_error}')
