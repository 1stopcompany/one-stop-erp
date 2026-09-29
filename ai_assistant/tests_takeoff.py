"""
Materials / quantities / green-building (EDGE) analysis of drawings and specifications, tested with a fake AI: these check what we
send, how the answer is cleaned, how it is tied to the priced BOQ (plain code), the EDGE checklist and coverage, the pages, the
spreadsheet exports, the permissions and the automatic start after an upload. They say nothing about how well a real model reads a drawing.
"""
import json
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from blueprints.models import Blueprint, BlueprintRevision
from projects.models import ProjectTenderDocument
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

from . import edge, ollama, takeoff, triggers
from .models import AIRun
from .review import make_tools
from .tests import Base, fake_client, make_project
from .tests_ollama import FakeOllama, LOCAL, reply

RAW = {
    "drawing_summary": "Ground floor plan with finish and window schedules",
    "items": [
        {"category": "finish", "description": "Ceramic floor tiles 60x60", "specification": "Grade PEI 4", "location": "Living room",
         "unit": "m2", "quantity": 40, "quantity_basis": "printed", "boq_code": "3.1", "source_page": 1, "confidence": "high", "notes": ""},
        {"category": "finish", "description": "Ceramic floor tiles 60x60", "specification": "Grade PEI 4", "location": "Kitchen",
         "unit": "M²", "quantity": 12.5, "quantity_basis": "printed", "boq_code": "3.1", "source_page": 1, "confidence": "high", "notes": ""},
        {"category": "opening", "description": "Window W1 aluminium double glazed", "specification": "1.2 x 1.5 m", "location": "Bedrooms",
         "unit": "no.", "quantity": 6, "quantity_basis": "printed", "boq_code": "4.2", "source_page": 2, "confidence": "medium", "notes": ""},
        {"category": "material", "description": "Waterproofing membrane", "specification": "", "location": "Roof",
         "unit": None, "quantity": None, "quantity_basis": "not_stated", "boq_code": "9.9", "source_page": None, "confidence": "low", "notes": "quantity not printed"},
        {"category": "material", "description": "Paint", "specification": "", "location": "", "unit": "m", "quantity": 100, "quantity_basis": "printed",
         "boq_code": "3.1", "source_page": 3, "confidence": "high", "notes": ""},
    ],
    "green_data": [
        {"point": "glazing_type", "value": "Double glazing 6-12-6 mm, low-E", "number": None, "unit": None, "location": "All windows",
         "source_page": 2, "confidence": "high", "notes": ""},
        {"point": "wc_flush", "value": "Dual flush 3/6 L", "number": 6, "unit": "L", "location": "Bathrooms", "source_page": 4,
         "confidence": "medium", "notes": ""},
    ],
    "issues": [{"severity": "warning", "message": "Scale missing on sheet 3"}],
}


def boq(project):
    """Tiles (3.1, m2, qty 50, cost 20), windows (4.2, no, qty 5, cost 300); two lines share the code 7.7."""
    phase = ProjectPhase.objects.create(project=project, code="3", name_ar="تشطيبات", weight_percentage=0, order=1)
    tiles = ProjectPhaseSubItem.objects.create(phase=phase, code="3.1", name_ar="بلاط", weight_percentage=0, unit="m2",
                                               quantity=Decimal("50"), budget_unit_price=Decimal("20"), contract_unit_price=Decimal("30"))
    windows = ProjectPhaseSubItem.objects.create(phase=phase, code="4.2", name_ar="شبابيك", weight_percentage=0, unit="no",
                                                 quantity=Decimal("5"), budget_unit_price=Decimal("300"), contract_unit_price=Decimal("400"))
    for n in (1, 2):
        ProjectPhaseSubItem.objects.create(phase=phase, code="7.7", name_ar=f"dup {n}", weight_percentage=0, unit="m2",
                                           quantity=Decimal("1"), budget_unit_price=Decimal("1"), contract_unit_price=Decimal("1"))
    return tiles, windows


