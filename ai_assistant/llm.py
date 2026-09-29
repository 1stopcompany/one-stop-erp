"""
The provider switch. Everything else in the app (extraction, review, chat, views) calls this module and never
knows whether the work is done by Claude in Anthropic's cloud (AI_PROVIDER=anthropic, the default) or by an open
model running on the company's own machine through Ollama (AI_PROVIDER=ollama).
"""
from django.conf import settings

from . import claude, ollama
from .base import AgentResult, AIFailure, AINotConfigured  # noqa: F401  (re-exported for callers)
from .documents import content_blocks

# The size cap for one tool result sent to Claude; local models get less (see ollama.tool_result_limit).
CLOUD_TOOL_RESULT_LIMIT = 60000


def is_local() -> bool:
    return settings.AI_PROVIDER == "ollama"


def is_configured() -> bool:
    return ollama.is_configured() if is_local() else claude.is_configured()


def model_name() -> str:
    return ollama.model_name() if is_local() else claude.model_name()


def describe() -> dict:
    """What the pages show the user about who does the work."""
    if is_local():
        return {"provider": "ollama", "local": True, "label": f"Ollama on your own machine ({model_name()})", "model": model_name()}
    return {"provider": "anthropic", "local": False, "label": f"Claude in Anthropic's cloud ({model_name()})", "model": model_name()}


def setup_hint() -> str:
    """What to do when the assistant isn't set up (shown to users)."""
    if is_local():
        return "The local AI isn't set up: check OLLAMA_URL and OLLAMA_MODEL in the .env file and make sure Ollama is running."
    return "The AI assistant isn't switched on yet: an admin needs to add ANTHROPIC_API_KEY to the .env file and restart the server."


def status():
    """For the assistant page: None for Claude, or {"ok", "message"} for the local provider (is Ollama up, are the models installed)."""
    return ollama.status() if is_local() else None


def friendly_error(exc: Exception) -> str:
    return f"Unexpected error: {exc}" if is_local() else claude.friendly_error(exc)


def tool_result_limit() -> int:
    return ollama.tool_result_limit() if is_local() else CLOUD_TOOL_RESULT_LIMIT


# ------------------------------------------------------------------ the three things the app asks an AI to do

def read_document(name, file_obj, *, system, schema, note, client=None, merge=None):
    """Read a document into `schema`. `merge` (local provider only) combines the answers for the parts of a long document.
    Returns (raw dict, input_tokens, output_tokens)."""
    if is_local():
        return ollama.read_document(name, file_obj, system=system, schema=schema, note=note, merge=merge)
    blocks = content_blocks(name, file_obj) + [{"type": "text", "text": note}]
    return claude.structured_reply(client or claude.get_client(), system=system, content=blocks, schema=schema)


def structured(system, text, schema, client=None):
    """Turn plain text into `schema` (used to format an agent's free-text notes). Returns (raw dict, input_tokens, output_tokens)."""
    if is_local():
        return ollama.structured(system, text, schema)
    return claude.structured_reply(client or claude.get_client(), system=system, content=[{"type": "text", "text": text}], schema=schema)


def run_agent(*, system, messages, functions, max_turns, max_tokens, stop_after=None, client=None) -> AgentResult:
    """A conversation in which the AI may call the given read-only functions as tools."""
    if is_local():
        return ollama.agent_reply(system=system, messages=messages, functions=functions, max_turns=max_turns,
                                  max_tokens=min(max_tokens, 4096), stop_after=stop_after)
    return claude.agent_reply(client or claude.get_client(), system=system, messages=messages, functions=functions,
                              max_turns=max_turns, max_tokens=max_tokens, stop_after=stop_after)
