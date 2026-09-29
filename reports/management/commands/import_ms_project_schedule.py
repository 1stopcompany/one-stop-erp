"""
Import a project's CPM schedule from a Microsoft Project (.mpp) file into
ScheduleTask, for the "Critical Path" section of the internal monthly
report. See reports.schedule_models.ScheduleTask for why this doesn't try
to recompute the critical path itself -- everything (Start/Finish/
TotalSlack/Critical) is read directly from what MS Project already
computed.

Two input modes:
  --mpp <path>   Opens the file in Microsoft Project via COM automation
                 (requires MS Project installed on THIS machine) and
                 reads the Tasks collection directly. Nothing is saved
                 back to the .mpp file. NOTE: on this machine, launching
                 MS Project via COM from Python (win32com) fails with
                 "Server execution failed" even though MS Project and
                 pywin32 are both installed -- PowerShell's COM support
                 doesn't have this problem, so --json (below) is the
                 verified-working path here.
  --json <path>  Loads a pre-extracted task list. Produce it with
                 reports/management/scripts/extract_mpp_tasks.ps1 (same
                 field names/shape as the --mpp path would produce):

                     powershell -ExecutionPolicy Bypass -File reports\\management\\scripts\\extract_mpp_tasks.ps1 `
                         -MppPath "C:\\path\\to\\schedule.mpp" -OutJson "C:\\path\\to\\tasks.json"

Usage:
    python manage.py import_ms_project_schedule --project TAB --json "C:\\path\\to\\tasks.json"
"""

import json
import os
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.schedule_models import ScheduleTask

MINUTES_PER_DAY = 480  # MS Project's default 8-hour working day


def _extract_via_com(mpp_path):
    try:
        import win32com.client
    except ImportError:
        raise CommandError(
            'pywin32 is not installed (pip install pywin32), or this is not '
            'Windows -- COM automation requires Microsoft Project installed '
            'on this machine. Use --json with a pre-extracted dump instead.'
        )

    app = win32com.client.Dispatch('MSProject.Application')
    app.Visible = False
    app.DisplayAlerts = False
    try:
        app.FileOpen(mpp_path)
        proj = app.ActiveProject
        rows = []
        for t in proj.Tasks:
            if t is None:
                continue
            rows.append({
                'ID': t.ID,
                'UniqueID': t.UniqueID,
                'Name': t.Name,
                'OutlineLevel': t.OutlineLevel,
                'Summary': bool(t.Summary),
                'Milestone': bool(t.Milestone),
                'Start': t.Start.strftime('%Y-%m-%d') if t.Start else None,
                'Finish': t.Finish.strftime('%Y-%m-%d') if t.Finish else None,
                'Duration': t.Duration,
                'DurationText': t.DurationText,
                'PercentComplete': t.PercentComplete,
                'TotalSlack': t.TotalSlack,
                'Critical': bool(t.Critical),
                'Predecessors': t.Predecessors or '',
                'ResourceNames': t.ResourceNames or '',
            })
        try:
            proj.Close(0)  # pjDoNotSave
        except Exception:
            pass
        return rows
    finally:
        try:
            app.Quit()
        except Exception:
            pass


class Command(BaseCommand):
    help = "Import a project's CPM schedule from an MS Project (.mpp) file into ScheduleTask"

    def add_arguments(self, parser):
        parser.add_argument('--project', required=True, help='Project symbol (e.g. TAB)')
        parser.add_argument('--mpp', help='Path to a .mpp file (uses MS Project COM automation)')
        parser.add_argument('--json', help='Path to a pre-extracted task list JSON')

    def handle(self, *args, **options):
        if not options['mpp'] and not options['json']:
            raise CommandError('Pass either --mpp or --json')
        if options['mpp'] and options['json']:
            raise CommandError('Pass only one of --mpp / --json')

        try:
            project = Project.objects.get(project_symbol=options['project'])
        except Project.DoesNotExist:
            raise CommandError(f"No project with symbol '{options['project']}'")

        if options['mpp']:
            mpp_path = options['mpp']
            if not os.path.isfile(mpp_path):
                raise CommandError(f'File not found: {mpp_path}')
            self.stdout.write('Opening MS Project via COM automation (this may take a moment)...')
            rows = _extract_via_com(mpp_path)
            source_name = os.path.basename(mpp_path)
        else:
            json_path = options['json']
            if not os.path.isfile(json_path):
                raise CommandError(f'File not found: {json_path}')
            with open(json_path, encoding='utf-8-sig') as f:
                rows = json.load(f)
            source_name = os.path.basename(json_path)

        if not rows:
            raise CommandError('No tasks found in the source file')

        with transaction.atomic():
            deleted, _ = ScheduleTask.objects.filter(project=project).delete()
            created = []
            for r in rows:
                duration_days = (Decimal(str(r['Duration'])) / MINUTES_PER_DAY) if r.get('Duration') is not None else None
                total_slack_days = (Decimal(str(r['TotalSlack'])) / MINUTES_PER_DAY) if r.get('TotalSlack') is not None else None
                created.append(ScheduleTask(
                    project=project,
                    source_task_id=r['ID'],
                    unique_id=r['UniqueID'],
                    name=r['Name'] or '',
                    outline_level=r.get('OutlineLevel') or 1,
                    is_summary=bool(r.get('Summary')),
                    is_milestone=bool(r.get('Milestone')),
                    start_date=r.get('Start') or None,
                    finish_date=r.get('Finish') or None,
                    duration_days=duration_days,
                    duration_text=r.get('DurationText') or '',
                    percent_complete=Decimal(str(r.get('PercentComplete') or 0)),
                    total_slack_days=total_slack_days,
                    is_critical=bool(r.get('Critical')),
                    predecessors=(r.get('Predecessors') or '')[:255],
                    resource_names=(r.get('ResourceNames') or '')[:255],
                    source_file_name=source_name,
                ))
            ScheduleTask.objects.bulk_create(created)

        critical_count = sum(1 for r in rows if r.get('Critical'))
        finish_dates = [r['Finish'] for r in rows if r.get('Finish')]
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(created)} tasks for {project.project_symbol} "
            f"(replaced {deleted} previous rows). {critical_count} on the critical path. "
            f"Project finish: {max(finish_dates) if finish_dates else 'n/a'}."
        ))