class CleaningTests(SimpleTestCase):
    def test_takeoff_is_made_safe(self):
        cleaned = takeoff.clean_takeoff({
            "items": [
                {"category": "nonsense", "description": "  Bricks ", "quantity": -3, "unit": "no", "confidence": "??"},
                {"category": "material", "description": "", "quantity": 5},
                "junk",
                {"category": "material", "description": "Sand", "quantity": "12.5", "quantity_basis": "not_stated", "source_page": "x"},
            ],
            "green_data": [{"point": "made_up_point", "value": "x"}, {"point": "wc_flush", "value": ""}, {"point": "wc_flush", "value": "6 L", "number": -1}],
            "issues": [{"severity": "bogus", "message": "odd"}, {"message": ""}],
        })
        bricks, sand = cleaned["items"]
        self.assertEqual((bricks["category"], bricks["description"], bricks["quantity"], bricks["quantity_basis"], bricks["confidence"]),
                         ("other", "Bricks", None, "not_stated", "medium"))
        self.assertEqual((sand["quantity"], sand["quantity_basis"], sand["source_page"]), ("12.5", "printed", None), "the basis follows the quantity")
        self.assertEqual([i["key"] for i in cleaned["items"]], ["t0", "t3"])
        self.assertEqual([(g["point"], g["number"]) for g in cleaned["green_data"]], [("wc_flush", None)])
        self.assertEqual(cleaned["issues"], [{"severity": "info", "message": "odd"}])
        self.assertEqual(cleaned["totals"], {"items": 2, "with_quantity": 1, "green_points": 1})

    def test_units_are_compared_in_a_normal_form(self):
        for a, b in [("m²", "m2"), ("M2", "m²"), ("No.", "nos"), ("L.S.", "lump sum"), ("م²", "m2"), ("متر مكعب", "m3"), (" m3 ", "cum")]:
            self.assertEqual(takeoff.unit_key(a), takeoff.unit_key(b), (a, b))
        self.assertNotEqual(takeoff.unit_key("m"), takeoff.unit_key("m2"))


class EdgeChecklistTests(SimpleTestCase):
    def test_the_checklist_is_consistent(self):
        self.assertEqual(len(edge.POINT_IDS), len(set(edge.POINT_IDS)))
        self.assertEqual(set(edge.GREEN_ITEM_SCHEMA["properties"]["point"]["enum"]), set(edge.POINT_IDS))
        self.assertEqual({p["domain"] for p in edge.POINT_BY_ID.values()}, {edge.ENERGY, edge.WATER, edge.MATERIALS})
        for pid, meta in edge.POINT_BY_ID.items():
            self.assertIn(pid, edge.prompt_section())
            self.assertIn(pid, takeoff.SYSTEM_PROMPT)

    def test_coverage_counts_found_and_missing(self):
        found = edge.clean_green([{"point": "wc_flush", "value": "6 L"}, {"point": "wc_flush", "value": "4.5 L"}, {"point": "glazing_type", "value": "double"}])
        cov = edge.coverage(found)
        self.assertEqual((cov["found"], cov["total"]), (2, len(edge.POINT_IDS)))
        self.assertEqual(len(cov["missing"]), len(edge.POINT_IDS) - 2)
        water = next(d for d in cov["domains"] if d["domain"] == edge.WATER)
        self.assertEqual(water["found"], 1)
        self.assertEqual(len(next(p for p in water["points"] if p["id"] == "wc_flush")["entries"]), 2)

    def test_the_prompt_never_claims_an_edge_result(self):
        self.assertIn("Report ONLY what is written", takeoff.SYSTEM_PROMPT)
        self.assertNotIn("EDGE certified", takeoff.SYSTEM_PROMPT)


