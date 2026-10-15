"""
Carrying monthly (EDGE) reports from one installation to another (e.g. the reports prepared on the office computer -> the company server) without touching
the other database by hand: export_package() writes one zip (the data as JSON + the attached files), and import_package() reads it back -- first as a
preview that changes nothing, then, only when asked, as new DRAFT reports.

    what travels: the report's own fields and every table of it (progress rows, key activities, issues, floors, external works, material supplies,
                  upcoming works, legacy workforce / equipment / activities) and its attachments (the files)
    what does not: the consultant's review comments, the site photos of the photographic record (reported in the preview), the approval / review
                   signatures (a copy always starts as a draft) and the report number (a new one is generated)
    safety:        the project is found by its symbol; a report whose project and period already exist is never touched or duplicated
"""
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

FORMAT_VERSION = 1
RELATIONS = ('progress_category_items', 'key_activities', 'issues_risks_delays', 'floor_activities', 'external_works', 'material_supplies',
             'upcoming_works', 'workforce', 'equipment', 'activities')
# the report's own fields that are never copied (identity, workflow, timestamps, people)
SKIP_REPORT_FIELDS = {'id', 'report_number', 'project', 'site_engineer', 'status', 'deleted_at', 'deleted_by', 'reviewed_by', 'review_date', 'approved_by',
                      'approval_date', 'rejection_reason', 'created_at', 'updated_at'}
SKIP_ROW_FIELDS = {'id', 'report', 'created_at', 'updated_at', 'floor'}


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row(obj, skip=SKIP_ROW_FIELDS):
    return {f.name: _plain(f.value_from_object(obj)) for f in obj._meta.concrete_fields if f.name not in skip}


def _from_row(model, data, **extra):
    values = {}
    for f in model._meta.concrete_fields:
        if f.name in data and f.name not in SKIP_ROW_FIELDS:
            values[f.name] = f.to_python(data[f.name])
    values.update(extra)
    return model(**values)


# ------------------------------------------------------------------ export
def export_package(reports):
    from reports.models import ReportAttachment
    from reports.progress_models import ProjectPhasePhoto

    payload = {'format': FORMAT_VERSION, 'exported_at': timezone.now().isoformat(), 'reports': []}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        file_no = 0
        for report in reports:
            item = {'source_id': report.pk, 'source_number': report.report_number, 'project_symbol': report.project.project_symbol,
                    'fields': {f.name: _plain(f.value_from_object(report)) for f in report._meta.concrete_fields if f.name not in SKIP_REPORT_FIELDS},
                    'tables': {}, 'attachments': [], 'photos_not_included': ProjectPhasePhoto.objects.filter(monthly_report=report).count(),
                    'review_comments_not_included': report.review_comments.count()}
            for relation in RELATIONS:
                rows = []
                for obj in getattr(report, relation).all():
                    row = _row(obj)
                    if relation == 'floor_activities':
                        row['floor_number'] = obj.floor.floor_number
                    rows.append(row)
                item['tables'][relation] = rows
            for attachment in ReportAttachment.objects.filter(report_type='monthly', report_id=report.pk).order_by('order', 'created_at'):
                entry = {'attachment_type': attachment.attachment_type, 'description': attachment.description, 'location': attachment.location, 'order': attachment.order,
                         'name': attachment.file.name.rsplit('/', 1)[-1] if attachment.file else '', 'archive_name': ''}
                if attachment.file:
                    try:
                        with attachment.file.open('rb') as handle:
                            file_no += 1
                            entry['archive_name'] = f'files/{file_no:03d}_{entry["name"]}'
                            archive.writestr(entry['archive_name'], handle.read())
                    except FileNotFoundError:
                        entry['missing'] = True
                item['attachments'].append(entry)
            payload['reports'].append(item)
        archive.writestr('data.json', json.dumps(payload, ensure_ascii=False, indent=1))
    return buffer.getvalue()


