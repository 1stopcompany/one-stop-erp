"""
Load the signed tools inventory sheet into the tools register.

    python manage.py import_tools_inventory --user admin                      # preview only
    python manage.py import_tools_inventory --user admin --apply

Every tool first enters the Main Warehouse (a completed "Received" record), and those listed on a project are then issued to it
(a completed "Issued" record), so each tool starts with a real history. Tools are matched by their inventory reference, so running
it again changes nothing; a project symbol or warehouse that does not exist here stops the whole import before anything is written.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from equipment import services
from equipment.models import Tool, ToolTransfer
from procurement.models import Warehouse
from projects.models import Project

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'electrical_tools_2026-10.json')


class Command(BaseCommand):
    help = 'Import the tools inventory sheet (equipment/data/electrical_tools_2026-10.json) into the tools register.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=DEFAULT_FILE)
        parser.add_argument('--user', required=True, help='Username recorded as the person who received / issued the tools (an admin or storekeeper)')
        parser.add_argument('--warehouse', default='Main Warehouse')
        parser.add_argument('--apply', action='store_true', help='Really write (without it: preview)')

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.filter(username=options['user'], is_active=True).first()
        if not user:
            raise CommandError(f"No active user named {options['user']}; nothing was changed.")
        warehouse = Warehouse.objects.filter(name=options['warehouse']).first()
        if not warehouse:
            raise CommandError(f"No warehouse named {options['warehouse']}; nothing was changed.")
        with open(options['file'], encoding='utf-8') as handle:
            data = json.load(handle)
        symbols = {t['location'] for t in data['tools'] if t['location'] != 'WH'}
        projects = {p.project_symbol: p for p in Project.objects.filter(project_symbol__in=symbols)}
        missing = sorted(symbols - set(projects))
        if missing:
            raise CommandError(f'This database has no project with the symbol(s) {missing}; nothing was changed.')

        existing = set(Tool.objects.exclude(source_ref='').values_list('source_ref', flat=True))
        todo = [t for t in data['tools'] if t['ref'] not in existing]
        by_place = {}
        for t in todo:
            by_place[t['location']] = by_place.get(t['location'], 0) + 1
        self.stdout.write(f"{len(data['tools'])} tools in the sheet; {len(data['tools']) - len(todo)} already imported; {len(todo)} to import.")
        for place, count in sorted(by_place.items()):
            self.stdout.write(f"  -> {count} end up {'in ' + warehouse.name if place == 'WH' else 'on project ' + place}")
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write it.'))
            return

        inventory_date = timezone.datetime.fromisoformat(data['inventory_date']).date()
        now = timezone.now()
        with transaction.atomic():
            for t in todo:
                tool = Tool.objects.create(name=t['name'], category=t['category'], manufacturer=t['manufacturer'], status=t['status'],
                                           holder=t['holder'], notes=t['notes'], source_ref=t['ref'], last_inventory_date=inventory_date)
                services.receive_into_warehouse(tool, warehouse, user, note=f"Opening entry from the inventory sheet of {data['inventory_date']}", when=now)
                if t['location'] != 'WH':
                    project = projects[t['location']]
                    tool.warehouse, tool.project = None, project
                    tool.save()
                    ToolTransfer.objects.create(
                        tool=tool, kind=ToolTransfer.KIND_ISSUE, status=ToolTransfer.COMPLETED, from_warehouse=warehouse, to_project=project,
                        note='Current location in the inventory sheet', requested_by=user, requested_at=now, approved_by=user, approved_at=now,
                        completed_by=user, completed_at=now)
                if t['status'] == Tool.STATUS_BROKEN:
                    services.open_maintenance(tool, user, t['notes'])
                    tool.refresh_from_db()
                    tool.status = Tool.STATUS_BROKEN
                    tool.save(update_fields=['status'])
        self.stdout.write(self.style.SUCCESS(f'{len(todo)} tools imported.'))
