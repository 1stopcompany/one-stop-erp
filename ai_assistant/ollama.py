"""
The local provider: an open model running on the company's own machine through Ollama (https://ollama.com).
Nothing leaves the company and there is no per-use fee. It talks to Ollama's HTTP API directly (`/api/chat`,
`/api/tags`) with `requests`, so it needs no extra package.

Differences from Claude that this module has to handle:
  * Ollama can't take PDFs: `documents.local_pages` turns them into page text or page pictures.
  * Ollama silently cuts off anything longer than the model's context (OLLAMA_NUM_CTX), so long documents are read
    in chunks and merged, and an answer whose prompt filled the context is treated as a failure, not accepted.
  * Small models are weaker at tables and at calling tools; answers are cleaned by the same code as Claude's.
"""
import json
import logging

import requests
from django.conf import settings

from . import documents
from .base import AgentResult, AIFailure

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 2.5      # Arabic tokenises poorly; this errs on the safe side
TEXT_NOTE = (
    "The text below was extracted from a PDF, so table columns may be out of order or run together (for example a unit and a "
    "quantity on one line, or a quantity a few lines away from its item). Use item numbers to keep each line's values together. "
    "If you can't tell which quantity belongs to an item, use null and set confidence to \"low\". Each page starts with a "
    "'--- Page N ---' line; use N as source_page."
)


def is_configured() -> bool:
    return bool(settings.OLLAMA_URL and settings.OLLAMA_MODEL)


def model_name() -> str:
    return settings.OLLAMA_MODEL


def _url(path: str) -> str:
    return settings.OLLAMA_URL + path


def _post(path: str, payload: dict) -> dict:
    """POST to Ollama; every failure becomes an AIFailure whose message says what to do."""
    try:
        response = requests.post(_url(path), json=payload, timeout=(10, settings.OLLAMA_TIMEOUT))
    except requests.ConnectionError:
        raise AIFailure(f"Couldn't reach Ollama at {settings.OLLAMA_URL}. Make sure it is running, or check OLLAMA_URL in the .env file.")
    except requests.Timeout:
        raise AIFailure("The local model took too long to answer. The machine may be too slow for this model: try a smaller model, "
                        "fewer pages, or raise OLLAMA_TIMEOUT.")
    if not response.ok:
        try:
            detail = str(response.json().get("error", ""))
        except ValueError:
            detail = response.text[:200]
        model = payload.get("model", "")
        if response.status_code == 404 or "not found" in detail.lower():
            raise AIFailure(f"The model '{model}' isn't installed in Ollama. Run:  ollama pull {model}")
        if "does not support tools" in detail.lower():
            raise AIFailure(f"The model '{model}' can't call tools, which the chat and review need. Choose a tool-capable model (for example qwen2.5 or llama3.1).")
        if "does not support" in detail.lower() and payload.get("messages") and any(m.get("images") for m in payload["messages"]):
            raise AIFailure(f"The model '{model}' can't read images. Set OLLAMA_VISION_MODEL to a vision model.")
        raise AIFailure(f"Ollama returned an error ({response.status_code}): {detail[:200]}")
    try:
        return response.json()
    except ValueError:
        raise AIFailure("Ollama sent an answer that couldn't be read. Try again.")


def status() -> dict:
    """Is Ollama up and are the configured models installed? Quick (2 s), for the assistant page."""
    try:
        response = requests.get(_url("/api/tags"), timeout=2)
        response.raise_for_status()
        installed = {m.get("name", "") for m in response.json().get("models", [])}
    except Exception:
        return {"ok": False, "message": f"Ollama isn't reachable at {settings.OLLAMA_URL}. Start it, or check OLLAMA_URL in the .env file."}
    wanted = [m for m in (settings.OLLAMA_MODEL, settings.OLLAMA_VISION_MODEL) if m]
    missing = [m for m in wanted if m not in installed and f"{m}:latest" not in installed]
    if missing:
        return {"ok": False, "message": "Ollama is running but these models aren't installed: " + ", ".join(missing)
                + ". Run:  " + "  &&  ".join(f"ollama pull {m}" for m in missing)}
    return {"ok": True, "message": "Ollama is running; models ready: " + ", ".join(wanted) + "."}