# ------------------------------------------------------------------ import
def read_package(raw):
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        payload = json.loads(archive.read('data.json').decode('utf-8'))
        if payload.get('format') != FORMAT_VERSION:
            raise ValueError('This package was made by a different version of the export.')
        files = {name: archive.read(name) for name in archive.namelist() if name.startswith('files/')}
    return payload, files


def plan(payload, author_username=''):
    """For every report in the package: what would happen (nothing is written). Returns a list of dicts."""
    from accounts.models import CustomUser
    from projects.models import Project, ProjectFloor
    from reports.models import MonthlyReport

    results = []
    author = CustomUser.objects.filter(username=author_username).first() if author_username else None
    for item in payload['reports']:
        fields = item['fields']
        project = Project.objects.filter(project_symbol=item['project_symbol']).first()
        result = {'item': item, 'project': project, 'problems': [], 'warnings': [], 'author': None, 'ok': True}
        if project is None:
            result['problems'].append(f'No project with the symbol {item["project_symbol"]} exists here.')
        else:
            result['author'] = author or project.manager or CustomUser.objects.filter(role='admin').order_by('id').first()
            if author_username and author is None:
                result['problems'].append(f'The author {author_username} does not exist here.')
            existing = MonthlyReport.objects.filter(project=project, reporting_period_from=fields['reporting_period_from'], reporting_period_to=fields['reporting_period_to']).first()
            if existing is not None:
                result['problems'].append(f'A monthly report for {fields["reporting_period_from"]} - {fields["reporting_period_to"]} already exists here ({existing.report_number}); it is left alone.')
            for row in item['tables'].get('floor_activities', []):
                if not ProjectFloor.objects.filter(project=project, floor_number=row.get('floor_number')).exists():
                    result['warnings'].append(f'Floor "{row.get("floor_number")}" does not exist in {project.project_symbol} here: that floor row is skipped.')
        if item.get('photos_not_included'):
            result['warnings'].append(f'{item["photos_not_included"]} photo(s) of the photographic record are not carried by the package.')
        if item.get('review_comments_not_included'):
            result['warnings'].append(f'{item["review_comments_not_included"]} consultant comment(s) are not carried.')
        for attachment in item['attachments']:
            if not attachment.get('archive_name'):
                result['warnings'].append(f'Attachment "{attachment["description"][:50]}": its file was missing on the exporting side.')
        result['ok'] = not result['problems']
        results.append(result)
    return results


@transaction.atomic
def apply(results, files):
    """Create the reports of every OK entry of plan() as drafts. Returns [(source number, new report)]."""
    from projects.models import ProjectFloor
    from reports.models import MonthlyReport, ReportAttachment

    from reports import models as report_models

    created = []
    for result in results:
        if not result['ok']:
            continue
        item, project = result['item'], result['project']
        values = {}
        for f in MonthlyReport._meta.concrete_fields:
            if f.name in item['fields'] and f.name not in SKIP_REPORT_FIELDS:
                values[f.name] = f.to_python(item['fields'][f.name])
        report = MonthlyReport.objects.create(project=project, site_engineer=result['author'], status='draft', **values)
        for relation in RELATIONS:
            model = getattr(MonthlyReport, relation).rel.related_model
            for row in item['tables'].get(relation, []):
                extra = {'report': report}
                if relation == 'floor_activities':
                    floor = ProjectFloor.objects.filter(project=project, floor_number=row.get('floor_number')).first()
                    if floor is None:
                        continue
                    extra['floor'] = floor
                _from_row(model, row, **extra).save()
        for attachment in item['attachments']:
            if not attachment.get('archive_name'):
                continue
            record = ReportAttachment(report_type='monthly', report_id=report.pk, attachment_type=attachment['attachment_type'], description=attachment['description'],
                                      location=attachment['location'], order=attachment['order'], uploaded_by=result['author'])
            record.file.save(attachment['name'], ContentFile(files[attachment['archive_name']]), save=True)
        created.append((item['source_number'], report))
    return created
