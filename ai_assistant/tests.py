"""
The AI assistant, tested without the network: a fake client stands in for Claude, so these check everything
around the model -- input handling, cleaning, importing, permissions, review tools -- not the model's judgement.
"""
import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from projects.models import Project, ProjectTenderDocument
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

from . import chat, claude, documents, jobs
from .extraction import clean_draft, extract_boq
from .health import project_health
from .importer import compare_with_boq, import_draft, mark_conflicts
from .models import AIRun
from .review import clean_review, make_tools, review_project

User = get_user_model()


def make_project(name, symbol, **fields):
    return Project.objects.create(name=name, project_symbol=symbol, client_name="Client", start_date=date(2026, 1, 1),
                                  contract_number=f"C-{symbol}", status="active", **fields)

RAW_DRAFT = {
    "document_summary": "Finishing works BOQ",
    "currency": "ILS",
    "sections": [{
        "name": "Civil Works",
        "items": [
            {"code": "1.1", "name_ar": "بند أول", "name_en": "First", "unit": "m2", "quantity": 100, "unit_price": 12.5,
             "source_page": 3, "confidence": "high", "notes": "", "sub_items": []},
            {"code": "1.2", "name_ar": "بند ثاني", "name_en": "Second", "unit": None, "quantity": None, "unit_price": None,
             "source_page": 3, "confidence": "medium", "notes": "",
             "sub_items": [
                 {"code": "1.2.1", "name_ar": "فرعي", "name_en": "Sub", "unit": "m", "quantity": 40, "unit_price": None,
                  "source_page": 4, "confidence": "high", "notes": ""},
                 {"code": "1.2.2", "name_ar": "فرعي 2", "name_en": "Sub 2", "unit": "no", "quantity": -5, "unit_price": None,
                  "source_page": None, "confidence": "weird", "notes": ""},
             ]},
            {"code": "1.1", "name_ar": "مكرر", "name_en": "Dup", "unit": "m2", "quantity": 5, "unit_price": None,
             "source_page": 5, "confidence": "low", "notes": "", "sub_items": []},
        ],
    }],
    "issues": [{"severity": "warning", "message": "Page 6 unreadable", "item_code": None}, {"severity": "bogus", "message": "odd", "item_code": "1.2"}],
}


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def fake_message(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


def fake_client(payload, stop_reason="end_turn"):
    client = mock.Mock()
    client.messages.stream.return_value = FakeStream(fake_message(payload, stop_reason))
    return client


class ScriptedRunner:
    """Stands in for client.beta.messages.tool_runner: calls the tools the script names, like the model would."""

    def __init__(self, tools, script, final_text=""):
        self.tools = {t.name: t for t in tools}
        self.script = script
        self.final_text = final_text
        self.results = {}

    def __iter__(self):
        for name, args in self.script:
            self.results[name] = self.tools[name].call(args)
            yield SimpleNamespace(stop_reason="tool_use", content=[], usage=SimpleNamespace(input_tokens=500, output_tokens=50))
        content = [SimpleNamespace(type="text", text=self.final_text)] if self.final_text else []
        yield SimpleNamespace(stop_reason="end_turn", content=content, usage=SimpleNamespace(input_tokens=600, output_tokens=80))


def review_client(script, holder=None, final_text=""):
    client = mock.Mock()

    def tool_runner(**kwargs):
        runner = ScriptedRunner(kwargs["tools"], script, final_text)
        if holder is not None:
            holder["runner"], holder["kwargs"] = runner, kwargs
        return runner

    client.beta.messages.tool_runner.side_effect = tool_runner
    return client


class Base(TestCase):
    """Uploads go to a throw-away MEDIA_ROOT so tests never leave files in the real media folder."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("boss", password="x", role="admin")
        cls.gm = User.objects.create_user("gm", password="x", role="general_manager")
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.other_pm = User.objects.create_user("pm2", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")
        cls.project = make_project("Dura Branch", "DUR", manager=cls.pm)


@override_settings(AI_RUN_IN_BACKGROUND=False)
class CleaningTests(Base):
    def test_clean_draft_makes_model_output_safe(self):
        draft = clean_draft(RAW_DRAFT)
        first, second, dup = draft["sections"][0]["items"]
        self.assertEqual(first["quantity"], "100")
        self.assertEqual(first["unit_price"], "12.5")
        self.assertEqual([first["key"], second["key"], dup["key"]], ["s0-i0", "s0-i1", "s0-i2"])
        self.assertEqual(second["sub_items"][0]["key"], "s0-i1-c0")
        bad_sub = second["sub_items"][1]
        self.assertIsNone(bad_sub["quantity"], "a negative quantity must not survive")
        self.assertEqual(bad_sub["confidence"], "medium")
        self.assertTrue(any("1.1" in i["message"] and "more than once" in i["message"] for i in draft["issues"]))
        self.assertEqual({i["severity"] for i in draft["issues"]}, {"warning", "info"})

    def test_clean_draft_survives_junk(self):
        draft = clean_draft({"sections": [{"name": None, "items": [{"code": None, "sub_items": None}]}], "issues": [{}]})
        self.assertEqual(draft["sections"][0]["items"][0]["code"], "")
        self.assertEqual(draft["issues"], [])

    def test_extract_boq_with_fake_client(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, created_by=self.admin,
                                   source_file=SimpleUploadedFile("boq.csv", b"1.1,Item,m2,10\n"))
        draft = extract_boq(run, client=fake_client(RAW_DRAFT))
        self.assertEqual(draft["totals"], {"sections": 1, "items": 3, "sub_items": 2})
        self.assertEqual((run.input_tokens, run.output_tokens), (1000, 200))

    def test_structured_reply_failure_modes(self):
        for payload, stop, text in [
            ({}, "refusal", "declined"), ({}, "max_tokens", "too large"), ("not json{", "end_turn", "invalid format"),
        ]:
            with self.assertRaises(claude.AIFailure) as ctx:
                claude.structured_reply(fake_client(payload, stop), system="s", content=[], schema={})
            self.assertIn(text, str(ctx.exception))

    def test_request_shape(self):
        client = fake_client(RAW_DRAFT)
        claude.structured_reply(client, system="sys", content=[{"type": "text", "text": "hi"}], schema={"type": "object"})
        kwargs = client.messages.stream.call_args.kwargs
        self.assertEqual(kwargs["thinking"], {"type": "adaptive"})
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertNotIn("temperature", kwargs)

    @override_settings(AI_REFUSAL_FALLBACK=True)
    def test_refusal_fallback_is_opt_in(self):
        client = mock.Mock()
        client.beta.messages.stream.return_value = FakeStream(fake_message(RAW_DRAFT))
        claude.structured_reply(client, system="s", content=[], schema={})
        self.assertEqual(client.beta.messages.stream.call_args.kwargs["fallbacks"], "default")


class DocumentTests(TestCase):
    def test_pdf_becomes_document_block(self):
        import pymupdf as fitz

        pdf = fitz.open()
        pdf.new_page()
        blocks = documents.content_blocks("a.pdf", SimpleUploadedFile("a.pdf", pdf.tobytes()))
        self.assertEqual(blocks[0]["type"], "document")
        self.assertEqual(blocks[0]["source"]["media_type"], "application/pdf")
        with override_settings(AI_MAX_PDF_PAGES=0), self.assertRaises(documents.UnsupportedSource):
            documents.content_blocks("a.pdf", SimpleUploadedFile("a.pdf", pdf.tobytes()))

    def test_pdf_check_rejects_damaged_files(self):
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            self.skipTest("PyMuPDF not installed")
        with self.assertRaises(documents.UnsupportedSource):
            documents.content_blocks("a.pdf", SimpleUploadedFile("a.pdf", b"not a pdf"))

    def test_cad_files_ask_for_pdf(self):
        with self.assertRaises(documents.UnsupportedSource) as ctx:
            documents.content_blocks("plan.dwg", SimpleUploadedFile("plan.dwg", b"x"))
        self.assertIn("PDF", str(ctx.exception))

    def test_csv_and_size_limit(self):
        blocks = documents.content_blocks("q.csv", SimpleUploadedFile("q.csv", "1.1,بند,10\n".encode()))
        self.assertIn("1.1 | بند | 10", blocks[0]["text"])
        with override_settings(AI_MAX_UPLOAD_MB=0):
            with self.assertRaises(documents.UnsupportedSource):
                documents.content_blocks("q.csv", SimpleUploadedFile("q.csv", b"abc"))

    def test_big_image_rejected(self):
        with self.assertRaises(documents.UnsupportedSource):
            documents.content_blocks("p.png", SimpleUploadedFile("p.png", b"0" * (5 * 1024 * 1024 + 1)))


class ImportTests(Base):
    def make_run(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, status=AIRun.DONE, created_by=self.admin)
        run.result = clean_draft(RAW_DRAFT)
        run.save()
        return run

    def test_import_creates_phases_and_sub_items_without_prices(self):
        run = self.make_run()
        summary = import_draft(run, ["s0-i0", "s0-i1"])
        self.assertEqual(summary["created_phases"], 2)
        whole = ProjectPhase.objects.get(project=self.project, code="1.1")
        self.assertEqual((whole.unit, whole.quantity, whole.section), ("m2", Decimal("100"), "Civil Works"))
        self.assertIn(f"[AI:run {run.pk}]", whole.notes)
        self.assertEqual(whole.sub_items.count(), 1)
        self.assertTrue(whole.sub_items.get().is_whole)
        self.assertFalse(whole.contract_unit_price)
        parent = ProjectPhase.objects.get(project=self.project, code="1.2")
        self.assertEqual(sorted(parent.sub_items.values_list("code", flat=True)), ["1.2.1", "1.2.2"])
        self.assertEqual(parent.sub_items.get(code="1.2.1").quantity, Decimal("40"))
        self.assertIsNone(parent.sub_items.get(code="1.2.2").quantity)

    def test_printed_prices_only_when_asked(self):
        run = self.make_run()
        import_draft(run, ["s0-i0"], use_printed_prices=True)
        self.assertEqual(ProjectPhaseSubItem.objects.get(phase__code="1.1").contract_unit_price, Decimal("12.50"))

    def test_existing_item_numbers_are_never_overwritten(self):
        ProjectPhase.objects.create(project=self.project, code="1.1", name_ar="موجود", weight_percentage=0, order=1)
        run = self.make_run()
        draft = mark_conflicts(self.project, run.result)
        self.assertTrue(draft["sections"][0]["items"][0]["exists"])
        summary = import_draft(run, ["s0-i0", "s0-i1", "s0-i2"])
        self.assertEqual(ProjectPhase.objects.get(project=self.project, code="1.1").name_ar, "موجود")
        self.assertEqual(summary["created_phases"], 1)
        self.assertEqual(len(summary["skipped"]), 2, "the existing 1.1 and the duplicate 1.1 in the document")

    def test_import_twice_adds_nothing_new(self):
        run = self.make_run()
        import_draft(run, ["s0-i0", "s0-i1"])
        again = import_draft(run, ["s0-i0", "s0-i1"])
        self.assertEqual(again["created_phases"], 0)
        self.assertEqual(ProjectPhase.objects.filter(project=self.project).count(), 2)

    def test_unselected_items_are_not_imported(self):
        import_draft(self.make_run(), ["s0-i1"])
        self.assertEqual(list(ProjectPhase.objects.filter(project=self.project).values_list("code", flat=True)), ["1.2"])

    def test_compare_with_boq(self):
        phase = ProjectPhase.objects.create(project=self.project, code="1.1", name_ar="x", weight_percentage=0, order=1,
                                            unit="m2", quantity=Decimal("90"))
        phase.sync_whole_item()
        ProjectPhase.objects.create(project=self.project, code="9.9", name_ar="only here", weight_percentage=0, order=2)
        result = compare_with_boq(self.project, clean_draft(RAW_DRAFT))
        self.assertIn("1.2", result["only_in_document"])
        self.assertEqual(result["only_in_boq"], ["9.9"])
        self.assertTrue(any(d["code"] == "1.1" and d["boq"].startswith("90") for d in result["quantity_differences"]))


class HealthTests(Base):
    def test_empty_boq(self):
        self.assertIn("The project has no BOQ yet", [f["title"] for f in project_health(self.project)])

    def test_priced_below_cost_and_weights(self):
        phase = ProjectPhase.objects.create(project=self.project, code="1", name_ar="a", weight_percentage=50, order=1,
                                            unit="m2", quantity=Decimal("10"), budget_unit_price=Decimal("100"), contract_unit_price=Decimal("80"))
        phase.sync_whole_item()
        titles = [f["title"] for f in project_health(self.project)]
        self.assertTrue(any("priced below their cost" in t for t in titles))
        self.assertTrue(any("not 100%" in t for t in titles))
        self.assertEqual(project_health(self.project)[0]["severity"], "error")


@override_settings(AI_RUN_IN_BACKGROUND=False)
class ReviewTests(Base):
    def test_every_tool_builds_a_schema_and_runs(self):
        from anthropic import beta_tool

        sink = {}
        tools = [beta_tool(fn) for fn in make_tools(self.project, sink)]
        self.assertEqual(len(tools), 9)
        for tool in tools:
            tool.to_dict()
            if tool.name != "submit_review":
                json.loads(tool.call({}))

    def test_tools_are_read_only_and_project_scoped(self):
        other = make_project("Elsewhere", "ELS")
        ProjectPhase.objects.create(project=other, code="X1", name_ar="secret other item", weight_percentage=100, order=1)
        tools = {fn.__name__: fn for fn in make_tools(self.project, {})}
        for name in ("get_boq", "get_cost_summary", "get_progress", "get_purchasing", "get_document_extractions", "get_project_overview"):
            self.assertNotIn("secret other item", tools[name]())
        counts = (ProjectPhase.objects.count(), AIRun.objects.count())
        for name, fn in tools.items():
            if name != "submit_review":
                fn()
        self.assertEqual(counts, (ProjectPhase.objects.count(), AIRun.objects.count()))

    def test_review_run_stores_cleaned_findings(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, created_by=self.admin)
        holder = {}
        script = [("get_health_checks", {}), ("submit_review", {"summary": "Fine.", "findings": [
            {"severity": "warning", "area": "BOQ", "title": "Weights", "detail": "d", "action": "a"},
            {"severity": "made-up", "title": "Odd severity"},
            {"title": ""},
        ]})]
        result = review_project(run, client=review_client(script, holder))
        self.assertEqual([f["title"] for f in result["findings"]], ["Weights", "Odd severity"])
        self.assertEqual(result["findings"][1]["severity"], "info")
        self.assertIn("health_checks", result)
        self.assertEqual((run.input_tokens, run.output_tokens), (1600, 180))
        kwargs = holder["kwargs"]
        self.assertEqual(kwargs["thinking"], {"type": "adaptive"})
        self.assertLessEqual(kwargs["max_iterations"], 30)

    def test_review_without_submission_fails(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, created_by=self.admin)
        with self.assertRaises(claude.AIFailure):
            review_project(run, client=review_client([("get_health_checks", {})]))

    def test_clean_review_orders_by_severity(self):
        cleaned = clean_review({"summary": "s", "findings": [{"title": "b", "severity": "info"}, "junk", {"title": "a", "severity": "error"}]})
        self.assertEqual([f["title"] for f in cleaned["findings"]], ["a", "b"])


@override_settings(AI_RUN_IN_BACKGROUND=False)
class JobTests(Base):
    def test_success_and_failure_are_recorded(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, created_by=self.admin,
                                   source_file=SimpleUploadedFile("boq.csv", b"1.1,Item,m2,10\n"))
        jobs.execute_run(run.pk, client=fake_client(RAW_DRAFT))
        run.refresh_from_db()
        self.assertEqual(run.status, AIRun.DONE)
        self.assertIsNotNone(run.finished_at)

        bad = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, created_by=self.admin,
                                   source_file=SimpleUploadedFile("plan.dwg", b"x"))
        jobs.execute_run(bad.pk, client=fake_client(RAW_DRAFT))
        bad.refresh_from_db()
        self.assertEqual(bad.status, AIRun.FAILED)
        self.assertIn("PDF", bad.error)

    def test_unexpected_errors_become_a_message(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, created_by=self.admin,
                                   source_file=SimpleUploadedFile("boq.csv", b"a"))
        client = mock.Mock()
        client.messages.stream.side_effect = RuntimeError("boom")
        with self.assertLogs("ai_assistant.jobs", level="ERROR"):
            jobs.execute_run(run.pk, client=client)
        run.refresh_from_db()
        self.assertEqual(run.status, AIRun.FAILED)
        self.assertIn("boom", run.error)

    def test_stale_runs_are_recovered(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, status=AIRun.RUNNING, created_by=self.admin)
        AIRun.objects.filter(pk=run.pk).update(created_at=run.created_at.replace(year=2020))
        jobs.recover_stale_runs()
        run.refresh_from_db()
        self.assertEqual(run.status, AIRun.FAILED)


@override_settings(AI_RUN_IN_BACKGROUND=False, ANTHROPIC_API_KEY="test-key")
class ViewTests(Base):
    def go(self, user, name, *args, method="get", data=None, **kw):
        self.client.force_login(user)
        url = reverse(f"ai_assistant:{name}", args=args)
        return getattr(self.client, method)(url, data or {}, **kw)

    def test_who_can_open_the_project_page(self):
        for user, code in [(self.admin, 200), (self.gm, 200), (self.pm, 200), (self.other_pm, 403), (self.engineer, 403)]:
            self.assertEqual(self.go(user, "project_ai", self.project.pk).status_code, code, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("ai_assistant:project_ai", args=[self.project.pk])).status_code, 302)

    def test_gm_can_review_but_not_read_or_import(self):
        with mock.patch("ai_assistant.claude.get_client", return_value=review_client([("submit_review", {"summary": "ok", "findings": []})])):
            response = self.go(self.gm, "start_review", self.project.pk, method="post")
        run = AIRun.objects.get()
        self.assertRedirects(response, reverse("ai_assistant:run_detail", args=[run.pk]))
        self.assertEqual(run.status, AIRun.DONE)
        self.assertEqual(self.go(self.gm, "analyze", self.project.pk, method="post", data={"source": "x"}).status_code, 403)
        self.assertEqual(self.go(self.gm, "run_import", run.pk, method="post", data={"keys": ["s0-i0"]}).status_code, 403)
        self.assertContains(self.go(self.gm, "run_detail", run.pk), "Summary")

    def test_analyze_upload_then_import_end_to_end(self):
        upload = SimpleUploadedFile("boq.csv", b"1.1,Item,m2,10\n")
        with mock.patch("ai_assistant.claude.get_client", return_value=fake_client(RAW_DRAFT)):
            response = self.go(self.pm, "analyze", self.project.pk, method="post", data={"file": upload, "instructions": "section 1 only"})
        run = AIRun.objects.get()
        self.assertRedirects(response, reverse("ai_assistant:run_detail", args=[run.pk]))
        self.assertEqual((run.status, run.instructions, run.source_label), (AIRun.DONE, "section 1 only", "boq.csv"))

        page = self.go(self.pm, "run_detail", run.pk)
        self.assertContains(page, "Draft BOQ")
        self.assertContains(page, "بند أول")
        self.assertContains(page, "Page 6 unreadable")

        response = self.go(self.pm, "run_import", run.pk, method="post", data={"keys": ["s0-i0", "s0-i1"]})
        self.assertRedirects(response, reverse("ai_assistant:run_detail", args=[run.pk]))
        run.refresh_from_db()
        self.assertEqual(run.import_summary["created_phases"], 2)
        self.assertEqual(run.imported_by, self.pm)
        self.assertEqual(ProjectPhase.objects.filter(project=self.project).count(), 2)
        from accounts.models import UserAuditLog
        self.assertEqual(UserAuditLog.objects.filter(content_type="AIRun").count(), 2)

    def test_import_needs_ticked_items_and_a_finished_draft(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, status=AIRun.FAILED, created_by=self.pm)
        self.go(self.pm, "run_import", run.pk, method="post", data={"keys": ["s0-i0"]})
        self.assertEqual(ProjectPhase.objects.count(), 0)
        run.status, run.result = AIRun.DONE, clean_draft(RAW_DRAFT)
        run.save()
        self.go(self.pm, "run_import", run.pk, method="post", data={})
        self.assertEqual(ProjectPhase.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_not_configured_is_explained_and_nothing_is_created(self):
        response = self.go(self.pm, "start_review", self.project.pk, method="post", follow=True)
        self.assertContains(response, "ANTHROPIC_API_KEY")
        self.assertEqual(AIRun.objects.count(), 0)
        self.assertContains(self.go(self.pm, "project_ai", self.project.pk), "isn't switched on")

    def test_upload_validation(self):
        response = self.go(self.pm, "analyze", self.project.pk, method="post",
                           data={"file": SimpleUploadedFile("plan.dwg", b"x")}, follow=True)
        self.assertContains(response, "Export drawings from CAD to PDF")
        self.assertEqual(AIRun.objects.count(), 0)
        self.go(self.pm, "analyze", self.project.pk, method="post", data={})
        self.assertEqual(AIRun.objects.count(), 0)

    def test_source_must_belong_to_the_project(self):
        other = make_project("Elsewhere", "ELS")
        doc = ProjectTenderDocument.objects.create(project=other, category="boq", title="Other BOQ",
                                                   document=SimpleUploadedFile("o.pdf", b"%PDF"))
        response = self.go(self.pm, "analyze", self.project.pk, method="post", data={"source": f"tender:{doc.pk}"})
        self.assertEqual(response.status_code, 404)

    def test_status_endpoint(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, status=AIRun.RUNNING, created_by=self.pm)
        self.assertEqual(self.go(self.pm, "run_status", run.pk).json(), {"status": "running", "finished": False, "error": ""})
        self.assertEqual(self.go(self.other_pm, "run_status", run.pk).status_code, 403)
        self.assertContains(self.go(self.pm, "run_detail", run.pk), "Reviewing the project")


class ChatTests(Base):
    def test_clean_history(self):
        cleaned = chat.clean_history([
            {"role": "assistant", "content": "stray first"}, {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "  hello  "}, {"role": "user", "content": "again"},
            {"role": "assistant", "content": "hi"}, {"role": "user", "content": "x" * 9000}, {"role": "user", "content": ""}, "junk",
        ])
        self.assertEqual([m["role"] for m in cleaned], ["user", "assistant", "user"])
        self.assertEqual(cleaned[0]["content"], "hello\n\nagain")
        self.assertEqual(len(cleaned[2]["content"]), chat.MAX_MESSAGE_CHARS)
        for bad in (None, [], [{"role": "assistant", "content": "hi"}], [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]):
            with self.assertRaises(chat.ChatInputError):
                chat.clean_history(bad)

    def test_answer_uses_read_only_tools(self):
        holder = {}
        client = review_client([("get_health_checks", {})], holder, final_text="Two items are unpriced.")
        result = chat.answer(self.project, [{"role": "user", "content": "what is wrong?"}], client=client)
        self.assertEqual(result["reply"], "Two items are unpriced.")
        self.assertEqual((result["input_tokens"], result["output_tokens"]), (1100, 130))
        names = {t.name for t in holder["kwargs"]["tools"]}
        self.assertNotIn("submit_review", names)
        self.assertIn("get_cost_summary", names)
        self.assertIn(self.project.name, holder["kwargs"]["system"])
        self.assertEqual(holder["kwargs"]["messages"], [{"role": "user", "content": "what is wrong?"}])

    def test_answer_without_text_fails_politely(self):
        with self.assertRaises(claude.AIFailure):
            chat.answer(self.project, [{"role": "user", "content": "q"}], client=review_client([("get_health_checks", {})]))


@override_settings(ANTHROPIC_API_KEY="test-key")
class ChatViewTests(Base):
    def post(self, user, project_id=None, messages=None):
        self.client.force_login(user)
        payload = {"project_id": project_id or self.project.pk, "messages": messages or [{"role": "user", "content": "how are we doing?"}]}
        return self.client.post(reverse("ai_assistant:chat_message"), json.dumps(payload), content_type="application/json")

    def test_config_lists_only_the_users_projects(self):
        other = make_project("Elsewhere", "ELS")
        self.client.force_login(self.pm)
        data = self.client.get(reverse("ai_assistant:chat_config")).json()
        self.assertEqual([p["id"] for p in data["projects"]], [self.project.pk])
        self.assertTrue(data["configured"])
        self.client.force_login(self.gm)
        self.assertEqual({p["id"] for p in self.client.get(reverse("ai_assistant:chat_config")).json()["projects"]}, {self.project.pk, other.pk})
        self.client.force_login(self.engineer)
        self.assertEqual(self.client.get(reverse("ai_assistant:chat_config")).json(), {"enabled": False})

    def test_reply(self):
        client = review_client([("get_health_checks", {})], final_text="Everything is fine.")
        with mock.patch("ai_assistant.claude.get_client", return_value=client):
            response = self.post(self.pm)
        self.assertEqual((response.status_code, response.json()), (200, {"reply": "Everything is fine."}))

    def test_permissions_and_bad_input(self):
        self.assertEqual(self.post(self.engineer).status_code, 403)
        self.assertEqual(self.post(self.other_pm).status_code, 400, "someone else's project is not selectable")
        self.assertEqual(self.post(self.pm, project_id="abc").status_code, 400)
        self.assertEqual(self.post(self.pm, messages=[{"role": "assistant", "content": "hi"}]).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("ai_assistant:chat_message"), "{}", content_type="application/json").status_code, 302)

    @override_settings(ANTHROPIC_API_KEY="")
    def test_not_configured(self):
        response = self.post(self.pm)
        self.assertEqual(response.status_code, 503)
        self.assertIn("ANTHROPIC_API_KEY", response.json()["error"])

    def test_failures_become_messages(self):
        client = mock.Mock()
        client.beta.messages.tool_runner.side_effect = RuntimeError("boom")
        with mock.patch("ai_assistant.claude.get_client", return_value=client), self.assertLogs("ai_assistant.views", level="ERROR"):
            response = self.post(self.pm)
        self.assertEqual(response.status_code, 502)
        self.assertIn("boom", response.json()["error"])

    def test_hourly_limit(self):
        from django.core.cache import cache

        cache.clear()
        client = review_client([], final_text="ok")
        with mock.patch("ai_assistant.claude.get_client", return_value=client), mock.patch("ai_assistant.views.CHAT_LIMIT_PER_HOUR", 2):
            self.assertEqual([self.post(self.pm).status_code for _ in range(3)], [200, 200, 429])
        cache.clear()

    def test_bubble_only_for_permitted_roles(self):
        url = reverse("projects:project_list")
        for user, shown in [(self.admin, True), (self.gm, True), (self.pm, True), (self.engineer, False)]:
            self.client.force_login(user)
            self.assertEqual(b"aicFab" in self.client.get(url).content, shown, user.username)