def _options(max_tokens: int) -> dict:
    return {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0, "num_predict": max_tokens}


def _chat(model: str, messages: list, *, max_tokens: int, tools=None, schema=None) -> dict:
    payload = {"model": model, "messages": messages, "stream": False, "options": _options(max_tokens)}
    if tools:
        payload["tools"] = tools
    if schema:
        payload["format"] = schema
    reply = _post("/api/chat", payload)
    if reply.get("prompt_eval_count", 0) >= settings.OLLAMA_NUM_CTX - 32:
        raise AIFailure(
            f"The request filled the model's whole working memory (OLLAMA_NUM_CTX={settings.OLLAMA_NUM_CTX}), so part of it was cut off. "
            "Raise OLLAMA_NUM_CTX (needs more memory), or split the document into parts."
        )
    if reply.get("done_reason") == "length":
        raise AIFailure("The local model's answer was cut off. Split the document into smaller parts, or raise OLLAMA_NUM_CTX.")
    return reply


def _usage(reply: dict):
    return reply.get("prompt_eval_count", 0), reply.get("eval_count", 0)


def tool_result_limit() -> int:
    """How many characters one tool result may have: a third of the working memory, so several fit."""
    return max(4000, int(settings.OLLAMA_NUM_CTX * CHARS_PER_TOKEN) // 3)


# ------------------------------------------------------------------ structured answers (reading documents)

def structured(system: str, text: str, schema: dict, *, images=None, model=None, max_tokens: int = 8192):
    """One request whose answer is constrained to `schema`. Returns (parsed dict, input_tokens, output_tokens)."""
    user = {"role": "user", "content": text}
    if images:
        user["images"] = images
    reply = _chat(model or settings.OLLAMA_MODEL, [{"role": "system", "content": system}, user], max_tokens=max_tokens, schema=schema)
    content = (reply.get("message") or {}).get("content", "")
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        logger.warning("Ollama returned invalid JSON: %.300s", content)
        raise AIFailure("The local model's answer couldn't be read (invalid format). Try again, or use a larger model.")
    return parsed, *_usage(reply)


def _split_text(text: str, budget: int) -> list:
    """A page longer than the budget is cut at line breaks (a single over-long line is cut into pieces, nothing is dropped)."""
    pieces, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > budget:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:budget])
            line = line[budget:]
        if current and len(current) + len(line) > budget:
            pieces.append(current)
            current = ""
        current += line
    if current:
        pieces.append(current)
    return pieces


def make_chunks(pages: list, budget: int) -> list:
    """Group pages into requests that fit the model: [{"text", "image"}], text chunks up to `budget` characters, one request per picture."""
    chunks, current = [], ""
    for page in pages:
        if page["image"]:
            if current:
                chunks.append({"text": current, "image": None})
                current = ""
            chunks.append({"text": f"The attached picture is page {page['page']} of the document.", "image": page["image"]})
            continue
        if not page["text"]:
            continue
        for piece in _split_text(f"--- Page {page['page']} ---\n{page['text']}\n", budget):
            if current and len(current) + len(piece) > budget:
                chunks.append({"text": current, "image": None})
                current = ""
            current += piece
    if current:
        chunks.append({"text": current, "image": None})
    return chunks


def merge_drafts(parts: list) -> dict:
    """Combine the per-chunk answers into one raw draft: sections with the same name are joined, issues are concatenated."""
    sections, index, issues = [], {}, []
    for part in parts:
        for section in part.get("sections") or []:
            key = (section.get("name") or "").strip()
            if key not in index:
                index[key] = {"name": section.get("name") or "", "items": []}
                sections.append(index[key])
            index[key]["items"].extend(section.get("items") or [])
        issues.extend(part.get("issues") or [])
    return {
        "document_summary": next((p["document_summary"] for p in parts if p.get("document_summary")), ""),
        "currency": next((p["currency"] for p in parts if p.get("currency")), None),
        "sections": sections,
        "issues": issues,
    }