class LinkToBoqTests(TestCase):
    def setUp(self):
        self.project = make_project("TKO", "TKO")
        self.tiles, self.windows = boq(self.project)

    def link(self):
        return takeoff.link_to_boq(self.project, takeoff.clean_takeoff(RAW))

    def test_matched_rows_are_summed_compared_and_priced_from_the_boq(self):
        linked = self.link()
        by_code = {l["code"]: l for l in linked["lines"]}
        tiles = by_code["3.1"]
        self.assertEqual(tiles["drawing_quantity"], Decimal("52.5"), "40 + 12.5; the 100 m of paint has another unit and is left out")
        self.assertEqual((tiles["boq_quantity"], tiles["difference"], tiles["cost"]), (Decimal("50.000"), Decimal("2.500"), "1050.00"))
        windows = by_code["4.2"]
        self.assertEqual((windows["drawing_quantity"], windows["difference"], windows["cost"]), (Decimal("6"), Decimal("1.000"), "1800.00"))

    def test_totals_and_row_details(self):
        linked = self.link()
        self.assertEqual(linked["totals"], {"items": 5, "with_quantity": 4, "matched": 4, "unmatched": 1, "priced": 3, "estimated_cost": "2850.00"})
        paint = next(r for r in linked["rows"] if r["description"] == "Paint")
        self.assertTrue(paint["unit_mismatch"])
        self.assertIsNone(paint["est_cost"])
        membrane = next(r for r in linked["rows"] if r["description"] == "Waterproofing membrane")
        self.assertIsNone(membrane["boq"], "9.9 isn't a real BOQ code, so it is never linked")

    def test_an_ambiguous_code_is_not_linked(self):
        raw = takeoff.clean_takeoff({"items": [{"category": "material", "description": "x", "unit": "m2", "quantity": 5, "boq_code": "7.7"}]})
        self.assertEqual(takeoff.link_to_boq(self.project, raw)["totals"]["matched"], 0)

    def test_a_phase_priced_as_a_whole_is_matched_by_the_phase_code(self):
        whole = ProjectPhase.objects.create(project=self.project, code="5", name_ar="a", weight_percentage=0, order=2, unit="ls", quantity=Decimal("1"),
                                            budget_unit_price=Decimal("900"), contract_unit_price=Decimal("1200"))
        whole.sync_whole_item()
        raw = takeoff.clean_takeoff({"items": [{"category": "material", "description": "Lump", "unit": "L.S.", "quantity": 1, "boq_code": "5"}]})
        linked = takeoff.link_to_boq(self.project, raw)
        self.assertEqual((linked["totals"]["matched"], linked["totals"]["estimated_cost"]), (1, "900.00"))

    def test_grouping_follows_a_fixed_category_order(self):
        labels = [label for label, _ in takeoff.grouped(self.link()["rows"])]
        self.assertEqual(labels, ["Materials", "Finishes", "Doors, windows & openings"])


@override_settings(AI_RUN_IN_BACKGROUND=False)
class ExtractionTests(Base):
    def make_run(self):
        return AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, created_by=self.admin, source_label="A-01",
                                    source_file=SimpleUploadedFile("plan.csv", b"D1,door,4\n"))

    def test_the_request_carries_the_rules_the_boq_and_the_edge_checklist(self):
        boq(self.project)
        client = fake_client(RAW)
        run = self.make_run()
        result = takeoff.extract_takeoff(run, client=client)
        kwargs = client.messages.stream.call_args.kwargs
        self.assertIn("WRITTEN, NOT MEASURED", kwargs["system"])
        self.assertIn("wc_flush", kwargs["system"])
        self.assertEqual(kwargs["output_config"]["format"]["schema"], takeoff.TAKEOFF_SCHEMA)
        text = json.dumps(kwargs["messages"][0]["content"], ensure_ascii=False)
        self.assertIn("3.1 | بلاط | m2", text)
        self.assertIn("4.2 | شبابيك | no", text)
        self.assertEqual(result["totals"], {"items": 5, "with_quantity": 4, "green_points": 2})
        self.assertEqual((run.input_tokens, run.output_tokens), (1000, 200))

    def test_an_empty_boq_is_said_plainly(self):
        self.assertIn("empty", takeoff.boq_reference(self.project))

    def test_the_runner_dispatches_by_kind(self):
        from . import jobs

        run = self.make_run()
        jobs.execute_run(run.pk, client=fake_client(RAW))
        run.refresh_from_db()
        self.assertEqual((run.status, run.result["totals"]["items"]), (AIRun.DONE, 5))

    @override_settings(**LOCAL)
    def test_local_model_reads_long_documents_in_parts_and_merges(self):
        with override_settings(OLLAMA_NUM_CTX=100):
            part1 = {"drawing_summary": "s", "items": [RAW["items"][0]], "green_data": [RAW["green_data"][0]], "issues": []}
            part2 = {"drawing_summary": "", "items": [RAW["items"][2]], "green_data": [RAW["green_data"][1]], "issues": RAW["issues"]}
            text = "Page one has a long enough schedule of finishes and quantities.\n" * 2
            run = AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, created_by=self.admin,
                                       source_file=SimpleUploadedFile("spec.txt", (text + "x" * 150).encode()))
            fake = FakeOllama(reply(json.dumps(part1), prompt=20), *[reply(json.dumps(part2), prompt=20) for _ in range(12)])
            with mock.patch("ai_assistant.ollama._post", fake):
                result = takeoff.extract_takeoff(run)
        self.assertGreaterEqual(len(fake.calls), 2)
        self.assertEqual({i["description"] for i in result["items"]}, {"Ceramic floor tiles 60x60", "Window W1 aluminium double glazed"})
        self.assertEqual(result["totals"]["green_points"], 2)

    def test_merge_takeoffs(self):
        merged = ollama.merge_takeoffs([{"drawing_summary": "", "items": [1], "green_data": [], "issues": []},
                                        {"drawing_summary": "S", "items": [2], "green_data": [3], "issues": [4]}])
        self.assertEqual(merged, {"drawing_summary": "S", "items": [1, 2], "green_data": [3], "issues": [4]})


