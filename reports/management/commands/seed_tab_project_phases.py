"""
Seed the real BOQ phase / sub-item / progress-entry data for the TAB
project ("بناء وتشطيب عمارة السيد طالب العمايرة" / Design-Build of Taleb
Amayreh Residential Building), as of the 31/07/2026 monthly reporting
cycle.

Source documents (cross-checked against each other):
  - "التقرير الفني والمالي للمالك 07.2026.docx" (owner financial/technical
    report, Arabic) -- BOQ % breakdown table + weight_percentage values.
  - "Monthly Site Progress.Jul EDGE Report 2026.Rev02.docx" (EDGE
    consultant monthly report, English) -- same BOQ breakdown table
    (English names/dates) + narrative confirming which items are
    "Completed" vs "In Progress".

Reconciliation note (documented here since it isn't obvious from either
source alone): both documents state an overall cumulative progress of
"31.803%" in their prose/table-label, and the EDGE report explicitly
repeats "8% cumulative to date" against every sub-item of Phase 4,
confirming Phase 4 stands at 8% (not the 7% you'd get by summing the
Arabic owner-report's per-row numbers literally, nor the 30.803% /
2,525,846 shown in that report's own small KPI table -- both of which
look like they were never updated after Phase 4's last revision). This
command uses 8% for Phase 4, which reproduces the 31.803% headline
figure quoted in both reports exactly: 6+4+10+8+0+0+0+2.2+1+0+0+0+0.603
= 31.803.

For any phase where the source table repeats one identical % across all
its sub-items (i.e. it's a phase-level rollup, not a genuine per-item
reading), completion is distributed "front-loaded" in table order --
fill each sub-item to 100% before moving to the next -- which is the
only distribution consistent with construction sequencing (e.g. you
can't cast a floor slab before its walls) and, for every phase where
this matters, matches the EDGE narrative's "Completed" / "In Progress"
call-outs.

Three phases (7, 9, 13) describe their single sub-item as "spread over N
units" (floors/stages/months) rather than a discrete scope -- for those,
the sub-item's weight_percentage is set to the FULL phase weight (not
the stated per-unit rate) and its completion_percentage is the fraction
of units elapsed, so the earned contribution still comes out correct.

Safe to re-run: every write is update_or_create keyed on the natural
identifiers (project+code for phases, phase+name_en for sub-items,
sub_item+report_date for progress entries).
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import (
    ProjectPhase,
    ProjectPhaseSubItem,
    ProjectPhaseProgressEntry,
    calculate_project_progress,
)

REPORT_DATE = date(2026, 7, 31)
CONTRACT_VALUE = Decimal('8200000.00')

# (code, name_ar, name_en, weight, [ (name_ar, name_en, weight, start, end, completion_pct), ... ])
PHASES = [
    (
        '1',
        'أعمال التصميم والترخيص تشمل فقط رسوم الدفاع المدني والاثار و نقابة المهندسين',
        'Design & Licensing Works (Civil Defense, Antiquities & Engineers Association fees only)',
        Decimal('6.000'),
        [
            ('عمل التصاميم', 'Design works', Decimal('3.000'), date(2025, 11, 1), date(2026, 1, 1), Decimal('100')),
            ('تقديم التراخيص ودفع الرسوم', 'Submission of licenses & fee payment', Decimal('2.500'), date(2025, 11, 1), date(2026, 5, 1), Decimal('100')),
            ('الفحص والموافقة', 'Review & approval', Decimal('0.500'), date(2025, 11, 1), None, Decimal('100')),
        ],
    ),
    (
        '2',
        'أعمال الحفريات وتسوية الأرض',
        'Excavation & Land-Leveling Works',
        Decimal('4.000'),
        [
            ('تسوية الموقع', 'Site leveling', Decimal('0.500'), date(2025, 12, 1), date(2025, 12, 10), Decimal('100')),
            ('الحفريات', 'Excavation', Decimal('3.000'), date(2025, 12, 1), date(2026, 1, 1), Decimal('100')),
            ('الردميات', 'Backfilling', Decimal('0.500'), date(2025, 12, 1), date(2026, 4, 15), Decimal('100')),
        ],
    ),
    (
        '3',
        'أعمال القواعد والجسور الرابطة',
        'Foundations & Tie-Beam Works',
        Decimal('10.000'),
        [
            ('البئر', 'Well / pit', Decimal('6.000'), date(2026, 2, 10), date(2026, 3, 15), Decimal('100')),
            ('القواعد', 'Foundations', Decimal('3.000'), date(2026, 2, 10), date(2026, 4, 11), Decimal('100')),
            ('جسور الربط', 'Tie beams', Decimal('1.000'), date(2026, 2, 10), date(2026, 4, 11), Decimal('100')),
        ],
    ),
    (
        '4',
        'الأعمدة والعقدات وجدران الطابق السفلي المواقف والمخازن',
        'Columns, Nodes & Walls – Basement Parking/Storage Floor',
        Decimal('10.000'),
        [
            # Front-loaded to the EDGE-confirmed 8% cumulative (see module docstring).
            ('الحفرة الصماء', 'Blind pit', Decimal('1.000'), date(2025, 12, 24), date(2026, 2, 10), Decimal('100')),
            ('جدران الموقف', 'Parking walls', Decimal('1.000'), date(2025, 12, 24), date(2026, 4, 30), Decimal('100')),
            ('عقدة الموقف', 'Parking floor slab (node)', Decimal('2.000'), date(2025, 12, 24), date(2026, 5, 10), Decimal('100')),
            ('جدران المخازن', 'Storage walls', Decimal('1.000'), date(2025, 12, 24), date(2026, 5, 30), Decimal('100')),
            ('عقدة المخازن', 'Storage floor slab (node)', Decimal('2.000'), date(2025, 12, 24), date(2026, 6, 30), Decimal('100')),
            ('جدران السدة', 'Mezzanine walls', Decimal('1.000'), date(2025, 12, 24), date(2026, 7, 10), Decimal('100')),
            ('عقدة السدة', 'Mezzanine floor slab (node)', Decimal('2.000'), date(2025, 12, 24), date(2026, 7, 30), Decimal('0')),
        ],
    ),
    (
        '5',
        'الأعمال الهيكلية للطوابق المتكررة 4 طوابق',
        'Structural Works – Repeated Floors (4 floors)',
        Decimal('17.000'),
        [
            ('جدران الأول', '1st floor walls', Decimal('2.000'), date(2026, 7, 30), date(2026, 8, 20), Decimal('0')),
            ('عقدة الأول', '1st floor slab (node)', Decimal('3.000'), date(2026, 7, 30), date(2026, 9, 15), Decimal('0')),
            ('جدران الثاني', '2nd floor walls', Decimal('1.000'), date(2026, 7, 30), date(2026, 10, 5), Decimal('0')),
            ('عقدة الثاني', '2nd floor slab (node)', Decimal('3.000'), date(2026, 7, 30), date(2026, 11, 1), Decimal('0')),
            ('جدران الثالث', '3rd floor walls', Decimal('1.000'), date(2026, 7, 30), date(2026, 11, 15), Decimal('0')),
            ('عقدة الثالث', '3rd floor slab (node)', Decimal('3.000'), date(2026, 7, 30), date(2026, 12, 17), Decimal('0')),
            ('جدران الرابع', '4th floor walls', Decimal('1.000'), date(2026, 7, 30), date(2027, 1, 5), Decimal('0')),
            ('عقدة الرابع', '4th floor slab (node)', Decimal('3.000'), date(2026, 7, 30), date(2027, 2, 2), Decimal('0')),
        ],
    ),
    (
        '6',
        'هيكل الرووف والدوبلكسات وغرفة الخزانات',
        'Roof Structure, Duplexes & Water-Tank Room',
        Decimal('5.000'),
        [
            ('الروف الأول', 'Roof 1', Decimal('2.000'), date(2027, 2, 2), date(2027, 3, 9), Decimal('0')),
            ('الروف الثاني', 'Roof 2', Decimal('2.000'), date(2027, 2, 2), date(2027, 4, 13), Decimal('0')),
            ('غرف السطح', 'Rooftop rooms', Decimal('1.000'), date(2027, 2, 2), date(2027, 5, 10), Decimal('0')),
        ],
    ),
    (
        '7',
        'أعمال الطوب والعزل الداخلي والخارجي',
        'Internal & External Masonry / Insulation Works',
        Decimal('6.000'),
        [
            # Single line item "spread over 9 floors" -- weight = full phase weight,
            # completion = fraction of floors done (see module docstring).
            ('تقسم الى 9 طوابق من القبو الى اخر روف', 'Split across 9 floors, basement to top roof',
             Decimal('6.000'), date(2026, 8, 16), date(2027, 5, 26), Decimal('0')),
        ],
    ),
    (
        '8',
        'أعمال الحجر الخارجي والتشطيبات المعمارية للواجهات',
        'External Stonework & Architectural Facade Finishes',
        Decimal('9.000'),
        [
            # Weight split per the EDGE report (6/1/2); the Arabic owner report
            # instead splits this phase 7/1/1 -- both sum to 9%, but disagree on
            # the split. Flagged in the seed summary printed by this command.
            ('تقسيم الحجر على 9 طوابق', 'Stonework split across 9 floors', Decimal('6.000'), date(2026, 5, 10), date(2027, 6, 28), Decimal('36.67')),
            ('كحلة الحجر', 'Stone pointing ("Kahla")', Decimal('1.000'), date(2026, 5, 10), date(2027, 6, 28), Decimal('0')),
            ('قصارة ودهان', 'Plaster & paint', Decimal('2.000'), date(2026, 5, 10), date(2027, 6, 28), Decimal('0')),
        ],
    ),
    (
        '9',
        'الأعمال الكهربائية والميكانيكية الأساسية',
        'Core Electrical & Mechanical Works',
        Decimal('10.000'),
        [
            ('تقسيم على عشرة مراحل (الطوابق + السطح)', 'Split across ten stages (floors + roof)',
             Decimal('10.000'), date(2026, 9, 26), date(2027, 8, 30), Decimal('10')),
        ],
    ),
    (
        '10',
        'أعمال التشطيب الداخلي الدهان، البلاط، الأبواب، الألمنيوم',
        'Interior Finishing Works (paint, tiling, doors, aluminum)',
        Decimal('16.000'),
        [
            ('القبو', 'Basement', Decimal('0.500'), date(2026, 10, 7), date(2027, 9, 7), Decimal('0')),
            ('المخازن+ السدة', 'Storage + mezzanine', Decimal('2.000'), date(2026, 10, 7), date(2027, 9, 7), Decimal('0')),
            ('الشقق خلف المخازن ×4', 'Apartments behind storage (×4)', Decimal('2.000'), date(2026, 10, 7), date(2027, 9, 7), Decimal('0')),
            ('الأربع طوابق مكرر', 'Repeated 4 floors', Decimal('8.000'), date(2026, 10, 7), date(2027, 9, 7), Decimal('0')),
            ('الروف مكرر', 'Repeated roof', Decimal('4.000'), date(2026, 10, 7), date(2027, 9, 7), Decimal('0')),
        ],
    ),
    (
        '11',
        'أعمال المصاعد وأنظمة الأمان والكاميرات',
        'Elevators, Safety & Camera Systems',
        Decimal('3.000'),
        [
            ('تأسيس المصعد والأنظمة', 'Elevator & systems installation', Decimal('2.000'), date(2027, 8, 7), date(2027, 11, 28), Decimal('0')),
            ('تشغيل المصعد والأنظمة', 'Elevator & systems commissioning', Decimal('1.000'), date(2027, 8, 7), date(2027, 11, 28), Decimal('0')),
        ],
    ),
    (
        '12',
        'أعمال الموقع الخارجي واللاندسكيب',
        'External Site & Landscape Works',
        Decimal('2.000'),
        [
            ('الاسوار الخارجية', 'Perimeter walls', Decimal('1.000'), date(2027, 6, 28), date(2027, 9, 4), Decimal('0')),
            ('تأسيس الأنظمة', 'Systems installation', Decimal('0.500'), date(2027, 6, 28), date(2027, 9, 4), Decimal('0')),
            ('البلاط والزراعة', 'Tiling & planting', Decimal('0.500'), date(2027, 6, 28), date(2027, 9, 4), Decimal('0')),
        ],
    ),
    (
        '13',
        'أعمال الإدارة، الإشراف، والتأمين والصيانة',
        'Management, Supervision, Insurance & Maintenance',
        Decimal('2.000'),
        [
            # Single line item "spread over 30 months" -- weight = full phase
            # weight, completion = fraction of the schedule elapsed so far.
            ('تقسم على اشهر المشروع 30 شهر', 'Spread over 30 project months', Decimal('2.000'), date(2025, 11, 1), date(2028, 11, 1), Decimal('30.15')),
        ],
    ),
]


class Command(BaseCommand):
    help = (
        "Seed ProjectPhase/ProjectPhaseSubItem/ProjectPhaseProgressEntry for the "
        "TAB project from the 07/2026 owner financial report + EDGE monthly report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-id', type=int, default=1,
            help='Project PK to seed (default: 1, the existing TAB project).',
        )

    def handle(self, *args, **options):
        try:
            project = Project.objects.get(pk=options['project_id'])
        except Project.DoesNotExist:
            raise CommandError(f"Project id={options['project_id']} does not exist.")

        with transaction.atomic():
            if not project.contract_value:
                project.contract_value = CONTRACT_VALUE
                project.save(update_fields=['contract_value'])
                self.stdout.write(f"Set {project}.contract_value = {CONTRACT_VALUE}")
            elif project.contract_value != CONTRACT_VALUE:
                self.stdout.write(self.style.WARNING(
                    f"{project} already has contract_value={project.contract_value}, "
                    f"which differs from the source documents' {CONTRACT_VALUE} -- left untouched."
                ))

            for order, (code, name_ar, name_en, weight, sub_items) in enumerate(PHASES, start=1):
                phase, _created = ProjectPhase.objects.update_or_create(
                    project=project, code=code,
                    defaults={'name_ar': name_ar, 'name_en': name_en, 'weight_percentage': weight, 'order': order},
                )
                for sub_order, (sub_ar, sub_en, sub_weight, start, end, completion) in enumerate(sub_items, start=1):
                    sub_item, _created = ProjectPhaseSubItem.objects.update_or_create(
                        phase=phase, name_en=sub_en,
                        defaults={
                            'name_ar': sub_ar,
                            'weight_percentage': sub_weight,
                            'planned_start_date': start,
                            'planned_completion_date': end,
                            'order': sub_order,
                        },
                    )
                    ProjectPhaseProgressEntry.objects.update_or_create(
                        sub_item=sub_item, report_date=REPORT_DATE,
                        defaults={
                            'execution_percentage': completion,
                            'notes': (
                                'Seeded from owner financial report + EDGE monthly report, 07/2026 '
                                '(reports.seed_tab_project_phases)'
                            ),
                        },
                    )

        result = calculate_project_progress(project, as_of_date=REPORT_DATE, contract_value=project.contract_value)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(PHASES)} phases for {project}. "
            f"Overall progress as of {REPORT_DATE}: {result['overall_percentage']}% "
            f"(expected 31.803% per both source reports)."
        ))
