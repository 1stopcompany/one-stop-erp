"""
Copy a project's BOQ progress entries (the recorded execution % of each contract item, by date) from one database to another -- e.g.
from the local PC to the server -- and, only when asked, the project's contract money values.

    python manage.py progress_copy export TAB reports/data/progress_TAB.json
    python manage.py progress_copy import reports/data/progress_TAB.json                       # preview only
    python manage.py progress_copy import reports/data/progress_TAB.json --apply
    python manage.py progress_copy import reports/data/progress_TAB.json --with-project-values [--apply]

Items are matched by the phase code and the item's Arabic name (the BOQ must already be there: see `boq_pricing`). For every entry
of the file: when this database has an entry for the same item and date its % is updated if different, otherwise it is created.
Nothing is ever deleted, and entries this database has that the file does not are left alone. Entries are copied without their
link to a daily / monthly report or the user who recorded them.

--with-project-values also copies the contract value, the advance payment value and the performance retention rate of the project
(shown first); the project's status, dates and everything else are never touched.
"""
import datetime
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import ProjectPhaseProgressEntry, ProjectPhaseSubItem

PROJECT_FIELDS = ('contract_value', 'advance_payment_value', 'performance_retention_rate')


def _text(value):
    return ' '.join((value or '').split())


class Command(BaseCommand):
    help = "Export / import a project's BOQ progress entries (and optionally its contract money values) between databases."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('target', help='export: the project symbol (e.g. TAB); import: the JSON file')
        parser.add_argument('path', nargs='?', help='export: the JSON file to write')
        parser.add_argument('--apply', action='store_true', help='import: really write the changes (without it, only a preview)')
        parser.add_argument('--with-project-values', action='store_true',
                            help="import: also copy the project's contract value, advance payment value and retention rate")

    def handle(self, *args, **options):
        if options['action'] == 'export':
            return self.export(options['target'], options['path'])
        return self.import_(options['target'], options['apply'], options['with_project_values'])

    def export(self, symbol, path):
        if not path:
            raise CommandError('export needs the output file: progress_copy export TAB path.json')
        project = Project.objects.filter(project_symbol=symbol).first()
        if not project:
            raise CommandError(f'No project with the symbol {symbol}.')
        entries = (ProjectPhaseProgressEntry.objects.filter(sub_item__phase__project=project)
                   .select_related('sub_item__phase').order_by('sub_item__phase__order', 'sub_item__order', 'report_date', 'id'))
        rows = [{
            'phase': e.sub_item.phase.code, 'item': _text(e.sub_item.name_ar), 'date': e.report_date.isoformat(),
            'percent': str(e.execution_percentage), 'notes': e.notes or '',
        } for e in entries]
        data = {'version': 1, 'project': symbol, 'entries': rows,
                'project_values': {name: (None if getattr(project, name) is None else str(getattr(project, name))) for name in PROJECT_FIELDS}}
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=0)
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} progress entries of {symbol} written to {path}'))

    def import_(self, path, apply, with_values):
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        project = Project.objects.filter(project_symbol=data['project']).first()
        if not project:
            raise CommandError(f"This database has no project {data['project']}.")
        subs = {(s.phase.code, _text(s.name_ar)): s
                for s in ProjectPhaseSubItem.objects.filter(phase__project=project).select_related('phase')}
        missing = sorted({(r['phase'], r['item']) for r in data['entries'] if (r['phase'], r['item']) not in subs})
        if missing:
            for phase, item in missing:
                self.stderr.write(f'  no BOQ item here for phase {phase} - {item}')
            raise CommandError(f'{len(missing)} BOQ item(s) of the file do not exist on this database (copy the BOQ first with boq_pricing); nothing was changed.')

        create, update, same = [], [], 0
        for row in data['entries']:
            sub = subs[(row['phase'], row['item'])]
            day, percent = datetime.date.fromisoformat(row['date']), Decimal(row['percent'])
            existing = ProjectPhaseProgressEntry.objects.filter(sub_item=sub, report_date=day).order_by('id').first()
            if existing is None:
                create.append((sub, day, percent, row['notes']))
            elif existing.execution_percentage != percent:
                update.append((existing, percent, row['notes']))
            else:
                same += 1
        self.stdout.write(f"File: {len(data['entries'])} progress entries. Here: {len(create)} to create, {len(update)} to update, {same} already the same.")
        for entry, percent, _ in update[:20]:
            self.stdout.write(f'  update {entry.sub_item.phase.code} / {_text(entry.sub_item.name_ar)[:30]} {entry.report_date}: {entry.execution_percentage} -> {percent}')

        changes = {}
        if with_values:
            for name in PROJECT_FIELDS:
                new = data['project_values'].get(name)
                new = None if new is None else Decimal(new)
                old = getattr(project, name)
                self.stdout.write(f'  project {name}: {old} -> {new}')
                if new is not None and old != new:
                    changes[name] = new
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        with transaction.atomic():
            for entry, percent, notes in update:
                entry.execution_percentage = percent
                if notes:
                    entry.notes = notes
                entry.save()
            for sub, day, percent, notes in create:
                ProjectPhaseProgressEntry.objects.create(sub_item=sub, report_date=day, execution_percentage=percent, notes=notes)
            if changes:
                for name, value in changes.items():
                    setattr(project, name, value)
                project.save(update_fields=list(changes))
        self.stdout.write(self.style.SUCCESS(f'{len(create)} created, {len(update)} updated' + (f', project values set: {sorted(changes)}.' if changes else '.')))
