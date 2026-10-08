"""
Copy a project's BOQ pricing from one database to another (e.g. from the local PC to the server) without touching anything else.

    python manage.py boq_pricing export TAB reports/data/boq_pricing_TAB.json
    python manage.py boq_pricing import reports/data/boq_pricing_TAB.json            # dry run: only shows what would change
    python manage.py boq_pricing import reports/data/boq_pricing_TAB.json --apply    # writes it

It only UPDATES existing BOQ sub-items (matched by the phase code and the item's Arabic name) and only these fields: weight,
unit, quantity, contract unit price, budget unit price. It never creates or deletes a phase / item, never touches progress
entries, reports, purchases or anything else, and refuses to run if a line of the file has no match on this database.
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import ProjectPhaseSubItem

FIELDS = ('weight_percentage', 'unit', 'quantity', 'contract_unit_price', 'budget_unit_price')


def _text(value):
    return ' '.join((value or '').split())


def _dec(value):
    return None if value is None else Decimal(str(value))


class Command(BaseCommand):
    help = "Export / import a project's BOQ pricing (weights, units, quantities, contract and budget prices)."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('target', help="export: the project symbol (e.g. TAB); import: the JSON file")
        parser.add_argument('path', nargs='?', help='export: the JSON file to write')
        parser.add_argument('--apply', action='store_true', help='import: really write the changes (without it, only a preview)')

    def handle(self, *args, **options):
        if options['action'] == 'export':
            return self.export(options['target'], options['path'])
        return self.import_(options['target'], options['apply'])

    # ------------------------------------------------------------------ export
    def export(self, symbol, path):
        if not path:
            raise CommandError('export needs the output file: boq_pricing export TAB path.json')
        project = Project.objects.filter(project_symbol=symbol).first()
        if not project:
            raise CommandError(f'No project with the symbol {symbol}.')
        rows = []
        for sub in ProjectPhaseSubItem.objects.filter(phase__project=project).select_related('phase').order_by('phase__order', 'order', 'id'):
            rows.append({
                'phase': sub.phase.code, 'name': _text(sub.name_ar),
                'weight_percentage': str(sub.weight_percentage), 'unit': sub.unit,
                'quantity': None if sub.quantity is None else str(sub.quantity),
                'contract_unit_price': str(sub.contract_unit_price), 'budget_unit_price': str(sub.budget_unit_price),
            })
        data = {'project': symbol, 'contract_value': str(project.contract_value), 'items': rows}
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} items of {symbol} written to {path}'))

    # ------------------------------------------------------------------ import
    def import_(self, path, apply):
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        project = Project.objects.filter(project_symbol=data['project']).first()
        if not project:
            raise CommandError(f"This database has no project {data['project']}.")

        subs = {}
        for sub in ProjectPhaseSubItem.objects.filter(phase__project=project).select_related('phase'):
            subs[(sub.phase.code, _text(sub.name_ar))] = sub
        missing = [(row['phase'], row['name']) for row in data['items'] if (row['phase'], row['name']) not in subs]
        if missing:
            for key in missing:
                self.stderr.write(f'  no match here for phase {key[0]} - {key[1]}')
            raise CommandError(f'{len(missing)} line(s) of the file have no matching BOQ item on this database; nothing was changed.')
        extra = len(subs) - len(data['items'])
        if extra:
            self.stdout.write(self.style.WARNING(f'  note: this database has {extra} item(s) that are not in the file; they are left as they are.'))

        changes = []
        for row in data['items']:
            sub = subs[(row['phase'], row['name'])]
            new = {
                'weight_percentage': _dec(row['weight_percentage']), 'unit': row['unit'], 'quantity': _dec(row['quantity']),
                'contract_unit_price': _dec(row['contract_unit_price']), 'budget_unit_price': _dec(row['budget_unit_price']),
            }
            diff = {name: (getattr(sub, name), new[name]) for name in FIELDS if getattr(sub, name) != new[name]}
            if diff:
                changes.append((sub, new, diff))

        for sub, _, diff in changes:
            shown = ', '.join(f'{name} {old} -> {new}' for name, (old, new) in diff.items())
            self.stdout.write(f'  {sub.phase.code} / {_text(sub.name_ar)[:40]}: {shown}')
        file_contract = sum(_dec(row['contract_unit_price']) * (_dec(row['quantity']) or 1) for row in data['items'])
        self.stdout.write(f"{len(changes)} of {len(data['items'])} item(s) would change; the file's contract total is {file_contract:,.2f} "
                          f"(project contract value on this database: {project.contract_value:,.2f}).")
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return
        with transaction.atomic():
            for sub, new, _ in changes:
                for name in FIELDS:
                    setattr(sub, name, new[name])
                sub.save(update_fields=list(FIELDS) + ['updated_at'])
        self.stdout.write(self.style.SUCCESS(f'{len(changes)} item(s) updated.'))