@override_settings(AI_RUN_IN_BACKGROUND=False, ANTHROPIC_API_KEY="test-key")
class PageTests(Base):
    def setUp(self):
        boq(self.project)
        self.run = AIRun.objects.create(
            project=self.project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE, created_by=self.pm, source_label="Drawing A-01 rev 0: Ground floor",
            result=takeoff.clean_takeoff(RAW),
        )

    def get(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(f"ai_assistant:{name}", args=args))

    def test_analyze_a_document_in_takeoff_mode(self):
        self.client.force_login(self.pm)
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client(RAW)):
            response = self.client.post(reverse("ai_assistant:analyze", args=[self.project.pk]), {
                "mode": "takeoff", "file": SimpleUploadedFile("spec.csv", b"floor tiles,40,m2\n")})
        run = AIRun.objects.exclude(pk=self.run.pk).get()
        self.assertEqual((run.kind, run.status), (AIRun.DRAWING_TAKEOFF, AIRun.DONE))
        self.assertRedirects(response, reverse("ai_assistant:run_detail", args=[run.pk]))

    def test_default_mode_is_still_the_draft_boq(self):
        self.client.force_login(self.pm)
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client({"document_summary": "", "currency": None, "sections": [], "issues": []})):
            self.client.post(reverse("ai_assistant:analyze", args=[self.project.pk]), {"file": SimpleUploadedFile("boq.csv", b"1,x,m2\n")})
        self.assertEqual(AIRun.objects.exclude(pk=self.run.pk).get().kind, AIRun.BOQ_EXTRACT)

    def test_the_result_page_shows_materials_the_boq_comparison_and_edge_data(self):
        page = self.get(self.pm, "run_detail", self.run.pk)
        self.assertContains(page, "Ceramic floor tiles 60x60")
        self.assertContains(page, "not stated")
        self.assertContains(page, "Compared with the BOQ")
        self.assertContains(page, "52.5")
        self.assertContains(page, "2850.00")
        self.assertContains(page, "Double glazing 6-12-6 mm, low-E")
        self.assertContains(page, "Scale missing on sheet 3")
        self.assertContains(page, "2 / %d" % len(edge.POINT_IDS))
        self.assertContains(page, "Not stated")

    def test_the_general_manager_can_view_but_the_engineer_cannot(self):
        self.assertEqual(self.get(self.gm, "run_detail", self.run.pk).status_code, 200)
        self.assertEqual(self.get(self.engineer, "run_detail", self.run.pk).status_code, 403)
        self.assertEqual(self.get(self.engineer, "project_edge", self.project.pk).status_code, 403)

    def test_the_materials_list_downloads_as_a_spreadsheet(self):
        response = self.get(self.pm, "takeoff_csv", self.run.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertTrue(body.startswith(chr(0xFEFF)), "a BOM so Excel reads Arabic")
        self.assertIn("Ceramic floor tiles 60x60", body)
        lines = body.splitlines()
        self.assertEqual(len(lines), 1 + 5)
        self.assertIn("BOQ code", lines[0])
        self.assertEqual(self.get(self.engineer, "takeoff_csv", self.run.pk).status_code, 403)

    def test_a_run_without_a_takeoff_has_no_spreadsheet(self):
        other = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, status=AIRun.DONE, created_by=self.pm, result={"summary": ""})
        self.assertEqual(self.get(self.pm, "takeoff_csv", other.pk).status_code, 404)

    def test_the_project_green_summary_combines_documents_and_lists_what_is_missing(self):
        second = takeoff.clean_takeoff({"items": [], "green_data": [{"point": "roof_insulation", "value": "XPS 8 cm"}]})
        AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE, created_by=self.pm, source_label="Spec", result=second)
        AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.FAILED, created_by=self.pm, source_label="Broken")
        page = self.get(self.pm, "project_edge", self.project.pk)
        self.assertContains(page, "XPS 8 cm")
        self.assertContains(page, "Dual flush 3/6 L")
        self.assertContains(page, "3 / %d" % len(edge.POINT_IDS))
        self.assertContains(page, "Still missing")
        self.assertContains(page, "nothing on this page is an EDGE result")
        self.assertNotContains(page, "Broken")
        data = edge.project_edge_data(self.project)
        self.assertEqual((data["found"], len(data["documents"])), (3, 2))

    def test_only_the_latest_analysis_of_a_document_counts(self):
        newer = takeoff.clean_takeoff({"items": [], "green_data": [{"point": "wc_flush", "value": "4.5 L newer"}]})
        AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE, created_by=self.pm,
                             source_label=self.run.source_label, result=newer)
        values = [e["value"] for d in edge.project_edge_data(self.project)["domains"] for p in d["points"] for e in p["entries"]]
        self.assertIn("4.5 L newer", values)
        self.assertNotIn("Dual flush 3/6 L", values)

    def test_the_green_summary_csv_marks_missing_points(self):
        response = self.get(self.pm, "project_edge_csv", self.project.pk)
        body = response.content.decode("utf-8")
        self.assertIn("MISSING", body)
        self.assertIn("Double glazing 6-12-6 mm, low-E", body)
        self.assertEqual(len(body.splitlines()) - 1, len(edge.POINT_IDS))


