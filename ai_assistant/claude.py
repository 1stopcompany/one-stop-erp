"""
The Claude (Anthropic cloud) provider: the only module that talks to the Claude API. Callers normally go
through `llm.py`, which picks this or the local Ollama provider; configuration, error messages and token
accounting for Claude are handled here once.
"""
import json
import logging

from django.conf import settings

from .base import AgentResult, AIFailure, AINotConfigured  # noqa: F401  (re-exported: callers use claude.AIFailure)

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", ""))


def model_name() -> str:
    return settings.AI_ASSISTANT_MODEL


def get_client():
    if not is_configured():
        raise AINotConfigured("ANTHROPIC_API_KEY is not set. Add it to the .env file and restart the server.")
    import anthropic

    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=900.0)


def fallback_options() -> dict:
    """
    Optional server-side refusal fallback (see the Claude API docs, "server-side-fallback"): if a request is
    declined by a safety classifier, the API re-runs it on a fallback model. Off unless AI_REFUSAL_FALLBACK=1.
    """
    if getattr(settings, "AI_REFUSAL_FALLBACK", False):
        return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return {}


def friendly_error(exc: Exception) -> str:
    """Turn an SDK exception into a message a project manager can act on."""
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return "The API key was rejected. Check ANTHROPIC_API_KEY in the .env file."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "The API key isn't allowed to use this model or feature."
    if isinstance(exc, anthropic.RateLimitError):
        return "The AI service is busy or the usage limit was reached. Try again in a few minutes."
    if isinstance(exc, anthropic.BadRequestError):
        return f"The AI service rejected the request: {getattr(exc, 'message', exc)}"
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach the AI service. Check the server's internet connection."
    if isinstance(exc, anthropic.APIStatusError):
        return f"The AI service returned an error ({exc.status_code}). Try again later."
    return f"Unexpected error: {exc}"


def structured_reply(client, *, system: str, content: list, schema: dict, max_tokens: int = 64000):
    """
    One request whose answer is constrained to `schema` (JSON). Streams (long documents can take
    minutes) and returns (parsed dict, input_tokens, output_tokens). Raises AIFailure on a refusal,
    a truncated answer or invalid JSON.
    """
    options = {
        "model": model_name(), "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": content}],
        "thinking": {"type": "adaptive"},
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    fallback = fallback_options()
    stream = client.beta.messages.stream(**options, **fallback) if fallback else client.messages.stream(**options)
    with stream as s:
        message = s.get_final_message()

    if message.stop_reason == "refusal":
        raise AIFailure("The AI service declined to read this document.")
    if message.stop_reason == "max_tokens":
        raise AIFailure("The document is too large for one pass: the answer was cut off. Split it into parts (for example one section per file) and try again.")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        logger.warning("AI returned invalid JSON: %.300s", text)
        raise AIFailure("The AI answer couldn't be read (invalid format). Try again.")
    usage = message.usage
    return parsed, usage.input_tokens, usage.output_tokens


def agent_reply(client, *, system: str, messages: list, functions: list, max_turns: int, max_tokens: int, stop_after=None) -> AgentResult:
    """
    A conversation in which Claude may call the given read-only Python functions (the SDK's tool runner
    executes them and feeds results back). Returns the last text. Raises AIFailure on a refusal.
    `stop_after` is only used by the local provider (the runner ends when the model stops calling tools).
    """
    from anthropic import beta_tool

    runner = client.beta.messages.tool_runner(
        model=model_name(), max_tokens=max_tokens, system=system, tools=[beta_tool(fn) for fn in functions],
        messages=messages, thinking={"type": "adaptive"}, max_iterations=max_turns,
    )
    tokens_in = tokens_out = 0
    last = None
    for message in runner:
        tokens_in += message.usage.input_tokens
        tokens_out += message.usage.output_tokens
        if message.stop_reason == "refusal":
            raise AIFailure("The AI service declined that request.")
        last = message
    text = "\n".join(b.text for b in (last.content if last else []) if getattr(b, "type", "") == "text").strip()
    return AgentResult(text, tokens_in, tokens_out)
