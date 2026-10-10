"""
Link a project's BOQ phases to its MS Project plan tasks, and keep the plan's progress in step with the BOQ progress.

    python manage.py plan_link link TAB                    # preview of the links
    python manage.py plan_link link TAB --apply            # write them (replaces this project's links)
    python manage.py plan_link sync TAB [--date 2026-09-30] [--phases 2,3,4,5,6] [--apply]   # plan tasks' % complete from the BOQ progress
    python manage.py plan_link report TAB [--date 2026-09-30]           # plan vs actual per phase, printed

The rules below are written for the TAB project (the plan's task IDs are the row numbers of the MS Project file). They only create
rows in PhaseScheduleLink; the BOQ itself, the plan itself (except the % complete written by `sync --apply`) and the owner's
report are not touched.
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import ProjectPhase
from reports.schedule_models import PhaseScheduleLink, ScheduleTask
from reports.services.plan_vs_actual import WHOLE_PROJECT, plan_vs_actual, sync_task_progress

PARKING = range(121, 130)       # "Parking Finishing Works and landscaping" group
FINISHING = range(20, 120)      # "Finishing Works" group (floor by floor)


def tab_rules(tasks):
    """{BOQ phase code: [plan task IDs]} for the TAB plan; `tasks` = {task ID: ScheduleTask}."""
    def leaves(ids):
        return [i for i in ids if i in tasks and not tasks[i].is_summary]

    def named(ids, prefix):
        return [i for i in leaves(ids) if tasks[i].name.strip().lower().startswith(prefix)]

    blocks = named(FINISHING, 'block works')
    meps = named(FINISHING, 'mep')
    other_finishing = [i for i in leaves(FINISHING) if i not in blocks and i not in meps]
    return {
        '2': [1, 2],                         # site preparation, excavation
        '3': [4, 5],                         # basement / septic walls and slabs, concrete below ground slab
        '4': [6, 7],                         # basement floor, ground floor
        '5': [8, 9, 10, 11],                 # first to fourth floor
        '6': [12, 13],                       # roof 1 and roof 2
        '7': blocks + [14, 15, 16],          # block works of every floor, parapet insulation, roof screed and insulation
        '8': [17, 18],                       # external plaster, pointing
        '9': meps + [132, 134, 135],         # MEP fixes of every floor, main DBs, data / LV, SELCO
        '10': other_finishing,               # plaster, tiles, aluminium, painting, doors... of every floor
        '11': [131],                         # elevator installation
        '12': list(PARKING),                 # parking finishing works and landscaping
        '13': [WHOLE_PROJECT],               # management & supervision: the whole job
    }


class Command(BaseCommand):
    help = "Link BOQ phases to MS Project plan tasks; sync plan progress; print plan vs actual."

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['link', 'sync', 'report'])
        parser.add_argument('project', help='Project symbol, e.g. TAB')
        parser.add_argument('--date', help='As-of date (YYYY-MM-DD); default today')
        parser.add_argument('--phases', default='2,3,4,5,6', help="sync: the BOQ phase codes whose plan tasks get their %% complete (default: the structure phases, whose tasks follow one another); 'all' for every linked phase")
        parser.add_argument('--apply', action='store_true', help='Write the changes (without it: preview)')

    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=options['project']).first()
        if not project:
            raise CommandError(f"No project with the symbol {options['project']}.")
        as_of = datetime.date.fromisoformat(options['date']) if options['date'] else datetime.date.today()
        self.phases = None if options['phases'] == 'all' else {c.strip() for c in options['phases'].split(',') if c.strip()}
        return getattr(self, f"do_{options['action']}")(project, as_of, options['apply'])

    # ------------------------------------------------------------------ link
    def do_link(self, project, as_of, apply):
        tasks = {t.source_task_id: t for t in ScheduleTask.objects.filter(project=project)}
        if not tasks:
            raise CommandError(f'{project.project_symbol} has no schedule tasks here; import the plan first.')
        phases = {p.code: p for p in ProjectPhase.objects.filter(project=project)}
        rules = tab_rules(tasks)
        missing = [code for code in rules if code not in phases]
        if missing:
            raise CommandError(f'This database has no BOQ phase with code(s) {missing}; nothing was changed.')
        rows = []
        for code, ids in rules.items():
            uids = sorted({WHOLE_PROJECT if i == WHOLE_PROJECT else tasks[i].unique_id for i in ids if i == WHOLE_PROJECT or i in tasks})
            rows.append((phases[code], ids, uids))
            self.stdout.write(f'  phase {code}: {len(uids)} plan task(s)')
        unlinked = sorted(c for c in phases if c not in rules)
        self.stdout.write(f"{len(rows)} phases linked; phases without a plan link (not compared): {unlinked or 'none'}.")
        if not apply:
            self.stdout.write(self.style.WARNING('Preview only. Run again with --apply to write the links.'))
            return
        with transaction.atomic():
            PhaseScheduleLink.objects.filter(phase__project=project).delete()
            PhaseScheduleLink.objects.bulk_create([PhaseScheduleLink(phase=phase, task_unique_id=uid) for phase, _, uids in rows for uid in uids])
        self.stdout.write(self.style.SUCCESS(f'{sum(len(u) for _, _, u in rows)} links written.'))

    # ------------------------------------------------------------------ sync
    def do_sync(self, project, as_of, apply):
        changes = sync_task_progress(project, as_of, apply=apply, phase_codes=self.phases)
        for task, old, new in changes[:60]:
            self.stdout.write(f'  #{task.source_task_id} {task.name[:48]}: {old}% -> {new}%')
        if len(changes) > 60:
            self.stdout.write(f'  ... and {len(changes) - 60} more')
        self.stdout.write(f'{len(changes)} task(s) ' + ('updated.' if apply else 'would change. Preview only; add --apply to write it.'))

    # ------------------------------------------------------------------ report
    def do_report(self, project, as_of, apply):
        result = plan_vs_actual(project, as_of)
        self.stdout.write(f"Plan vs actual as of {as_of}: planned {result['planned_total']:.2f}%  actual {result['actual_total']:.2f}%  "
                          f"variance {result['variance_total']:+.2f} points ({result['status_total']})")
        for row in result['rows']:
            self.stdout.write(f"  {row['phase'].code:>3}  weight {row['weight']:>6.2f}  planned {row['planned']:>6.1f}  actual {row['actual']:>6.1f}  "
                              f"{row['variance']:+7.1f}  {row['status']}")
