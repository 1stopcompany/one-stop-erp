"""
The local (Ollama) provider, tested without Ollama: `ollama._post` is replaced by a scripted fake, so these check what
we SEND (model, schema, context size, images, tool results) and how we handle what comes back -- not the local model's
judgement. Live behaviour against a real Ollama has not been exercised by these tests.
"""
import copy
import json
from unittest import mock

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from . import chat, documents, llm, ollama
from .base import AIFailure
from .extraction import BOQ_SCHEMA, extract_boq
from .models import AIRun
from .review import REVIEW_SCHEMA, make_tools, review_project
from .tests import RAW_DRAFT, Base

LOCAL = dict(AI_PROVIDER="ollama", OLLAMA_URL="http://ollama.test:11434", OLLAMA_MODEL="qwen2.5:7b", OLLAMA_VISION_MODEL="",
             OLLAMA_NUM_CTX=16384, OLLAMA_PDF_MODE="auto", OLLAMA_MAX_IMAGE_PAGES=12, ANTHROPIC_API_KEY="", AI_RUN_IN_BACKGROUND=False)


def reply(content="", tool_calls=None, prompt=100, out=20, done_reason="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"message": message, "prompt_eval_count": prompt, "eval_count": out, "done_reason": done_reason}


def call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


class FakeOllama:
    """Stands in for ollama._post: returns the scripted replies in order and remembers what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, path, payload):
        self.calls.append((path, copy.deepcopy(payload)))
        return self.replies.pop(0)

    @property
    def payloads(self):
        return [p for _, p in self.calls]


def pdf_bytes(*page_texts):
    import pymupdf

    pdf = pymupdf.open()
    for text in page_texts:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
    return pdf.tobytes()


def pdf_upload(*page_texts):
    return SimpleUploadedFile("boq.pdf", pdf_bytes(*page_texts))


@override_settings(**LOCAL)
class ProviderSwitchTests(SimpleTestCase):
    def test_local_provider_is_selected_and_described(self):
        self.assertTrue(llm.is_local())
        self.assertTrue(llm.is_configured())
        self.assertEqual(llm.model_name(), "qwen2.5:7b")
        self.assertTrue(llm.describe()["local"])
        self.assertIn("own machine", llm.describe()["label"])
        self.assertIn("OLLAMA_URL", llm.setup_hint())
        self.assertLess(llm.tool_result_limit(), llm.CLOUD_TOOL_RESULT_LIMIT)

    def test_not_configured_without_a_model(self):
        with override_settings(OLLAMA_MODEL=""):
            self.assertFalse(llm.is_configured())

    @override_settings(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="k")
    def test_cloud_is_the_default_behaviour(self):
        self.assertFalse(llm.is_local())
        self.assertTrue(llm.is_configured())
        self.assertIsNone(llm.status())
        self.assertIn("Anthropic", llm.describe()["label"])
        self.assertIn("ANTHROPIC_API_KEY", llm.setup_hint())


@override_settings(**LOCAL)
class ConnectionTests(SimpleTestCase):
    def test_unreachable_ollama(self):
        with mock.patch("requests.post", side_effect=requests.ConnectionError()):
            with self.assertRaises(AIFailure) as ctx:
                ollama._post("/api/chat", {"model": "m"})
        self.assertIn("Couldn't reach Ollama", str(ctx.exception))
        self.assertIn("http://ollama.test:11434", str(ctx.exception))

    def test_timeout(self):
        with mock.patch("requests.post", side_effect=requests.ReadTimeout()):
            with self.assertRaises(AIFailure) as ctx:
                ollama._post("/api/chat", {"model": "m"})
        self.assertIn("too long", str(ctx.exception))

    def _response(self, status, body):
        response = mock.Mock(ok=status < 400, status_code=status, text=json.dumps(body))
        response.json.return_value = body
        return response

    def test_missing_model_says_how_to_install_it(self):
        with mock.patch("requests.post", return_value=self._response(404, {"error": "model 'qwen2.5:7b' not found"})):
            with self.assertRaises(AIFailure) as ctx:
                ollama._post("/api/chat", {"model": "qwen2.5:7b"})
        self.assertIn("ollama pull qwen2.5:7b", str(ctx.exception))

    def test_model_without_tool_support(self):
        with mock.patch("requests.post", return_value=self._response(400, {"error": "registry.ollama.ai/library/gemma:2b does not support tools"})):
            with self.assertRaises(AIFailure) as ctx:
                ollama._post("/api/chat", {"model": "gemma:2b"})
        self.assertIn("can't call tools", str(ctx.exception))

    def test_request_goes_to_the_configured_url_with_a_long_timeout(self):
        with mock.patch("requests.post", return_value=self._response(200, {"ok": 1})) as post:
            ollama._post("/api/chat", {"model": "m"})
        self.assertEqual(post.call_args.args[0], "http://ollama.test:11434/api/chat")
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 1800))

    def test_status(self):
        tags = self._response(200, {"models": [{"name": "qwen2.5:7b"}, {"name": "llava:latest"}]})
        tags.raise_for_status = lambda: None
        with mock.patch("requests.get", return_value=tags):
            self.assertTrue(ollama.status()["ok"])
            with override_settings(OLLAMA_VISION_MODEL="llava"):
                self.assertTrue(ollama.status()["ok"], "'llava' is installed as llava:latest")
            with override_settings(OLLAMA_VISION_MODEL="qwen2.5vl:7b"):
                result = ollama.status()
        self.assertFalse(result["ok"])
        self.assertIn("ollama pull qwen2.5vl:7b", result["message"])
        with mock.patch("requests.get", side_effect=requests.ConnectionError()):
            self.assertIn("isn't reachable", ollama.status()["message"])


@override_settings(**LOCAL)
class StructuredTests(SimpleTestCase):
    def test_request_shape(self):
        fake = FakeOllama(reply(json.dumps({"a": 1}), prompt=50, out=7))
        with mock.patch("ai_assistant.ollama._post", fake):
            parsed, tokens_in, tokens_out = ollama.structured("sys", "hello", {"type": "object"})
        self.assertEqual((parsed, tokens_in, tokens_out), ({"a": 1}, 50, 7))
        path, payload = fake.calls[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["format"], {"type": "object"})
        self.assertEqual(payload["options"]["num_ctx"], 16384)
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])

    def test_invalid_json_and_cut_off_answers_fail_clearly(self):
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply("not json {"))):
            with self.assertRaises(AIFailure) as ctx:
                ollama.structured("s", "t", {})
        self.assertIn("invalid format", str(ctx.exception))
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply("{}", done_reason="length"))):
            with self.assertRaises(AIFailure) as ctx:
                ollama.structured("s", "t", {})
        self.assertIn("cut off", str(ctx.exception))

    def test_a_prompt_that_filled_the_context_is_rejected_not_trusted(self):
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply("{}", prompt=16384))):
            with self.assertRaises(AIFailure) as ctx:
                ollama.structured("s", "t", {})
        self.assertIn("OLLAMA_NUM_CTX", str(ctx.exception))


@override_settings(**LOCAL)
class ChunkingTests(SimpleTestCase):
    def test_pages_are_grouped_under_the_budget_and_nothing_is_dropped(self):
        pages = [{"page": n, "text": "x" * 100, "image": None} for n in range(1, 6)]
        chunks = ollama.make_chunks(pages, budget=260)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c["text"]) <= 260 for c in chunks))
        joined = "".join(c["text"] for c in chunks)
        self.assertEqual(joined.count("x"), 500)
        for n in range(1, 6):
            self.assertIn(f"--- Page {n} ---", joined)

    def test_one_huge_line_is_split_not_truncated(self):
        chunks = ollama.make_chunks([{"page": 1, "text": "y" * 1000, "image": None}], budget=300)
        self.assertEqual("".join(c["text"] for c in chunks).count("y"), 1000)

    def test_pictures_get_their_own_request(self):
        pages = [{"page": 1, "text": "hello", "image": None}, {"page": 2, "text": "", "image": "AAAA"}, {"page": 3, "text": "bye", "image": None}]
        chunks = ollama.make_chunks(pages, budget=1000)
        self.assertEqual([bool(c["image"]) for c in chunks], [False, True, False])

    def test_merge_joins_sections_by_name(self):
        merged = ollama.merge_drafts([
            {"document_summary": "", "currency": None, "sections": [{"name": "Civil", "items": [{"code": "1"}]}], "issues": [{"message": "a"}]},
            {"document_summary": "BOQ", "currency": "ILS", "sections": [{"name": "Civil", "items": [{"code": "2"}]}, {"name": "Electrical", "items": []}], "issues": []},
        ])
        self.assertEqual([s["name"] for s in merged["sections"]], ["Civil", "Electrical"])
        self.assertEqual([i["code"] for i in merged["sections"][0]["items"]], ["1", "2"])
        self.assertEqual((merged["document_summary"], merged["currency"], len(merged["issues"])), ("BOQ", "ILS", 1))


@override_settings(**LOCAL)
class ReadDocumentTests(SimpleTestCase):
    def test_pdf_text_is_read_in_chunks_and_merged(self):
        upload = pdf_upload("1.1 Concrete works for the foundations, quantity 100 m3", "1.2 Steel reinforcement bars, quantity 40 ton", "1.3 Internal plaster, three coats, 300 m2")
        one = {"document_summary": "s", "currency": None, "sections": [{"name": "Civil", "items": [{"code": "1.1"}]}], "issues": []}
        two = {"document_summary": "", "currency": None, "sections": [{"name": "Civil", "items": [{"code": "1.2"}]}], "issues": []}
        with override_settings(OLLAMA_NUM_CTX=100):   # budget 100 characters: forces one request per page
            fake = FakeOllama(reply(json.dumps(one), prompt=20), reply(json.dumps(two), prompt=20), reply(json.dumps(two), prompt=20))
            with mock.patch("ai_assistant.ollama._post", fake):
                raw, tokens_in, tokens_out = ollama.read_document("boq.pdf", upload, system="S", schema=BOQ_SCHEMA, note="NOTE")
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual((tokens_in, tokens_out), (60, 60))
        self.assertEqual(len(raw["sections"]), 1)
        self.assertEqual(len(raw["sections"][0]["items"]), 3)
        first = fake.payloads[0]
        self.assertEqual(first["format"], BOQ_SCHEMA)
        user = first["messages"][1]["content"]
        self.assertIn("NOTE", user)
        self.assertIn("--- Page 1 ---", user)
        self.assertIn("Concrete works", user)
        self.assertIn("table columns may be out of order", user)

    def test_scanned_pdf_without_a_vision_model_explains_what_to_do(self):
        with self.assertRaises(documents.UnsupportedSource) as ctx:
            ollama.read_document("scan.pdf", pdf_upload(""), system="S", schema={}, note="N")
        self.assertIn("OLLAMA_VISION_MODEL", str(ctx.exception))

    @override_settings(OLLAMA_VISION_MODEL="qwen2.5vl:7b")
    def test_scanned_pages_go_to_the_vision_model_as_pictures(self):
        empty = {"document_summary": "", "currency": None, "sections": [], "issues": []}
        fake = FakeOllama(reply(json.dumps(empty)))
        with mock.patch("ai_assistant.ollama._post", fake):
            ollama.read_document("scan.pdf", pdf_upload(""), system="S", schema=BOQ_SCHEMA, note="N")
        payload = fake.payloads[0]
        self.assertEqual(payload["model"], "qwen2.5vl:7b")
        self.assertEqual(len(payload["messages"][1]["images"]), 1)
        self.assertGreater(len(payload["messages"][1]["images"][0]), 100)

    @override_settings(OLLAMA_VISION_MODEL="qwen2.5vl:7b", OLLAMA_PDF_MODE="images")
    def test_images_mode_reads_every_page_as_a_picture_even_with_text(self):
        empty = {"document_summary": "", "currency": None, "sections": [], "issues": []}
        fake = FakeOllama(reply(json.dumps(empty)), reply(json.dumps(empty)))
        with mock.patch("ai_assistant.ollama._post", fake):
            ollama.read_document("boq.pdf", pdf_upload("plenty of text on page one here", "and more text on page two here"), system="S", schema={}, note="N")
        self.assertEqual([p["model"] for p in fake.payloads], ["qwen2.5vl:7b"] * 2)

    @override_settings(OLLAMA_VISION_MODEL="qwen2.5vl:7b", OLLAMA_MAX_IMAGE_PAGES=1)
    def test_too_many_picture_pages_is_a_clear_error(self):
        with self.assertRaises(documents.UnsupportedSource) as ctx:
            documents.local_pages("scan.pdf", pdf_upload("", ""))
        self.assertIn("OLLAMA_MAX_IMAGE_PAGES", str(ctx.exception))

    def test_images_need_a_vision_model_and_cad_needs_pdf(self):
        with self.assertRaises(documents.UnsupportedSource):
            documents.local_pages("p.png", SimpleUploadedFile("p.png", b"x"))
        with self.assertRaises(documents.UnsupportedSource) as ctx:
            documents.local_pages("plan.dwg", SimpleUploadedFile("plan.dwg", b"x"))
        self.assertIn("PDF", str(ctx.exception))

    def test_csv_is_plain_text(self):
        pages = documents.local_pages("q.csv", SimpleUploadedFile("q.csv", "1.1,بند,10\n".encode()))
        self.assertIn("1.1 | بند | 10", pages[0]["text"])


@override_settings(**LOCAL)
class AgentTests(Base):
    def functions(self, sink=None):
        return make_tools(self.project, sink if sink is not None else {}, include_submit=True, max_chars=llm.tool_result_limit())

    def run_agent(self, fake, **kw):
        with mock.patch("ai_assistant.ollama._post", fake):
            return llm.run_agent(system="SYS", messages=[{"role": "user", "content": "how are we?"}], functions=self.functions(),
                                 max_turns=kw.pop("max_turns", 6), max_tokens=8000, **kw)

    def test_tool_call_then_answer(self):
        fake = FakeOllama(reply(tool_calls=[call("get_health_checks", {})], prompt=200, out=10), reply("All good.", prompt=300, out=5))
        result = self.run_agent(fake)
        self.assertEqual((result.text, result.input_tokens, result.output_tokens), ("All good.", 500, 15))
        first, second = fake.payloads
        self.assertEqual({t["function"]["name"] for t in first["tools"]}, {f.__name__ for f in self.functions()})
        self.assertEqual(first["messages"][0], {"role": "system", "content": "SYS"})
        tool_message = second["messages"][-1]
        self.assertEqual((tool_message["role"], tool_message["tool_name"]), ("tool", "get_health_checks"))
        self.assertIn("BOQ", tool_message["content"])
        self.assertEqual(second["messages"][-2]["tool_calls"][0]["function"]["name"], "get_health_checks")

    def test_arguments_may_arrive_as_a_json_string(self):
        fake = FakeOllama(reply(tool_calls=[call("get_boq", json.dumps({"section": "Civil"}))]), reply("ok"))
        self.assertEqual(self.run_agent(fake).text, "ok")
        self.assertEqual(fake.payloads[1]["messages"][-1]["content"], "[]")

    def test_unknown_tool_and_bad_arguments_are_reported_back_to_the_model(self):
        fake = FakeOllama(reply(tool_calls=[call("delete_everything", {}), call("get_boq", {"section": ["not", "a", "string"]})]), reply("sorry"))
        self.assertEqual(self.run_agent(fake).text, "sorry")
        results = [m["content"] for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
        self.assertIn("no tool called 'delete_everything'", results[0])
        self.assertTrue(results[1].startswith("Error:"))

    def test_stops_after_the_named_tool(self):
        submit = call("submit_review", {"summary": "s", "findings": []})
        fake = FakeOllama(reply(tool_calls=[submit]))
        result = self.run_agent(fake, stop_after="submit_review")
        self.assertEqual(result.text, "")
        self.assertEqual(len(fake.calls), 1)

    def test_runs_out_of_turns_without_looping_forever(self):
        fake = FakeOllama(*[reply(tool_calls=[call("get_health_checks", {})]) for _ in range(3)])
        self.assertEqual(self.run_agent(fake, max_turns=3).text, "")
        self.assertEqual(len(fake.calls), 3)

    def test_local_tool_results_are_capped_to_fit_the_model(self):
        from reports.progress_models import ProjectPhase

        for n in range(50):
            ProjectPhase.objects.create(project=self.project, code=f"1.{n}", name_ar="بند " * 20, weight_percentage=0, order=n, section="S")
        tools = {f.__name__: f for f in make_tools(self.project, {}, include_submit=False, max_chars=2000)}
        text = tools["get_boq"]("S")
        self.assertLess(len(text), 2200)
        self.assertIn("truncated", text)

    def test_the_sdk_is_not_needed_at_all_for_the_provider_switch(self):
        """AI_PROVIDER=ollama must not construct an Anthropic client or ask for a key."""
        with mock.patch("ai_assistant.claude.get_client", side_effect=AssertionError("Claude must not be used")):
            fake = FakeOllama(reply("hi"))
            self.assertEqual(self.run_agent(fake).text, "hi")


@override_settings(**LOCAL)
class LocalReviewAndChatTests(Base):
    def test_review_via_submit_tool(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, created_by=self.admin)
        submit = call("submit_review", {"summary": "Weights are off.", "findings": [
            {"severity": "warning", "area": "BOQ", "title": "Weights", "detail": "d", "action": "a"}]})
        fake = FakeOllama(reply(tool_calls=[call("get_health_checks", {})]), reply(tool_calls=[submit]))
        with mock.patch("ai_assistant.ollama._post", fake):
            result = review_project(run)
        self.assertEqual([f["title"] for f in result["findings"]], ["Weights"])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("health_checks", result)

    def test_review_written_as_plain_text_is_converted_to_the_required_format(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, created_by=self.admin)
        formatted = {"summary": "One issue.", "findings": [{"severity": "error", "area": "Cost", "title": "Over budget", "detail": "d", "action": "a"}]}
        fake = FakeOllama(reply("The project is over budget on item 1.1."), reply(json.dumps(formatted)))
        with mock.patch("ai_assistant.ollama._post", fake):
            result = review_project(run)
        self.assertEqual(result["findings"][0]["title"], "Over budget")
        self.assertEqual(fake.payloads[1]["format"], REVIEW_SCHEMA)
        self.assertIn("over budget on item 1.1", fake.payloads[1]["messages"][1]["content"])

    def test_review_with_no_answer_fails(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.PROJECT_REVIEW, created_by=self.admin)
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply(""))):
            with self.assertRaises(AIFailure):
                review_project(run)

    def test_chat_answer(self):
        fake = FakeOllama(reply(tool_calls=[call("get_cost_summary", {})]), reply("Budget is fine."))
        with mock.patch("ai_assistant.ollama._post", fake):
            result = chat.answer(self.project, [{"role": "user", "content": "budget?"}])
        self.assertEqual(result["reply"], "Budget is fine.")
        self.assertNotIn("submit_review", {t["function"]["name"] for t in fake.payloads[0]["tools"]})

    def test_extraction_end_to_end(self):
        run = AIRun.objects.create(project=self.project, kind=AIRun.BOQ_EXTRACT, created_by=self.admin,
                                   source_file=SimpleUploadedFile("boq.csv", b"1.1,Item,m2,10\n"))
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply(json.dumps(RAW_DRAFT), prompt=900, out=300))):
            draft = extract_boq(run)
        self.assertEqual(draft["totals"], {"sections": 1, "items": 3, "sub_items": 2})
        self.assertEqual((run.input_tokens, run.output_tokens), (900, 300))


@override_settings(**LOCAL)
class LocalViewTests(Base):
    def test_chat_works_without_any_anthropic_key(self):
        self.client.force_login(self.pm)
        config = self.client.get(reverse("ai_assistant:chat_config")).json()
        self.assertTrue(config["configured"])
        self.assertIn("own machine", config["provider"])
        body = json.dumps({"project_id": self.project.pk, "messages": [{"role": "user", "content": "hi"}]})
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply("Hello from the local model."))):
            response = self.client.post(reverse("ai_assistant:chat_message"), body, content_type="application/json")
        self.assertEqual((response.status_code, response.json()), (200, {"reply": "Hello from the local model."}))

    def test_local_errors_reach_the_user_as_readable_messages(self):
        self.client.force_login(self.pm)
        body = json.dumps({"project_id": self.project.pk, "messages": [{"role": "user", "content": "hi"}]})
        with mock.patch("requests.post", side_effect=requests.ConnectionError()):
            response = self.client.post(reverse("ai_assistant:chat_message"), body, content_type="application/json")
        self.assertEqual(response.status_code, 502)
        self.assertIn("Couldn't reach Ollama", response.json()["error"])

    def test_assistant_page_shows_local_privacy_notice_and_status(self):
        self.client.force_login(self.pm)
        with mock.patch("ai_assistant.ollama.status", return_value={"ok": False, "message": "Ollama is down: reachable at X only."}):
            page = self.client.get(reverse("ai_assistant:project_ai", args=[self.project.pk]))
        self.assertContains(page, "documents stay on your own server")
        self.assertContains(page, "Ollama is down: reachable at X only.")
        self.assertNotContains(page, "uploaded to")

    def test_document_run_records_the_local_model(self):
        self.client.force_login(self.pm)
        upload = SimpleUploadedFile("boq.csv", b"1.1,Item,m2,10\n")
        with mock.patch("ai_assistant.ollama._post", FakeOllama(reply(json.dumps(RAW_DRAFT)))):
            self.client.post(reverse("ai_assistant:analyze", args=[self.project.pk]), {"file": upload})
        run = AIRun.objects.get()
        self.assertEqual((run.status, run.model_name), (AIRun.DONE, "qwen2.5:7b"))