def merge_takeoffs(parts: list) -> dict:
    """Combine the per-chunk answers of a materials / green-data take-off: lists are concatenated, the first summary wins."""
    return {
        "drawing_summary": next((p["drawing_summary"] for p in parts if p.get("drawing_summary")), ""),
        "items": [i for p in parts for i in p.get("items") or []],
        "green_data": [g for p in parts for g in p.get("green_data") or []],
        "issues": [i for p in parts for i in p.get("issues") or []],
    }


def read_document(name: str, file_obj, *, system: str, schema: dict, note: str, merge=None):
    """Read a document into the schema, in as many requests as its size needs (`merge` combines the parts; default: a BOQ draft).
    Returns (raw dict, input_tokens, output_tokens)."""
    pages = documents.local_pages(name, file_obj)
    chunks = make_chunks(pages, budget=settings.OLLAMA_NUM_CTX)
    if not chunks:
        raise documents.UnsupportedSource("Nothing readable was found in this file.")
    parts, tokens_in, tokens_out = [], 0, 0
    for number, chunk in enumerate(chunks, start=1):
        where = f" (part {number} of {len(chunks)})" if len(chunks) > 1 else ""
        if chunk["image"]:
            if not settings.OLLAMA_VISION_MODEL:
                raise documents.UnsupportedSource("Reading pictures needs OLLAMA_VISION_MODEL to be set in the .env file.")
            text, model, images = f"{note}\n\n{chunk['text']}", settings.OLLAMA_VISION_MODEL, [chunk["image"]]
        else:
            text, model, images = f"{note}\n\n{TEXT_NOTE}\n\n{chunk['text']}", settings.OLLAMA_MODEL, None
        logger.info("Ollama: reading %s%s with %s", name, where, model)
        raw, a, b = structured(system, text, schema, images=images, model=model)
        parts.append(raw)
        tokens_in, tokens_out = tokens_in + a, tokens_out + b
    return (merge or merge_drafts)(parts), tokens_in, tokens_out


# ------------------------------------------------------------------ tool-using conversations (chat, review)

def agent_reply(*, system: str, messages: list, functions: list, max_turns: int, max_tokens: int, stop_after=None) -> AgentResult:
    """
    The conversation with the model calling the given read-only Python functions as tools. Runs the loop here
    (the model asks for a tool, we run it and hand back the result) until it answers in plain text, or
    `stop_after` has been called, or `max_turns` is used up (then the text is empty).
    """
    from anthropic import beta_tool   # only used to turn a documented Python function into a tool description

    tools = {t.name: t for t in (beta_tool(fn) for fn in functions)}
    schemas = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools.values()]
    conversation = [{"role": "system", "content": system}] + [dict(m) for m in messages]
    tokens_in = tokens_out = 0

    for _ in range(max_turns):
        reply = _chat(settings.OLLAMA_MODEL, conversation, max_tokens=max_tokens, tools=schemas)
        a, b = _usage(reply)
        tokens_in, tokens_out = tokens_in + a, tokens_out + b
        message = reply.get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls:
            return AgentResult((message.get("content") or "").strip(), tokens_in, tokens_out)
        conversation.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name, arguments = function.get("name", ""), function.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            if name not in tools:
                result = f"Error: there is no tool called '{name}'. Available: {', '.join(tools)}."
            else:
                try:
                    result = str(tools[name].call(arguments))
                except Exception as exc:  # a bad argument from the model: tell it, let it try again
                    result = f"Error: {exc}"
            conversation.append({"role": "tool", "tool_name": name, "content": result})
            if stop_after and name == stop_after and not result.startswith("Error"):
                return AgentResult("", tokens_in, tokens_out)
    return AgentResult("", tokens_in, tokens_out)
