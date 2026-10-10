"""
Copy ONE owner financial report (the technical & financial report for the owner) from one database to another -- e.g. from the local
PC to the server -- with its price table, phase descriptions and photos (the photo files are copied into the bundle folder).

    python manage.py owner_report_copy export OFR-TAB-20260908103526-E6F62282 reports/data/owner_report_TAB_2026-09
    python manage.py owner_report_copy import reports/data/owner_report_TAB_2026-09                # preview only
    python manage.py owner_report_copy import reports/data/owner_report_TAB_2026-09 --apply
    python manage.py owner_report_copy import reports/data/owner_report_TAB_2026-09 --apply --replace

The report is created as a DRAFT for the project's site engineer on this database. The project, its BOQ phases (matched by code) and
the progress entries must already be here: the report's money figures are computed from them. When a report with the same number
already exists the import is refused unless --replace is given (then only that report, with its table rows and photo records, is
replaced). The author is the project's site engineer, or --author USERNAME. No other report, project or BOQ record is touched.
"""
import datetime
import json
import os
import shutil
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.owner_financial_models import OwnerFinancialReport, OwnerReportPhaseUpdate, OwnerReportPriceComparisonItem
from reports.progress_models import ProjectPhase, ProjectPhasePhoto, ProjectPhaseSubItem

REPORT_FIELDS = ('report_number', 'report_date', 'reporting_period_from', 'reporting_period_to', 'contract_value_snapshot',
                 'advance_payment_value_snapshot', 'performance_retention_rate_snapshot', 'previous_payments_total', 'progress_summary',
                 'next_month_expected_works', 'next_month_expected_completion_pct', 'material_price_note', 'closing_note')
DATES = {'report_date', 'reporting_period_from', 'reporting_period_to'}
DECIMALS = {'contract_value_snapshot', 'advance_payment_value_snapshot', 'performance_retention_rate_snapshot', 'previous_payments_total',
            'next_month_expected_completion_pct'}


def _dump(value):
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _load(name, value):
    if value is None:
        return None
    if name in DATES:
        return datetime.date.fromisoformat(value)
    if name in DECIMALS:
        return Decimal(str(value))
    return value