@override_settings(AI_RUN_IN_BACKGROUND=False, ANTHROPIC_API_KEY="test-key")
class DrawingButtonTests(Base):
    def setUp(self):
        blueprint = Blueprint.objects.create(project=self.project, drawing_number="A-01", title="Plan", discipline="architectural")
        self.revision = BlueprintRevision.objects.create(blueprint=blueprint, revision="0", status="approved",
                                                         file=SimpleUploadedFile("plan.csv", b"D1,door,4\n"))

    def analyze(self, user):
        self.client.force_login(user)
        return self.client.post(reverse("ai_assistant:analyze_drawing", args=[self.revision.pk]))

    def test_analyzing_a_revision_starts_a_run_linked_to_it(self):
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client(RAW)):
            response = self.analyze(self.pm)
        run = AIRun.objects.get()
        self.assertEqual((run.kind, run.source_revision, run.status), (AIRun.DRAWING_TAKEOFF, self.revision, AIRun.DONE))
        self.assertIn("A-01 rev 0", run.source_label)
        self.assertRedirects(response, reverse("ai_assistant:run_detail", args=[run.pk]))

    def test_only_managers_can_analyze_drawings(self):
        self.assertEqual(self.analyze(self.gm).status_code, 403)
        self.assertEqual(self.analyze(self.engineer).status_code, 403)
        self.assertEqual(AIRun.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_without_an_ai_set_up_nothing_starts_and_the_reason_is_shown(self):
        self.client.force_login(self.pm)
        response = self.client.post(reverse("ai_assistant:analyze_drawing", args=[self.revision.pk]), follow=True)
        self.assertContains(response, "ANTHROPIC_API_KEY")
        self.assertEqual(AIRun.objects.count(), 0)

    def test_the_drawings_page_shows_the_analyze_button_then_the_result_link(self):
        self.client.force_login(self.pm)
        url = reverse("blueprints:project_drawings", args=[self.project.pk])
        self.assertContains(self.client.get(url), reverse("ai_assistant:analyze_drawing", args=[self.revision.pk]))
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client(RAW)):
            self.analyze(self.pm)
        run = AIRun.objects.get()
        page = self.client.get(url)
        self.assertContains(page, reverse("ai_assistant:run_detail", args=[run.pk]))
        self.assertContains(page, "AI analysis")
        self.assertContains(page, "Re-analyze")

    def test_the_analyze_button_is_hidden_from_people_who_cannot_use_it(self):
        self.client.force_login(self.engineer)
        Project = self.project.__class__
        Project.objects.filter(pk=self.project.pk).update(site_engineer=self.engineer)
        page = self.client.get(reverse("blueprints:project_drawings", args=[self.project.pk]))
        self.assertNotContains(page, reverse("ai_assistant:analyze_drawing", args=[self.revision.pk]))

    @override_settings(ANTHROPIC_API_KEY="")
    def test_the_analyze_button_is_hidden_when_the_ai_is_not_set_up(self):
        self.client.force_login(self.pm)
        page = self.client.get(reverse("blueprints:project_drawings", args=[self.project.pk]))
        self.assertNotContains(page, reverse("ai_assistant:analyze_drawing", args=[self.revision.pk]))


