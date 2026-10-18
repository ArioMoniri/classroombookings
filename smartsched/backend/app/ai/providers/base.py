"""Provider-neutral types of the AI gateway (wave 3 W3-AI).

The AI layer speaks one request shape: the Anthropic Messages API keyword arguments that
:class:`app.ai.client.AIClient` builds (``model``, ``max_tokens``, ``system``, ``messages`` with typed content
blocks, ``tools`` with ``input_schema`` / ``strict``, ``tool_choice``, ``output_config`` with ``format`` and
``effort``). Every adapter takes that shape and answers a message object with the same attribute surface as the
Anthropic SDK's ``Message`` (``content`` blocks of type ``text`` / ``tool_use``, ``stop_reason``, ``usage``,
``model``), so ``chat.py``, ``elicit.py``, ``ingest.py``, the council and the explain paths do not change with the
provider. The Anthropic adapter returns the SDK's own objects; the others return :class:`GMessage`.

``stop_reason`` is normalised to ``end_turn`` / ``tool_use`` / ``max_tokens`` / ``refusal``. A provider's own
safety block (OpenAI ``content_filter``, Gemini ``SAFETY``) is a ``refusal``.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

EventSink = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class GBlock:
    """A content block (``text`` or ``tool_use``) with the SDK block's attributes."""

    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, **_: Any) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text}
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class GUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class GStopDetails:
    category: str | None = None
    explanation: str | None = None


@dataclass
class GMessage:
    content: list[GBlock]
    stop_reason: str = "end_turn"
    model: str = ""
    usage: GUsage = field(default_factory=GUsage)
    stop_details: GStopDetails | None = None
    _request_id: str | None = None
    #: the ``tool_use`` was built by the OpenAI-compatible adapter from a JSON-schema answer (HB-13 emulation), not
    #: chosen by the server: the probe does not count it as an honoured ``tool_choice`` (HB-17 bug 4)
    emulated: bool = False


@dataclass
class ModelInfo:
    """One model a provider lists (``POST /ai/admin/providers/{p}/sync``)."""

    id: str
    display_name: str = ""
    created_at: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    #: USD per 1M tokens when the provider publishes it (OpenRouter) or the admin entered it
    price_in: float | None = None
    price_out: float | None = None
    #: what the model does (VO-01): ``text`` | ``stt`` (speech to text) | ``tts``; filled at sync
    #: (:func:`app.ai.voice.registry.model_modalities`)
    modalities: list[str] | None = None
    #: what the model can do (HB-12, :mod:`app.ai.capabilities`): ``{tools, tool_choice, strict_tools, json_schema,
    #: vision, pdf, context_window, parallel_tools, source, checked_at}``; ``None`` per field = unknown
    capabilities: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")} | {"id": self.id}


class ProviderError(RuntimeError):
    """A provider failure, already reduced to a short text without upstream bodies or keys."""

    #: the HTTP status the server answered with, when there was one (the probe treats a 5xx as "unknown", HB-F bug D)
    status: int | None = None


class ProviderUnsupported(ProviderError):
    """The request uses something this provider cannot express (a PDF document block, vision on a text model)."""


class ProviderAdapter(ABC):
    """One provider. ``create`` / ``stream`` take Anthropic-shaped kwargs; ``list_models`` backs the sync."""

    #: provider id (``anthropic`` | ``openai`` | ``azure_openai`` | ``openrouter`` | ``openai_compatible`` |
    #: ``gemini`` | ``bedrock``)
    name: str = ""
    #: the route model's capability record (HB-12/13), set by the gateway before a call; ``None`` = unknown. The
    #: OpenAI-compatible adapter uses it to pick named tool choice / JSON-schema emulation / PDF rasterising.
    capabilities: dict[str, Any] | None = None

    @abstractmethod
    async def create(self, kwargs: dict[str, Any]) -> Any: ...

    async def stream(self, kwargs: dict[str, Any], on_event: EventSink | None) -> Any:
        """Default: one non-streamed call, replayed as events (a text delta per text block, a ``tool_start`` per
        tool call), so the chat stream works on every provider."""
        message = await self.create(kwargs)
        if on_event is not None:
            for block in message.content:
                if block.type == "text" and block.text:
                    await on_event({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    await on_event({"type": "tool_start", "name": block.name})
        return message

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    async def sniff(self, models: list[ModelInfo]) -> str | None:
        """Add server-specific capability facts to ``models`` (HB-12). Returns the detected server kind; the
        default knows nothing more than the model list."""
        return None

    def translate_error(self, exc: Exception, model: str) -> Exception:
        """Map a transport / SDK error to a short :class:`ProviderError`; unknown exceptions come back unchanged."""
        return exc


# ---------------------------------------------------------------------------------------------- shared helpers


def system_text(system: str | list[dict[str, Any]] | None) -> str:
    """Anthropic ``system`` (a string or text blocks with ``cache_control``) -> one string."""
    if not system:
        return ""
    if isinstance(system, str):
        return system
    return "\n\n".join(str(b.get("text") or "") for b in system if isinstance(b, dict) and b.get("type") == "text")


def block_dict(block: Any) -> dict[str, Any]:
    """A content block (dict or SDK object) as a dict."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        dumped = block.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return {"type": getattr(block, "type", ""), "text": getattr(block, "text", "")}


def content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block_dict(b) for b in (content or [])]


def tool_result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    parts = [str(c.get("text") or "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(parts)


def output_schema(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    fmt = (kwargs.get("output_config") or {}).get("format")
    if isinstance(fmt, dict) and fmt.get("type") == "json_schema":
        schema = fmt.get("schema")
        return schema if isinstance(schema, dict) else None
    return None


#: key of the tool input a provider sent as broken JSON (HB-13): the strict schema check of the caller refuses it,
#: so chat answers the model with an ``INVALID_JSON`` tool result instead of failing the whole call
INVALID_INPUT_KEY = "_invalid"


def tool_input(raw: Any) -> dict[str, Any]:
    """Tool-call arguments as an object; unreadable arguments become ``{"_invalid": <first 500 chars>}``."""
    try:
        return parse_json_object(raw)
    except ProviderError:
        return {INVALID_INPUT_KEY: str(raw if raw is not None else "")[:500]}


def parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError) as exc:
        raise ProviderError("the model sent a tool call whose arguments are not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProviderError("the model sent tool arguments that are not a JSON object")
    return data


__all__ = [
    "INVALID_INPUT_KEY",
    "EventSink",
    "GBlock",
    "GMessage",
    "GStopDetails",
    "GUsage",
    "ModelInfo",
    "ProviderAdapter",
    "ProviderError",
    "ProviderUnsupported",
    "block_dict",
    "content_blocks",
    "output_schema",
    "parse_json_object",
    "system_text",
    "tool_input",
    "tool_result_text",
]
