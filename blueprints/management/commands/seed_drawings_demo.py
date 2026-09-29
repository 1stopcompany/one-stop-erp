"""
Seed (or with --clear, remove) demo insurance, tender documents, engineering drawings and AI analyses for the demo project
"[DEMO] Cost Control Tower" (symbol DEMOCC, made by seed_costing_demo), so the start-up workflow, Drawings, AI Assistant and
green-building (EDGE) pages have realistic content. The drawings are real PDFs; nothing is sent to any AI.

Usage:
    python manage.py seed_drawings_demo            # add (skips if already seeded)
    python manage.py seed_drawings_demo --clear    # remove what this command added
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from blueprints import demo
from projects.models import Project

SYMBOL = "DEMOCC"


class Command(BaseCommand):
    help = "Seed (or with --clear, remove) demo drawings, insurance and tender documents for the DEMOCC demo project"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove the demo drawings, insurance, tender documents and analyses")

    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=SYMBOL).first()

        if options["clear"]:
            with transaction.atomic():
                demo.clear(project)
            self.stdout.write(self.style.SUCCESS("Removed the demo drawings, insurance, tender documents and analyses."))
            return

        if project is None:
            self.stdout.write("The demo project doesn't exist yet: creating it with seed_costing_demo first.")
            call_command("seed_costing_demo", stdout=self.stdout, stderr=self.stderr)
            project = Project.objects.filter(project_symbol=SYMBOL).first()
            if project is None:
                self.stderr.write(self.style.ERROR("Couldn't create the demo project (see the message above)."))
                return
        if demo.is_seeded(project):
            self.stdout.write("Demo drawings already present -- nothing to do (use --clear to reset).")
            return

        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).order_by("id").first()
        reviewer = User.objects.filter(role="project_manager").order_by("id").first() or admin
        with transaction.atomic():
            counts = demo.seed(project, admin, reviewer)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{project.name}': {counts['insurance']} insurance policies, {counts['tender_documents']} tender documents, "
            f"{counts['drawings']} drawings ({counts['revisions']} revisions) and {counts['analyses']} AI analyses. "
            f"Open Workflow, Blueprints > {project.name}, and AI Assistant > Green building. Remove with: seed_drawings_demo --clear"
        ))