@override_settings(AI_RUN_IN_BACKGROUND=False, ANTHROPIC_API_KEY="test-key", AI_AUTO_ANALYZE_DRAWINGS=True)
class AutomaticAnalysisTests(Base):
    def revision(self, name="plan.csv"):
        blueprint = Blueprint.objects.create(project=self.project, drawing_number=f"A-{Blueprint.objects.count() + 1}", title="Plan", discipline="architectural")
        return BlueprintRevision.objects.create(blueprint=blueprint, revision="0", file=SimpleUploadedFile(name, b"D1,door,4\n"))

    def test_an_uploaded_drawing_is_analyzed_when_the_ai_is_set_up(self):
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client(RAW)):
            run = triggers.auto_analyze_revision(self.revision(), self.engineer)
        self.assertEqual((run.status, run.created_by), (AIRun.DONE, self.engineer))

    @override_settings(AI_AUTO_ANALYZE_DRAWINGS=False)
    def test_it_can_be_switched_off(self):
        self.assertIsNone(triggers.auto_analyze_revision(self.revision(), self.pm))
        self.assertEqual(AIRun.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_nothing_happens_without_a_provider(self):
        self.assertIsNone(triggers.auto_analyze_revision(self.revision(), self.pm))

    def test_cad_files_are_skipped_because_they_cannot_be_read(self):
        self.assertIsNone(triggers.auto_analyze_revision(self.revision("plan.dwg"), self.pm))
        self.assertEqual(AIRun.objects.count(), 0)

    def test_a_problem_starting_the_analysis_never_breaks_the_upload(self):
        with mock.patch("ai_assistant.triggers.start_takeoff", side_effect=RuntimeError("boom")), self.assertLogs("ai_assistant.triggers", level="ERROR"):
            self.assertIsNone(triggers.auto_analyze_revision(self.revision(), self.pm))

    @override_settings(**LOCAL)
    def test_it_works_with_the_local_provider_too(self):
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply(json.dumps(RAW), prompt=50))):
            run = triggers.auto_analyze_revision(self.revision(), self.pm)
        self.assertEqual((run.status, run.model_name), (AIRun.DONE, "qwen2.5:7b"))


@override_settings(AI_RUN_IN_BACKGROUND=False)
class ReviewToolTests(Base):
    def test_the_review_and_chat_can_see_the_takeoffs(self):
        boq(self.project)
        AIRun.objects.create(project=self.project, kind=AIRun.DRAWING_TAKEOFF, status=AIRun.DONE, created_by=self.pm, source_label="A-01",
                             result=takeoff.clean_takeoff(RAW))
        tools = {f.__name__: f for f in make_tools(self.project, {})}
        data = json.loads(tools["get_drawing_takeoffs"]())
        document = data["documents"][0]
        self.assertEqual(document["document"], "A-01")
        self.assertEqual(document["totals"]["estimated_cost"], "2850.00")
        self.assertEqual(document["items_without_a_boq_line"], ["Waterproofing membrane"])
        green = data["green_building_edge"]
        self.assertEqual((green["found"], green["total"]), (2, len(edge.POINT_IDS)))
        self.assertIn("EDGE app", green["note"])
        self.assertNotIn("Double glazing", json.dumps(data["documents"]))
        self.assertTrue(any(s["point"] == "glazing_type" for s in green["stated"]))
