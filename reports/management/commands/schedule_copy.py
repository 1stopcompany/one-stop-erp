"""
Copy a project's imported schedule (the Gantt's tasks) from one database to another -- e.g. from the local PC to the server --
exactly as it is stored: every task with its dates, duration, slack, critical flag, predecessors, baseline and actual dates.

    python manage.py schedule_copy export TAB reports/data/schedule_TAB.json
    python manage.py schedule_copy import reports/data/schedule_TAB.json              # preview only
    python manage.py schedule_copy import reports/data/schedule_TAB.json --apply

Only the project's schedule tasks (ScheduleTask) are written. When this database already has tasks for the project the import is
refused, unless --replace is added (then those are replaced by the file's). Nothing else is touched.
"""
import datetime
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from projects.models import Project
from reports.schedule_models import ScheduleTask

SKIP = {'id', 'project', 'imported_at'}


def _fields():
    return [f for f in ScheduleTask._meta.fields if f.name not in SKIP]


def _dump(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _load(field, value):
    if value is None:
        return None
    if isinstance(field, models.DateTimeField):
        return datetime.datetime.fromisoformat(value)
    if isinstance(field, models.DateField):
        return datetime.date.fromisoformat(value)
    if isinstance(field, models.DecimalField):
        return Decimal(str(value))
    return value


class Command(BaseCommand):
    help = "Export / import a project's schedule tasks (the Gantt data) between databases."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('target', help='export: the project symbol (e.g. TAB); import: the JSON file')
        parser.add_argument('path', nargs='?', help='export: the JSON file to write')
        parser.add_argument('--apply', action='store_true', help='import: really write it (without it, only a preview)')
        parser.add_argument('--replace', action='store_true', help='import: replace the tasks this database already has for the project')

    def handle(self, *args, **options):
        if options['action'] == 'export':
            return self.export(options['target'], options['path'])
        return self.import_(options['target'], options['apply'], options['replace'])

    def export(self, symbol, path):
        if not path:
            raise CommandError('export needs the output file: schedule_copy export TAB path.json')
        project = Project.objects.filter(project_symbol=symbol).first()
        if not project:
            raise CommandError(f'No project with the symbol {symbol}.')
        tasks = ScheduleTask.objects.filter(project=project).order_by('source_task_id', 'id')
        rows = [{f.name: _dump(getattr(task, f.name)) for f in _fields()} for task in tasks]
        if not rows:
            raise CommandError(f'{symbol} has no schedule tasks here.')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'version': 1, 'project': symbol, 'tasks': rows}, handle, ensure_ascii=False, indent=0)
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} tasks of {symbol} written to {path}'))

    def import_(self, path, apply, replace):
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        project = Project.objects.filter(project_symbol=data['project']).first()
        if not project:
            raise CommandError(f"This database has no project {data['project']}.")
        rows = data['tasks']
        starts = [row['start_date'] for row in rows if row.get('start_date')]
        finishes = [row['finish_date'] for row in rows if row.get('finish_date')]
        critical = sum(1 for row in rows if row.get('is_critical'))
        self.stdout.write(f"File: {len(rows)} tasks, {min(starts)} -> {max(finishes)}, {critical} critical.")
        existing = ScheduleTask.objects.filter(project=project).count()
        if existing and not replace:
            raise CommandError(f'This database already has {existing} schedule task(s) for {project.project_symbol}; nothing was changed. '
                               f'Add --replace to replace them by the file\'s.')
        self.stdout.write(f'This database: {existing} existing task(s) for {project.project_symbol}'
                          + (' -> they would be REPLACED.' if existing else ' -> the schedule would be created.'))
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        fields = _fields()
        with transaction.atomic():
            ScheduleTask.objects.filter(project=project).delete()
            ScheduleTask.objects.bulk_create([
                ScheduleTask(project=project, **{f.name: _load(f, row.get(f.name)) for f in fields}) for row in rows
            ])
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} tasks written for {project.project_symbol}.'))
