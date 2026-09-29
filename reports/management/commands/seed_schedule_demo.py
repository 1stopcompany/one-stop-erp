"""
Seed (or with --clear, remove) a Primavera-style demo schedule for the demo project "[DEMO] Cost Control Tower" (DEMOCC, made by
seed_costing_demo): a three-level WBS, milestones, every link type with lags, the critical path, float, a baseline the current
schedule has slipped against, and progress up to today.

Usage:
    python manage.py seed_schedule_demo            # add, or refresh the dates and progress relative to today
    python manage.py seed_schedule_demo --clear    # remove the demo schedule
"""
from django.core.management.base import BaseCommand

from projects.models import Project
from reports import schedule_demo

SYMBOL = "DEMOCC"


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) a demo project schedule for the DEMOCC demo project"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo schedule")

    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=SYMBOL).first()
        if project is None:
            self.stderr.write(self.style.ERROR("The demo project doesn't exist yet: run seed_costing_demo first."))
            return
        if options["clear"]:
            self.stdout.write(self.style.SUCCESS(f"Removed {schedule_demo.clear(project)} demo schedule rows."))
            return
        count = schedule_demo.seed(project)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {count} schedule rows for '{project.name}'. Open the project > Schedule. Remove with: seed_schedule_demo --clear"
        ))
