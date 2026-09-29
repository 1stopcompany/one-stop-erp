"""Small types shared by the AI providers (Claude in the cloud, Ollama on the company's own machine)."""
from dataclasses import dataclass


class AINotConfigured(Exception):
    """The chosen AI provider isn't set up, so the AI features can't run."""


class AIFailure(Exception):
    """The provider was reached (or tried) and didn't produce a usable answer; the message is safe to show a user."""


@dataclass
class AgentResult:
    """What a tool-using conversation ended with: the assistant's last text and the tokens it took."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
