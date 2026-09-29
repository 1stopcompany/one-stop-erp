"""
Seed (or with --clear, remove) demo daily site reports for the demo project "[DEMO] Cost Control Tower" (symbol DEMOCC,
made by seed_costing_demo): six reports covering every stage of the draft -> submitted -> engineering_approved ->
approved / rejected workflow, each with every section the Daily Report page shows.

Usage:
    python manage.py seed_daily_report_demo            # add (skips if already seeded)
    python manage.py seed_daily_report_demo --clear    # remove what this command added
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from reports import daily_report_demo as demo
from reports.master_data_models import LaborClassification
from projects.models import Project

SYMBOL = "DEMOCC"


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) demo daily site reports for the DEMOCC demo project"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo daily reports and everything logged in them")

    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=SYMBOL).first()

        if options["clear"]:
            with transaction.atomic():
                demo.clear(project)
            self.stdout.write(self.style.SUCCESS("Removed the demo daily reports."))
            return

        if project is None:
            self.stdout.write("The demo project doesn't exist yet: creating it with seed_costing_demo first.")
            call_command("seed_costing_demo", stdout=self.stdout, stderr=self.stderr)
            project = Project.objects.filter(project_symbol=SYMBOL).first()
            if project is None:
                self.stderr.write(self.style.ERROR("Couldn't create the demo project (see the message above)."))
                return
        if demo.is_seeded(project):
            self.stdout.write("Demo daily reports already present -- nothing to do (use --clear to reset).")
            return
        if not LaborClassification.objects.exists():
            self.stdout.write("Loading labor classifications first (load_master_data)...")
            call_command("load_master_data", stdout=self.stdout, stderr=self.stderr)

        User = get_user_model()
        engineering_manager = User.objects.filter(role="engineering_manager").order_by("id").first()
        general_manager = User.objects.filter(role="general_manager").order_by("id").first()
        if not project.site_engineer:
            self.stderr.write(self.style.ERROR("The demo project has no site engineer assigned -- can't author daily reports."))
            return
        if not engineering_manager or not general_manager:
            self.stderr.write(self.style.ERROR("Need at least one engineering_manager and one general_manager user to seed the review workflow."))
            return

        with transaction.atomic():
            counts = demo.seed(project, engineering_manager, general_manager)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{project.name}': {counts['reports']} daily reports (draft, submitted, engineering_approved, "
            f"approved x2, rejected), {counts['worker_attendance']} worker attendance rows, {counts['activity_progress']} "
            f"BOQ-linked activity progress rows, {counts['site_events']} site events, {counts['attachments']} photos, "
            f"{counts['next_day_plan']} next-day plan items. Open Reports > Daily Reports for {project.name}. "
            f"Remove with: seed_daily_report_demo --clear"
        ))
