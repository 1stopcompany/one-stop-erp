"""
Copy a project's BOQ (phases, items, weights, dates, units, quantities, contract and budget prices) from one database to another
-- e.g. from the local PC to the server -- without touching anything else.

    python manage.py boq_pricing export TAB reports/data/boq_pricing_TAB.json
    python manage.py boq_pricing import reports/data/boq_pricing_TAB.json                     # preview only
    python manage.py boq_pricing import reports/data/boq_pricing_TAB.json --apply

* When the project on this database already has the same phases and items (matched by the phase code and the item's Arabic
  name), only these fields of the existing items are UPDATED: weight, unit, quantity, contract price, budget price.
* When the project's BOQ here is different (for example only a stub), the whole BOQ is REPLACED by the file's:
      python manage.py boq_pricing import reports/data/boq_pricing_TAB.json --replace-structure [--apply]
  This is refused if ANYTHING is attached to the existing phases / items: progress entries, daily-report activities, purchase
  requisition or order lines, subcontract lines, owner-report phase updates, photos, milestones, budget alerts.
Nothing else (reports, purchases, project data, progress) is ever created, changed or deleted.
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

UPDATE_FIELDS = ('weight_percentage', 'unit', 'quantity', 'contract_unit_price', 'budget_unit_price')
PHASE_FIELDS = ('code', 'name_ar', 'name_en', 'weight_percentage', 'order', 'notes', 'section', 'unit', 'quantity',
                'budget_unit_price', 'contract_unit_price')
SUB_FIELDS = ('code', 'name_ar', 'name_en', 'weight_percentage', 'planned_start_date', 'planned_completion_date', 'order', 'unit',
              'quantity', 'budget_unit_price', 'contract_unit_price', 'is_whole')
DECIMALS = {'weight_percentage', 'quantity', 'budget_unit_price', 'contract_unit_price'}
DATES = {'planned_start_date', 'planned_completion_date'}


def _text(value):
    return ' '.join((value or '').split())


def _dec(value):
    return None if value is None else Decimal(str(value))


def _dump(obj, fields):
    out = {}
    for name in fields:
        value = getattr(obj, name)
        out[name] = None if value is None else (value.isoformat() if name in DATES else (str(value) if name in DECIMALS else value))
    return out


def _load(row, fields):
    out = {}
    for name in fields:
        value = row.get(name)
        if value is None:
            out[name] = None
        elif name in DECIMALS:
            out[name] = Decimal(str(value))
        elif name in DATES:
            out[name] = __import__('datetime').date.fromisoformat(value)
        else:
            out[name] = value
    return out


class Command(BaseCommand):
    help = "Export / import a project's BOQ (phases, items, weights, dates, units, quantities, contract and budget prices)."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('target', help="export: the project symbol (e.g. TAB); import: the JSON file")
        parser.add_argument('path', nargs='?', help='export: the JSON file to write')
        parser.add_argument('--apply', action='store_true', help='import: really write the changes (without it, only a preview)')
        parser.add_argument('--replace-structure', action='store_true',
                            help="import: replace the project's whole BOQ here by the file's (refused when anything is attached to it)")

    def handle(self, *args, **options):
        if options['action'] == 'export':
            return self.export(options['target'], options['path'])
        return self.import_(options['target'], options['apply'], options['replace_structure'])

    # ------------------------------------------------------------------ export
    def export(self, symbol, path):
        if not path:
            raise CommandError('export needs the output file: boq_pricing export TAB path.json')
        project = Project.objects.filter(project_symbol=symbol).first()
        if not project:
            raise CommandError(f'No project with the symbol {symbol}.')
        phases = []
        for phase in ProjectPhase.objects.filter(project=project).order_by('order', 'code'):
            row = _dump(phase, PHASE_FIELDS)
            row['items'] = [_dump(sub, SUB_FIELDS) for sub in phase.sub_items.all().order_by('order', 'id')]
            phases.append(row)
        data = {'version': 2, 'project': symbol, 'contract_value': str(project.contract_value), 'phases': phases}
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        items = sum(len(p['items']) for p in phases)
        self.stdout.write(self.style.SUCCESS(f'{len(phases)} phases / {items} items of {symbol} written to {path}'))

    # ------------------------------------------------------------------ import
    def import_(self, path, apply, replace):
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        project = Project.objects.filter(project_symbol=data['project']).first()
        if not project:
            raise CommandError(f"This database has no project {data['project']}.")
        file_items = [(phase, item) for phase in data['phases'] for item in phase['items']]
        total = sum(_dec(item['contract_unit_price']) * (_dec(item['quantity']) or 1) for _, item in file_items)
        self.stdout.write(f"File: {len(data['phases'])} phases, {len(file_items)} items, contract total {total:,.2f} "
                          f"(project contract value on this database: {project.contract_value}).")

        subs = {(sub.phase.code, _text(sub.name_ar)): sub
                for sub in ProjectPhaseSubItem.objects.filter(phase__project=project).select_related('phase')}
        missing = [(phase['code'], _text(item['name_ar'])) for phase, item in file_items if (phase['code'], _text(item['name_ar'])) not in subs]
        if replace:
            return self.replace_structure(project, data, apply)
        if missing:
            for code, name in missing:
                self.stderr.write(f'  no match here for phase {code} - {name}')
            raise CommandError(f'{len(missing)} line(s) of the file have no matching BOQ item on this database; nothing was changed. '
                               f'If this database has a different BOQ for the project, use --replace-structure.')

        changes = []
        for phase, item in file_items:
            sub = subs[(phase['code'], _text(item['name_ar']))]
            new = _load(item, UPDATE_FIELDS)
            diff = {name: (getattr(sub, name), new[name]) for name in UPDATE_FIELDS if getattr(sub, name) != new[name]}
            if diff:
                changes.append((sub, new, diff))
        for sub, _, diff in changes:
            shown = ', '.join(f'{name} {old} -> {new}' for name, (old, new) in diff.items())
            self.stdout.write(f'  {sub.phase.code} / {_text(sub.name_ar)[:40]}: {shown}')
        self.stdout.write(f'{len(changes)} of {len(file_items)} item(s) would change.')
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        with transaction.atomic():
            for sub, new, _ in changes:
                for name in UPDATE_FIELDS:
                    setattr(sub, name, new[name])
                sub.save(update_fields=list(UPDATE_FIELDS) + ['updated_at'])
        self.stdout.write(self.style.SUCCESS(f'{len(changes)} item(s) updated.'))

    # ------------------------------------------------------------------ replace the whole structure
    def attached(self, phases, subs):
        """What is hanging on the existing phases / items: {description: count} for every relation that has rows."""
        found = {}
        for model, queryset in ((ProjectPhase, phases), (ProjectPhaseSubItem, subs)):
            for relation in model._meta.related_objects:
                if relation.related_model is ProjectPhaseSubItem and model is ProjectPhase:
                    continue   # the items themselves (replaced together with their phases)
                count = relation.related_model.objects.filter(**{f'{relation.field.name}__in': queryset}).count()
                if count:
                    found[f'{relation.related_model.__name__}.{relation.field.name}'] = count
        return found

    def replace_structure(self, project, data, apply):
        phases = ProjectPhase.objects.filter(project=project)
        subs = ProjectPhaseSubItem.objects.filter(phase__project=project)
        attached = self.attached(phases, subs)
        if attached:
            for name, count in attached.items():
                self.stderr.write(f'  attached: {name} = {count}')
            raise CommandError('The existing BOQ of this project has records attached to it, so it will not be replaced. Nothing was changed.')
        self.stdout.write(f'This database: {phases.count()} phase(s) and {subs.count()} item(s) for {project.project_symbol} -- nothing is attached to them.')
        self.stdout.write(f"They would be REPLACED by {len(data['phases'])} phases / {sum(len(p['items']) for p in data['phases'])} items from the file.")
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        with transaction.atomic():
            phases.delete()   # its items go with it (checked above: nothing else is attached)
            created_items = 0
            for row in data['phases']:
                phase = ProjectPhase.objects.create(project=project, **_load(row, PHASE_FIELDS))
                for item in row['items']:
                    ProjectPhaseSubItem.objects.create(phase=phase, **_load(item, SUB_FIELDS))
                    created_items += 1
        self.stdout.write(self.style.SUCCESS(f"BOQ replaced: {len(data['phases'])} phases / {created_items} items created."))
