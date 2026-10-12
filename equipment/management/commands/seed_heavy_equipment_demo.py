"""
Demo heavy equipment on the DEMOCC project, so the register, the daily report's equipment list and the monthly rental claims can be seen
working:  python manage.py seed_heavy_equipment_demo        (--clear removes what it created)

Creates two rental vendors, five heavy equipment (two owned, three rented at an hourly / daily / monthly rate) registered on DEMOCC, and
puts them on the project's existing demo daily reports (hours, idle hours, operator, meter), so `generate_equipment_claims --date ...`
has something to claim. Demo data only: nothing here touches a real project, and it is meant for a local database.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from equipment import services
from equipment.models import EquipmentClaim, Tool, ToolTransfer
from procurement.models import Vendor
from projects.models import Project
from reports.daily_detail_models import DailyReportActivityProgress
from reports.models import DailyEquipment, DailyReport

DEMO = '[DEMO] '
VENDORS = [DEMO + 'Hebron Heavy Rentals', DEMO + 'Al-Amal Machinery']
# (name, make, plate, operator, ownership, vendor index, rate, unit, meter, hours per working day)
FLEET = [
    ('Wheel Loader 966', 'CAT', '55-410-21', 'Abu Samer', 'owned', None, None, 'day', '4210.0', '6'),
    ('Dump Truck 18 m3', 'Mercedes', '62-118-04', 'Jamal', 'owned', None, None, 'day', '9830.5', '5.5'),
    ('Excavator 20T', 'Komatsu PC200', '71-336-90', 'Mahmoud A.', 'rented', 0, Decimal('280'), 'hour', '2310.0', '7.5'),
    ('Backhoe Loader', 'JCB 3CX', '58-902-17', 'Hani', 'rented', 1, Decimal('650'), 'day', '5120.0', '8'),
    ('Concrete Pump 36m', 'Putzmeister', '44-207-63', 'Ziad', 'rented', 1, Decimal('18000'), 'month', '860.0', '6'),
]


class Command(BaseCommand):
    help = 'Seed demo heavy equipment (and their hours on the demo daily reports) on the DEMOCC project.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Remove the demo heavy equipment, their report rows and claims')

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol='DEMOCC').first()
        if not project:
            raise CommandError('The DEMOCC demo project does not exist here (run the other demo seeds first).')
        demo_tools = Tool.objects.filter(kind=Tool.KIND_HEAVY, source_ref__startswith='DEMO-HEAVY')
        if options['clear']:
            EquipmentClaim.objects.filter(tool__in=demo_tools).delete()
            DailyEquipment.objects.filter(tool__in=demo_tools).delete()
            ToolTransfer.objects.filter(tool__in=demo_tools).delete()
            count = demo_tools.count()
            demo_tools.delete()
            Vendor.objects.filter(name__in=VENDORS).delete()
            self.stdout.write(self.style.SUCCESS(f'Removed {count} demo heavy equipment.'))
            return
        admin = project.manager or project.site_engineer
        if not admin:
            raise CommandError('DEMOCC has no manager / site engineer to act as the person registering the equipment.')
        vendors = [Vendor.objects.get_or_create(name=name)[0] for name in VENDORS]
        created = []
        for index, (name, make, plate, operator, ownership, vendor_i, rate, unit, meter, _hours) in enumerate(FLEET, start=1):
            ref = f'DEMO-HEAVY-{index}'
            tool = Tool.objects.filter(source_ref=ref).first()
            if tool:
                continue
            tool = Tool(kind=Tool.KIND_HEAVY, name=name, manufacturer=make, plate_no=plate, operator=operator, ownership=ownership,
                        rental_vendor=vendors[vendor_i] if vendor_i is not None else None, rental_rate=rate, rental_rate_unit=unit,
                        hour_meter=Decimal(meter), status=Tool.STATUS_WORKING, source_ref=ref)
            tool.save()
            services.receive_at(tool, admin, project=project, note='Demo heavy equipment registered on the project')
            created.append(tool)

        # hours on the project's demo daily reports that were actually filed (not the drafts)
        reports = list(DailyReport.objects.filter(project=project, status__in=('submitted', 'engineering_approved', 'approved')).order_by('report_date'))
        rows = 0
        for tool in Tool.objects.filter(source_ref__startswith='DEMO-HEAVY').order_by('source_ref'):
            hours = Decimal(FLEET[int(tool.source_ref.rsplit('-', 1)[1]) - 1][9])
            for report in reports:
                if DailyEquipment.objects.filter(report=report, tool=tool).exists():
                    continue
                activity = report.activity_progress_entries.first() or DailyReportActivityProgress.objects.create(
                    report=report, activity_description='Site excavation and levelling', quantity_today=Decimal('1'), unit='m3')
                DailyEquipment.objects.create(report=report, tool=tool, activity=activity, hours_worked=hours, idle_hours=Decimal('1') if tool.ownership == 'rented' else 0,
                                              operator_name=tool.operator, meter_reading=tool.hour_meter + hours)
                rows += 1
        self.stdout.write(self.style.SUCCESS(f'{len(created)} demo heavy equipment registered on DEMOCC, {rows} hour rows put on its daily reports. '
                                             'Try:  python manage.py generate_equipment_claims --date 2026-09-25 --project DEMOCC'))
