"""The demo drawings: real PDFs, analyses that match them, a project that becomes ready for work, and a clean way back."""
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_assistant import edge, takeoff
from ai_assistant.models import AIRun
from projects import readiness
from projects.models import Project
from reports.progress_models import ProjectPhase

from . import demo
from .models import Blueprint, BlueprintRevision

User = get_user_model()


def make_demo_project():
    """DEMOCC with the same priced BOQ codes seed_costing_demo creates (without needing the item catalogue)."""
    project = Project.objects.create(name="[DEMO] Cost Control Tower", project_symbol="DEMOCC", contract_number="DEMO-CC-1", client_name="C",
                                     start_date=date(2026, 1, 1), status="active")
    lines = [("1", "1.1", "m3", 300, 40, 55), ("1", "1.2", "m3", 120, 420, 560), ("2", "2.1", "m3", 250, 480, 640), ("2", "2.2", "m2", 800, 55, 75),
             ("3", "3.1", "m2", 600, 75, 105), ("3", "3.2", "m2", 1200, 14, 22)]
    phases = {}
    for phase_code, code, unit, qty, budget, contract in lines:
        if phase_code not in phases:
            phases[phase_code] = ProjectPhase.objects.create(project=project, code=phase_code, name_ar=phase_code, weight_percentage=0, order=int(phase_code))
        phase = phases[phase_code]
        phase.sub_items.create(code=code, name_ar=code, weight_percentage=0, unit=unit, quantity=Decimal(qty),
                               budget_unit_price=Decimal(budget), contract_unit_price=Decimal(contract))
    for code, unit, qty, budget, contract in [("4", "No.", 80, 150, 210), ("5", "m2", 300, 90, 130)]:
        phase = ProjectPhase.objects.create(project=project, code=code, name_ar=code, weight_percentage=0, order=int(code), unit=unit,
                                            quantity=Decimal(qty), budget_unit_price=Decimal(budget), contract_unit_price=Decimal(contract))
        phase.sync_whole_item()
    return project


class DemoDrawingsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls.media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", role="admin", is_superuser=True)
        self.project = make_demo_project()

    def seed(self):
        out = StringIO()
        call_command("seed_drawings_demo", stdout=out)
        return out.getvalue()

    def files_on_disk(self):
        return [os.path.join(root, f) for root, _, names in os.walk(self.media) for f in names]

    def test_seed_counts_and_states(self):
        message = self.seed()
        self.assertIn("4 insurance policies, 5 tender documents, 8 drawings (9 revisions) and 9 AI analyses", message)
        statuses = sorted(BlueprintRevision.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["approved"] * 4 + ["pending"] * 3 + ["rejected", "superseded"])
        self.assertEqual({p.state for p in self.project.insurances.all()}, {"valid", "expiring", "expired"})
        self.assertIn("Fixture wattages", BlueprintRevision.objects.get(status="rejected").rejection_reason)

    def test_drawings_are_real_pdfs_and_match_their_analyses(self):
        import pymupdf

        self.seed()
        for revision in BlueprintRevision.objects.exclude(blueprint__drawing_number="C-01"):
            data = revision.file.read()
            revision.file.close()
            self.assertTrue(data.startswith(b"%PDF"), revision)
            text = " ".join(page.get_text() for page in pymupdf.open(stream=data, filetype="pdf"))
            sheet = next(s for s in demo.SHEETS if s["number"] == revision.blueprint.drawing_number)
            for row in sheet["schedule"]:
                self.assertIn(row[1].split(",")[0][:20], text.replace("\n", " "), f"{sheet['number']} lists {row[1]}")
            for note in sheet["notes"]:
                self.assertIn(note[:25], text.replace("\n", " "), f"{sheet['number']} states: {note}")
        cad = BlueprintRevision.objects.get(blueprint__drawing_number="C-01")
        self.assertTrue(cad.file.name.endswith(".dwg"))

    def test_the_project_becomes_ready_for_work(self):
        self.assertFalse(readiness.check(self.project).ok, "before: no insurance")
        self.seed()
        self.assertTrue(readiness.check(self.project).ok, readiness.check(self.project).summary())

    def test_analyses_tie_to_the_boq(self):
        self.seed()
        run = AIRun.objects.get(source_label__startswith="Drawing A-01 rev A")
        linked = takeoff.link_to_boq(self.project, run.result)
        by_code = {line["code"]: line for line in linked["lines"]}
        self.assertEqual((by_code["3.1"]["drawing_quantity"], by_code["3.1"]["difference"]), (Decimal("568"), Decimal("-32.000")))
        self.assertEqual(by_code["3.2"]["difference"], Decimal("120.000"))
        self.assertEqual(linked["totals"]["unmatched"], 2, "the ceiling and the membrane have no BOQ line")
        electrical = AIRun.objects.get(source_label__startswith="Drawing E-01")
        self.assertEqual(takeoff.link_to_boq(self.project, electrical.result)["lines"][0]["difference"], Decimal("16.000"))

    def test_the_green_summary_has_both_found_and_missing_points(self):
        self.seed()
        data = edge.project_edge_data(self.project)
        self.assertEqual(len(data["documents"]), 8, "the failed CAD analysis and the superseded revision are not part of it")
        self.assertGreater(data["found"], 25)
        missing = {m["id"] for m in data["missing"]}
        self.assertTrue({"floor_insulation", "greywater_recycling", "water_metering", "natural_ventilation", "heating_system"} <= missing)
        found = {p["id"] for d in data["domains"] for p in d["points"] if p["entries"]}
        self.assertTrue({"window_performance", "shower_heads", "wc_flush", "renewable_energy"} <= found, "including the ones only the specification states")

    def test_the_cad_drawing_shows_the_failed_state(self):
        self.seed()
        run = AIRun.objects.get(source_label__startswith="Drawing C-01")
        self.assertEqual(run.status, AIRun.FAILED)
        self.assertIn("Export the drawing to PDF", run.error)

    def test_the_pages_show_the_demo(self):
        self.seed()
        self.client.force_login(self.admin)
        drawings = self.client.get(reverse("blueprints:project_drawings", args=[self.project.pk]))
        for text in ("A-01", "Approved for construction", "Awaiting approval", "Rejected", "Superseded", "AI analysis", "AI failed"):
            self.assertContains(drawings, text)
        run = AIRun.objects.get(source_label__startswith="Drawing A-01 rev A")
        page = self.client.get(reverse("ai_assistant:run_detail", args=[run.pk]))
        self.assertContains(page, "Ceramic floor tiles 60x60")
        self.assertContains(page, "Compared with the BOQ")
        self.assertContains(self.client.get(reverse("ai_assistant:project_edge", args=[self.project.pk])), "Still missing")
        self.assertContains(self.client.get(reverse("projects:workflow", args=[self.project.pk])), "Expired")

    def test_seeding_twice_changes_nothing_and_clear_removes_everything_including_files(self):
        before = set(self.files_on_disk())      # the media folder is shared by the tests of this class
        self.seed()
        made = set(self.files_on_disk()) - before
        counts = (Blueprint.objects.count(), BlueprintRevision.objects.count(), AIRun.objects.count(), self.project.insurances.count(), len(made))
        self.assertIn("already present", self.seed())
        self.assertEqual(counts, (Blueprint.objects.count(), BlueprintRevision.objects.count(), AIRun.objects.count(),
                                  self.project.insurances.count(), len(set(self.files_on_disk()) - before)))
        self.assertEqual(len(made), 9 + 4 + 5, "9 drawing files, 4 insurance certificates, 5 tender documents")

        call_command("seed_drawings_demo", clear=True, stdout=StringIO())
        self.assertEqual((Blueprint.objects.count(), BlueprintRevision.objects.count(), AIRun.objects.count(),
                          self.project.insurances.count(), self.project.tender_documents.count()), (0, 0, 0, 0, 0))
        self.assertEqual(set(self.files_on_disk()), before)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists(), "the demo project itself stays")

    def test_real_records_next_to_the_demo_survive_a_clear(self):
        self.project.insurances.create(policy_type="car", insurer="Real", policy_number="REAL-1", start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
                                       document="insurance/real.pdf")
        self.seed()
        call_command("seed_drawings_demo", clear=True, stdout=StringIO())
        self.assertEqual(list(self.project.insurances.values_list("policy_number", flat=True)), ["REAL-1"])