class Command(BaseCommand):
    help = "Export / import one owner financial report (with its table rows and photos) between databases."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('target', help='export: the report number; import: the bundle folder')
        parser.add_argument('folder', nargs='?', help='export: the bundle folder to write')
        parser.add_argument('--apply', action='store_true', help='import: really write it (without it, only a preview)')
        parser.add_argument('--replace', action='store_true', help='import: replace the report of the same number if it exists here')
        parser.add_argument('--author', help="import: username of the report's author on this database (a site engineer or project manager); "
                                             "default: the project's site engineer")

    def handle(self, *args, **options):
        if options['action'] == 'export':
            return self.export(options['target'], options['folder'])
        return self.import_(options['target'], options['apply'], options['replace'], options['author'])

    # ------------------------------------------------------------------ export
    def export(self, number, folder):
        if not folder:
            raise CommandError('export needs the output folder: owner_report_copy export NUMBER folder')
        report = OwnerFinancialReport.all_objects.filter(report_number=number).select_related('project').first()
        if not report:
            raise CommandError(f'No owner report numbered {number}.')
        os.makedirs(os.path.join(folder, 'photos'), exist_ok=True)
        photos = []
        for index, photo in enumerate(ProjectPhasePhoto.objects.filter(owner_financial_report=report).select_related('phase', 'sub_item').order_by('phase__order', 'order', 'id')):
            filename = f'{index + 1:03d}_{os.path.basename(photo.photo.name)}'
            with photo.photo.open('rb') as source, open(os.path.join(folder, 'photos', filename), 'wb') as target:
                shutil.copyfileobj(source, target)
            photos.append({'phase': photo.phase.code, 'sub_item': (photo.sub_item.name_ar if photo.sub_item_id else ''), 'file': filename,
                           'stored_name': photo.photo.name, 'caption': photo.caption, 'taken_date': _dump(photo.taken_date), 'order': photo.order})
        data = {
            'version': 1, 'project': report.project.project_symbol,
            'report': {name: _dump(getattr(report, name)) for name in REPORT_FIELDS},
            'price_items': [{'item_type': i.item_type, 'item_name': i.item_name, 'unit': i.unit, 'quantity': str(i.quantity),
                             'old_unit_price': str(i.old_unit_price), 'new_unit_price': str(i.new_unit_price)}
                            for i in report.price_comparison_items.all().order_by('id')],
            'frozen_at': _dump(report.frozen_at.isoformat()) if report.frozen_at else None, 'frozen_progress': report.frozen_progress,
            'phase_updates': [{'phase': u.phase.code, 'status': u.status, 'work_performed': u.work_performed, 'order': u.order}
                              for u in report.phase_updates.select_related('phase').order_by('order', 'id')],
            'photos': photos,
        }
        with open(os.path.join(folder, 'report.json'), 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(f"{number}: {len(data['price_items'])} price rows, {len(data['phase_updates'])} phase descriptions, {len(photos)} photos written to {folder}"))

    # ------------------------------------------------------------------ import
    def import_(self, folder, apply, replace, author_username=None):
        with open(os.path.join(folder, 'report.json'), encoding='utf-8') as handle:
            data = json.load(handle)
        project = Project.objects.filter(project_symbol=data['project']).first()
        if not project:
            raise CommandError(f"This database has no project {data['project']}.")
        author = project.site_engineer
        if author_username:
            from django.contrib.auth import get_user_model
            author = get_user_model().objects.filter(username=author_username, is_active=True).first()
            if not author:
                raise CommandError(f'No active user named {author_username} on this database; nothing was changed.')
            if author.role not in ('site_engineer', 'project_manager'):
                raise CommandError(f'{author_username} is a {author.role}; the report author must be a site engineer or a project manager. Nothing was changed.')
        if not author:
            raise CommandError(f'{project.project_symbol} has no site engineer here: add --author USERNAME (a site engineer or project manager). Nothing was changed.')
        phases = {p.code: p for p in ProjectPhase.objects.filter(project=project)}
        needed = {row['phase'] for row in data['phase_updates']} | {row['phase'] for row in data['photos']}
        missing = sorted(needed - set(phases))
        if missing:
            raise CommandError(f'This database has no BOQ phase with code(s) {missing} (copy the BOQ first with boq_pricing); nothing was changed.')
        missing_files = [row['file'] for row in data['photos'] if not os.path.isfile(os.path.join(folder, 'photos', row['file']))]
        if missing_files:
            raise CommandError(f'{len(missing_files)} photo file(s) are missing in the bundle: {missing_files[:3]}; nothing was changed.')
        number = data['report']['report_number']
        existing = OwnerFinancialReport.all_objects.filter(report_number=number).first()
        if existing and not replace:
            raise CommandError(f'This database already has the report {number} (status {existing.status}); nothing was changed. Add --replace to replace it.')

        report_data = {name: _load(name, data['report'][name]) for name in REPORT_FIELDS}
        self.stdout.write(f"Report {number}: period {report_data['reporting_period_from']} -> {report_data['reporting_period_to']}, previous payments "
                          f"{report_data['previous_payments_total']:,.2f}; {len(data['price_items'])} price rows, {len(data['phase_updates'])} phase "
                          f"descriptions, {len(data['photos'])} photos. Project: {project.project_symbol} (contract value here: {project.contract_value}).")
        self.stdout.write(f'Author on this database: {author.username} ({author.role}).')
        self.stdout.write('This database: ' + (f'the report exists ({existing.status}) and would be REPLACED.' if existing else 'no such report -> it would be created as a draft.'))
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return

        with transaction.atomic():
            if existing:
                ProjectPhasePhoto.objects.filter(owner_financial_report=existing).delete()
                existing.delete()
            report = OwnerFinancialReport.objects.create(project=project, site_engineer=author, status='draft', **report_data)
            if data.get('frozen_progress'):   # the report was final when it was exported: keep it final, with the same fixed figures
                report.frozen_progress = data['frozen_progress']
                report.frozen_at = datetime.datetime.fromisoformat(data['frozen_at'])
                report.save(update_fields=['frozen_progress', 'frozen_at'])
            for row in data['price_items']:
                OwnerReportPriceComparisonItem.objects.create(
                    report=report, item_type=row['item_type'], item_name=row['item_name'], unit=row['unit'], quantity=Decimal(row['quantity']),
                    old_unit_price=Decimal(row['old_unit_price']), new_unit_price=Decimal(row['new_unit_price']))
            for row in data['phase_updates']:
                OwnerReportPhaseUpdate.objects.create(report=report, phase=phases[row['phase']], status=row['status'],
                                                      work_performed=row['work_performed'], order=row['order'])
            for row in data['photos']:
                with open(os.path.join(folder, 'photos', row['file']), 'rb') as source:
                    stored = default_storage.save(row['stored_name'], ContentFile(source.read()))
                sub = ProjectPhaseSubItem.objects.filter(phase=phases[row['phase']], name_ar=row['sub_item']).first() if row['sub_item'] else None
                ProjectPhasePhoto.objects.create(phase=phases[row['phase']], sub_item=sub, photo=stored, caption=row['caption'],
                                                 taken_date=_load('report_date', row['taken_date']) if row['taken_date'] else None,
                                                 order=row['order'], owner_financial_report=report)
        self.stdout.write(self.style.SUCCESS(f'Report {number} written: {len(data["price_items"])} price rows, {len(data["phase_updates"])} phase descriptions, '
                                             f'{len(data["photos"])} photos. Amount due here: {report.amount_due():,.2f}.'))
