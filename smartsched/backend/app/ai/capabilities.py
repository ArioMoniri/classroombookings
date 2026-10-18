"""What a model can do: capability detection at sync, the active probe at "Test", admin overrides, and the per-feature
needs that route validation enforces (HB-12; docs/research/2026-10-17-ai-helper-architecture.md §5.8).

A capability record (stored on each synced model as ``capabilities``)::

    {tools, tool_choice, strict_tools, json_schema, vision, pdf, context_window, parallel_tools, source, checked_at}

plus ``context_verified`` once a layer has said where its ``context_window`` comes from: ``True`` when it is the
window the server actually serves (Ollama ``GET /api/ps`` ``context_length`` or a ``num_ctx`` parameter, an admin
override), ``False`` when it is only the model's maximum (an Ollama model that was not loaded at sync). ``False``
warns ``context_unverified`` on the route and the provider card until the probe reads the served window (HB-17
bug 2: Ollama serves ``OLLAMA_CONTEXT_LENGTH``, often half the maximum, and silently drops the system prompt of a
longer prompt).

``True`` / ``False`` are facts, ``None`` is unknown. ``pdf`` means *this gateway can send a PDF document block to the
model*: it is ``False`` for every OpenAI-compatible server (the adapter rasterises the pages to PNG instead, HB-13).

Three layers, later ones win per field (a ``None`` never overwrites a fact):

1. **sync** (``source: provider``): Claude providers know everything; OpenAI / Azure / OpenRouter come from the model
   list; an ``openai_compatible`` server is sniffed with safe requests on the same host, through the same
   ``url_guard`` check as every call (:meth:`app.ai.providers.openai_compat.OpenAICompatAdapter.sniff`);
2. **probe** (``source: probe``, ``POST /ai/admin/providers/{p}/test?probe=true``, metered as ``test``): a forced
   single-tool call (an ``auto`` retry when it is not honoured), a JSON-schema call and a 32×32 image, at most
   :data:`PROBE_MAX_TOKENS` output tokens each (:func:`probe`); a call that proves nothing (cut off at ``max_tokens``
   with no content, a lost connection, a timeout, a 5xx) leaves its capabilities ``None``, so sync's value stands;
3. **admin** (``source: admin``, audited ``ai.provider.capabilities``): for servers that hide what they can do.

:func:`route_issues` turns the per-feature needs into route errors (``model_lacks_capability``,
``context_too_small``) and warnings (``capability_unknown``): a fact refuses, an unknown only warns.
"""

from __future__ import annotations

import base64
import inspect
import json
import re
import struct
import zlib
from datetime import UTC, datetime
from typing import Any

import httpx

BOOL_KEYS = ("tools", "tool_choice", "strict_tools", "json_schema", "vision", "pdf", "parallel_tools")
CAP_KEYS = (*BOOL_KEYS, "context_window")
SOURCES = ("provider", "probe", "admin")

#: Claude on the Anthropic API, Bedrock and Vertex: every capability (context from the model list when given)
CLAUDE_CONTEXT = 200_000


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def empty() -> dict[str, Any]:
    return {k: None for k in CAP_KEYS}


def record(source: str = "provider", **values: Any) -> dict[str, Any]:
    """A capability record with ``source`` and ``checked_at``; unknown keys are dropped."""
    out = empty()
    for k, v in values.items():
        if k in BOOL_KEYS:
            out[k] = None if v is None else bool(v)
        elif k == "context_window":
            out[k] = _int(v)
        elif k == "context_verified" and v is not None:
            out[k] = bool(v)
    out["source"] = source if source in SOURCES else "provider"
    out["checked_at"] = now_iso()
    return out


def _int(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def merge(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """Later layers win per field; ``None`` never overwrites a known value. ``source`` / ``checked_at`` are those
    of the last layer that contributed a value. ``context_verified`` travels with ``context_window``: the layer
    that sets the window says whether it is the served one (an admin's window counts as known)."""
    out = empty()
    out["source"] = None
    out["checked_at"] = None
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        contributed = False
        for k in CAP_KEYS:
            v = layer.get(k)
            if v is None:
                continue
            out[k] = _int(v) if k == "context_window" else bool(v)
            contributed = True
            if k == "context_window":
                verified = layer.get("context_verified")
                if verified is None and layer.get("source") == "admin":
                    verified = True
                if verified is None:
                    out.pop("context_verified", None)
                else:
                    out["context_verified"] = bool(verified)
        if contributed:
            out["source"] = layer.get("source") or out["source"]
            out["checked_at"] = layer.get("checked_at") or out["checked_at"]
    return out


def is_known(caps: dict[str, Any] | None) -> bool:
    return isinstance(caps, dict) and any(caps.get(k) is not None for k in CAP_KEYS)


# ---------------------------------------------------------------------------------------------- at sync


def claude(context_window: int | None = None) -> dict[str, Any]:
    return record(
        tools=True,
        tool_choice=True,
        strict_tools=True,
        json_schema=True,
        vision=True,
        pdf=True,
        parallel_tools=True,
        context_window=context_window or CLAUDE_CONTEXT,
    )


def _openai_vision(model: str) -> bool | None:
    m = model.lower().rsplit("/", 1)[-1]
    if m.startswith(("gpt-4o", "gpt-4.1", "gpt-5", "o3", "o4")):
        return True
    if m.startswith(("gpt-3.5", "text-", "davinci", "babbage")):
        return False
    return None


def openai_cloud(model: str, context_window: int | None = None) -> dict[str, Any]:
    """OpenAI / Azure OpenAI chat models: tools, named tool choice, strict schemas and JSON schema are the API's."""
    return record(
        tools=True,
        tool_choice=True,
        strict_tools=True,
        json_schema=True,
        vision=_openai_vision(model),
        pdf=False,
        parallel_tools=True,
        context_window=context_window,
    )


def openrouter(entry: dict[str, Any]) -> dict[str, Any]:
    """OpenRouter publishes ``supported_parameters``, ``architecture.input_modalities`` and ``context_length``."""
    params = {str(p) for p in entry.get("supported_parameters") or []}
    mods = {str(m) for m in ((entry.get("architecture") or {}).get("input_modalities") or [])}
    known = bool(params)
    return record(
        tools=("tools" in params) if known else None,
        tool_choice=("tool_choice" in params) if known else None,
        strict_tools=("structured_outputs" in params) if known else None,
        json_schema=("structured_outputs" in params or "response_format" in params) if known else None,
        vision=("image" in mods) if mods else None,
        pdf=False,
        parallel_tools=("parallel_tool_calls" in params) if known else None,
        context_window=entry.get("context_length"),
    )


def vllm(entry: dict[str, Any]) -> dict[str, Any]:
    """vLLM's ``/v1/models`` carries ``max_model_len``. Named tool choice and JSON schema use its structured-output
    backend (always on); plain ``tools`` need ``--enable-auto-tool-choice`` and a parser, so they stay unknown."""
    return record(
        tool_choice=True,
        strict_tools=True,
        json_schema=True,
        pdf=False,
        context_window=entry.get("max_model_len"),
    )


def ollama_maximum(show: dict[str, Any] | None) -> int | None:
    """The model's own maximum context from ``POST /api/show`` (``model_info.<arch>.context_length``)."""
    ctx: int | None = None
    for k, v in ((show or {}).get("model_info") or {}).items():
        if str(k).endswith(".context_length"):
            ctx = _int(v)
    return ctx


def ollama_served(ps: dict[str, Any] | None, model: str) -> int | None:
    """The window Ollama serves a loaded model with: ``GET /api/ps`` ``models[].context_length`` (it follows
    ``OLLAMA_CONTEXT_LENGTH`` / ``num_ctx``, not the model's maximum). ``None`` while the model is not loaded."""
    names = {model, model if ":" in model else f"{model}:latest"}
    for entry in (ps or {}).get("models") or []:
        if isinstance(entry, dict) and {str(entry.get("name")), str(entry.get("model"))} & names:
            return _int(entry.get("context_length"))
    return None


def smaller(*windows: int | None) -> int | None:
    known = [w for w in windows if isinstance(w, int) and w > 0]
    return min(known) if known else None


def ollama(show: dict[str, Any], served: int | None = None) -> dict[str, Any]:
    """Ollama ``POST /api/show``: ``capabilities`` (``completion``, ``tools``, ``vision``, …) and
    ``model_info.<arch>.context_length`` (the model's maximum). Ollama has no ``tool_choice`` and does not enforce
    ``strict``; its JSON ``format`` is grammar-constrained. The window actually served is ``served`` (``GET /api/ps``
    ``context_length`` of the loaded model) or a ``num_ctx`` in the model's parameters; the record keeps the
    smaller of that and the maximum, and ``context_verified: False`` while neither is known."""
    caps = {str(c) for c in show.get("capabilities") or []}
    maximum = ollama_maximum(show)
    param: int | None = None
    for line in str(show.get("parameters") or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "num_ctx":
            param = _int(parts[1])
    known = served or param
    ctx = smaller(maximum, known)
    return record(
        tools=("tools" in caps) if caps else None,
        tool_choice=False,
        strict_tools=False,
        json_schema=True,
        vision=("vision" in caps) if caps else None,
        pdf=False,
        parallel_tools=False,
        context_window=ctx,
        context_verified=(known is not None) if ctx else None,
    )


def lmstudio(entry: dict[str, Any]) -> dict[str, Any]:
    """LM Studio ``GET /api/v0/models``: ``type`` (``llm`` / ``vlm`` / ``embeddings``), ``capabilities``
    (``tool_use``) and ``max_context_length``; structured output is supported."""
    caps = {str(c) for c in entry.get("capabilities") or []}
    kind = str(entry.get("type") or "")
    return record(
        tools="tool_use" in caps,
        json_schema=kind != "embeddings",
        vision=kind == "vlm" if kind else None,
        pdf=False,
        context_window=entry.get("loaded_context_length") or entry.get("max_context_length"),
    )


def llamacpp(props: dict[str, Any]) -> dict[str, Any]:
    """llama.cpp server ``GET /props``: ``default_generation_settings.n_ctx`` (or ``n_ctx``), the chat template's
    capabilities (``chat_template_caps.supports_tools``, needs ``--jinja``) and ``modalities.vision``."""
    settings = props.get("default_generation_settings") or {}
    ctx = settings.get("n_ctx") or props.get("n_ctx")
    tcaps = props.get("chat_template_caps") or {}
    mods = props.get("modalities") or {}
    tools = tcaps.get("supports_tools") if isinstance(tcaps, dict) and "supports_tools" in tcaps else None
    parallel = tcaps.get("supports_parallel_tool_calls") if isinstance(tcaps, dict) else None
    return record(
        tools=tools,
        json_schema=True,
        vision=mods.get("vision") if isinstance(mods, dict) and "vision" in mods else None,
        pdf=False,
        parallel_tools=parallel,
        context_window=ctx,
    )


def gemini(context_window: int | None = None) -> dict[str, Any]:
    return record(
        tools=True,
        tool_choice=True,
        json_schema=True,
        vision=True,
        pdf=True,
        parallel_tools=True,
        context_window=context_window,
    )


def for_listing(provider: str, model_id: str, raw: dict[str, Any] | None, context_window: int | None) -> dict[str, Any]:
    """The sync-time record of one listed model (the ``openai_compatible`` sniff adds its layer afterwards)."""
    if provider in ("anthropic", "bedrock", "vertex"):
        return claude(context_window)
    if provider in ("openai", "azure_openai"):
        return openai_cloud(model_id, context_window)
    if provider == "openrouter":
        return openrouter(raw or {})
    if provider == "gemini":
        return gemini(context_window)
    if provider == "openai_compatible" and raw and raw.get("max_model_len"):
        return vllm(raw)
    return record(pdf=False, context_window=context_window)


# ---------------------------------------------------------------------------------------------- feature needs

#: per feature: capability groups (any-of inside a group, every group needed) and the smallest context window
NEEDS: dict[str, dict[str, Any]] = {
    "chat": {"all": [("tools",)], "context": 16_000},
    "helper": {"all": [("tools", "json_schema")], "context": 8_000, "warn_if_false": ("tools",)},
    "rules": {"all": [("tools", "json_schema")]},
    "intake": {"all": [("tools", "json_schema")]},
    "vision": {"all": [("vision",), ("tools", "json_schema")]},
    "explain": {"all": [], "warn_if_false": ("json_schema",)},
    "booking_nl": {"all": [("tools", "json_schema")]},
    "guard": {"all": [("json_schema",)]},
}

_LABEL = {
    "tools": ("araç çağırma", "tool calling"),
    "json_schema": ("JSON şemalı yanıt", "JSON-schema output"),
    "vision": ("görüntü okuma", "image input"),
    "tool_choice": ("araç seçimi", "tool choice"),
}
_FEATURE = {
    "chat": ("sohbet", "chat"),
    "helper": ("yardımcı", "the helper"),
    "rules": ("metinden kural", "rules from text"),
    "intake": ("dosyadan aktarım", "file intake"),
    "vision": ("taranmış belge", "scans"),
    "explain": ("açıklamalar", "explanations"),
    "booking_nl": ("doğal dille rezervasyon", "plain-language bookings"),
    "guard": ("kapsam denetimi", "the scope check"),
}


def _lack_text(feature: str, group: tuple[str, ...]) -> tuple[str, str]:
    ftr, fen = _FEATURE.get(feature, (feature, feature))
    if group == ("tools",):
        return (
            f"Bu model araç çağırmayı desteklemiyor; {ftr} için araç destekli bir model seçin.",
            f"This model cannot call tools; choose a model with tool calling for {fen}.",
        )
    names_tr = " ya da ".join(_LABEL.get(c, (c, c))[0] for c in group)
    names_en = " or ".join(_LABEL.get(c, (c, c))[1] for c in group)
    return (
        f"Bu model {names_tr} desteklemiyor; {ftr} için bunu destekleyen bir model seçin.",
        f"This model does not support {names_en}; choose a model that does for {fen}.",
    )


def route_issues(feature: str | None, caps: dict[str, Any] | None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """``(errors, warnings)`` of routing ``feature`` to a model with ``caps`` (field ``model``; the caller renames
    it for the fallback). A capability that is ``False`` refuses; ``None`` warns until it is probed."""
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    need = NEEDS.get(feature or "")
    if need is None:
        return errors, warnings
    c = caps or {}

    def add(target: list[dict[str, str]], code: str, tr: str, en: str, **extra: str) -> None:
        target.append({"field": "model", "code": code, "message_tr": tr, "message_en": en, **extra})

    for group in need["all"]:
        values = [c.get(k) for k in group]
        if any(v is True for v in values):
            continue
        if all(v is False for v in values):
            tr, en = _lack_text(feature or "", tuple(group))
            add(errors, "model_lacks_capability", tr, en, capability="|".join(group))
        else:
            add(
                warnings,
                "capability_unknown",
                "Bu modelin yetenekleri bilinmiyor; Test düğmesiyle sınayın (yoklama).",
                "This model's capabilities are unknown; run Test with the probe.",
                capability="|".join(group),
            )
    for k in need.get("warn_if_false", ()):
        if c.get(k) is False and not errors:
            if feature == "helper":
                tr = "Bu model araç çağıramıyor; yardımcı yalnızca dizinden (Rehber modu) yanıt verecek."
                en = "This model cannot call tools; the helper will answer from the index only (guide mode)."
            else:
                tr = "Bu model JSON şemalı yanıt veremiyor; açıklamalar hazır şablonla gösterilecek."
                en = "This model cannot answer in JSON schema; explanations fall back to the template."
            add(warnings, "capability_degraded", tr, en, capability=k)
    floor = int(need.get("context") or 0)
    window = c.get("context_window")
    if floor and isinstance(window, int) and c.get("context_verified") is False:
        add(warnings, "context_unverified", *unverified_text(window))
    if floor and isinstance(window, int) and window < floor:
        add(
            errors,
            "context_too_small",
            f"Bu modelin bağlam penceresi ({window} jeton) bu özellik için küçük; en az {floor} jeton gerekir. "
            "Yerel sunucuda bağlamı büyütün (ör. OLLAMA_CONTEXT_LENGTH).",
            f"This model's context window ({window} tokens) is too small for this feature; it needs at least "
            f"{floor}. Raise the context on the local server (e.g. OLLAMA_CONTEXT_LENGTH).",
        )
    return errors, warnings


def unverified_text(window: int | None, model: str | None = None) -> tuple[str, str]:
    """``context_unverified`` in Turkish and English (the route warning and the provider card)."""
    name_tr = f"{model} için " if model else ""
    name_en = f" for {model}" if model else ""
    return (
        f"Yerel sunucunun {name_tr}gerçekten sunduğu bağlam penceresi henüz bilinmiyor; şimdilik modelin üst sınırı "
        f"({window} jeton) kullanılıyor. Modeli bir kez yükleyip Test düğmesiyle (yoklama) sınayın.",
        f"The context window the local server actually serves{name_en} is not known yet; the model's maximum "
        f"({window} tokens) is used for now. Load the model once and run Test with the probe.",
    )


# ---------------------------------------------------------------------------------------------- at call time (HB-13)

#: rough tokens of one image / one PDF page as a vision model reads it (Claude ~1 600 for a full page; Qwen-VL and
#: LLaVA tile smaller): the estimate errs high so a small local window is refused before it overflows
IMAGE_TOKENS = 1_600
#: the answer must have at least this many tokens of room, else the call is ``context_too_small``
MIN_OUTPUT_TOKENS = 512
_PAGE = re.compile(rb"/Type\s*/Page(?![s\w])")


def _pdf_pages(b64: str) -> int:
    try:
        raw = base64.standard_b64decode(b64 or "")
    except ValueError:
        return 1
    return max(len(_PAGE.findall(raw)), 1)


def _media_tokens(block: dict[str, Any]) -> tuple[int, int]:
    """``(text chars, media tokens)`` of one content block (a base64 payload is never counted as text)."""
    kind = block.get("type")
    if kind == "image":
        return 0, IMAGE_TOKENS
    if kind == "document":
        src = block.get("source") or {}
        if src.get("type") == "text":
            return len(str(src.get("data") or "")), 0
        if src.get("type") == "base64":
            return 0, IMAGE_TOKENS * _pdf_pages(str(src.get("data") or ""))
        return 0, IMAGE_TOKENS
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, list):
            chars = tokens = 0
            for b in content:
                c, t = _media_tokens(b) if isinstance(b, dict) else (len(str(b)), 0)
                chars, tokens = chars + c, tokens + t
            return chars, tokens
        return len(str(content or "")), 0
    if kind == "text":
        return len(str(block.get("text") or "")), 0
    return len(json.dumps(block, ensure_ascii=False, default=str)), 0


def estimate_input_tokens(kwargs: dict[str, Any]) -> int:
    """A deliberately high estimate of the prompt (system + messages + tool schemas): 1 token per 3 characters of
    text (Turkish runs longer than English) and :data:`IMAGE_TOKENS` per image or PDF page."""
    from app.ai.providers.base import block_dict, system_text

    chars = len(system_text(kwargs.get("system")))
    media = 0
    for msg in kwargs.get("messages") or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            chars += len(content)
            continue
        for b in content or []:
            c, t = _media_tokens(block_dict(b))
            chars, media = chars + c, media + t
    if kwargs.get("tools"):
        chars += len(json.dumps(kwargs["tools"], ensure_ascii=False, default=str))
    return chars // 3 + media + 16 * len(kwargs.get("messages") or [])


def fit_context(caps: dict[str, Any] | None, kwargs: dict[str, Any], max_tokens: int) -> int | None:
    """``max_tokens`` clamped to what is left of the model's context window after the prompt; ``None`` when not even
    :data:`MIN_OUTPUT_TOKENS` are left (``context_too_small``). An unknown window keeps ``max_tokens``."""
    window = (caps or {}).get("context_window")
    if not isinstance(window, int) or window <= 0:
        return max_tokens
    room = window - estimate_input_tokens(kwargs) - max(window // 50, 64)
    if room < min(MIN_OUTPUT_TOKENS, max_tokens or MIN_OUTPUT_TOKENS):
        return None
    return min(max_tokens, room) if max_tokens else room


def call_issue(caps: dict[str, Any] | None, kwargs: dict[str, Any]) -> str | None:
    """A request the model is *known* not to handle (a ``False`` fact; unknown never refuses): tools on a model
    without tool calling (a forced single tool still works through JSON-schema emulation unless that is known to
    fail too), or an image on a model without vision. Returns ``model_lacks_capability`` or ``None``."""
    c = caps or {}
    if kwargs.get("tools") and c.get("tools") is False:
        choice = kwargs.get("tool_choice") or {}
        if choice.get("type") != "tool" or c.get("json_schema") is False:
            return "model_lacks_capability"
    if c.get("vision") is False:
        for msg in kwargs.get("messages") or []:
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "image" for b in content):
                return "model_lacks_capability"
    return None


# ---------------------------------------------------------------------------------------------- probe


def _png(size: int = 32, rgb: tuple[int, int, int] = (220, 20, 20)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


RED_PNG_B64 = base64.standard_b64encode(_png()).decode()
PROBE_TOOL: dict[str, Any] = {
    "name": "report_colour",
    "description": "Report a colour name and a count.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"colour": {"type": "string", "enum": ["red", "green", "blue"]}, "count": {"type": "integer"}},
        "required": ["colour", "count"],
        "additionalProperties": False,
    },
}
PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class ProbeUsage:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def add(self, message: Any) -> None:
        usage = getattr(message, "usage", None)
        self.calls += 1
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)


def _tool_calls(message: Any, name: str) -> list[Any]:
    blocks = getattr(message, "content", None) or []
    return [b for b in blocks if getattr(b, "type", "") == "tool_use" and b.name == name]


def _text(message: Any) -> str:
    return "".join(
        str(getattr(b, "text", "") or "") for b in getattr(message, "content", None) or [] if b.type == "text"
    )


def _valid(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and set(data) == {"colour", "count"}
        and data.get("colour") in {"red", "green", "blue"}
        and isinstance(data.get("count"), int)
        and not isinstance(data.get("count"), bool)
    )


#: output tokens per probe call (HB-F bug A): a thinking model (qwen3, Qwen3.5, reasoning models on vLLM) reasons
#: before it answers and stopped at ``length`` with no tool call under the old 64
PROBE_MAX_TOKENS = 512


def _cut_off(message: Any) -> bool:
    """A ``max_tokens`` stop with no content (no text, no tool call): the model ran out of room while thinking, which
    proves nothing about what it can do (HB-F bug A)."""
    if getattr(message, "stop_reason", None) != "max_tokens":
        return False
    blocks = getattr(message, "content", None) or []
    return not _text(message).strip() and not any(getattr(b, "type", "") == "tool_use" for b in blocks)


def _unreached(exc: BaseException) -> bool:
    """A failure that says nothing about the model (HB-F bug D): the connection was lost, the call timed out or the
    server answered 5xx. A 4xx (a rejected named tool choice, an unsupported image) is a fact and stays ``False``."""
    status = getattr(exc, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)  # anthropic.APIStatusError
    if isinstance(status, int) and not isinstance(status, bool):
        return status >= 500
    try:
        import anthropic
    except ImportError:  # pragma: no cover - the SDK is a hard dependency
        sdk_transport: tuple[type[BaseException], ...] = ()
    else:
        sdk_transport = (anthropic.APIConnectionError,)  # includes APITimeoutError
    return isinstance(exc, (httpx.TransportError, TimeoutError, ConnectionError, *sdk_transport))


def _failed(exc: BaseException) -> bool | None:
    """The capability value a failed probe call leaves: ``None`` (unknown) when the server was not reached, else
    ``False``."""
    return None if _unreached(exc) else False


#: the forced call's message does not ask for the tool: only a server that honours ``tool_choice`` calls it, so one
#: that ignores the named choice (Ollama) is reported ``tool_choice: False`` (HB-17 bug 4)
NEUTRAL_ASK = "Say hello in one word."


async def probe(adapter: Any, model: str) -> tuple[dict[str, Any], ProbeUsage]:
    """Three small calls (each ≤ :data:`PROBE_MAX_TOKENS` = 512 output tokens, room for a thinking model to reason
    first) on ``adapter``: a forced single-tool call with a neutral message (``tools``, ``tool_choice``,
    ``strict_tools``; an ``auto`` retry that asks for the tool tells "tools without tool choice" apart), a JSON-schema
    answer (``json_schema``) and a 32×32 red square (``vision``). Nothing raises. A call the server refused (4xx) or
    answered wrongly is ``False``; a call that proves nothing is ``None`` (unknown, so sync's value stands): one cut
    off at ``max_tokens`` with no content (HB-F bug A), a lost connection, a timeout or a 5xx (bug D). When a call
    reached the server, the adapter's ``served_window`` (an Ollama model is loaded now) gives the window actually
    served (``context_window``, ``context_verified``)."""
    usage = ProbeUsage()
    found: dict[str, Any] = {}
    # the adapter must send exactly what the probe asks (no capability-based degrade while probing)
    saved = getattr(adapter, "capabilities", None)
    adapter.capabilities = {"tool_choice": True, "json_schema": True, "pdf": False}
    base = {
        "model": model,
        "max_tokens": PROBE_MAX_TOKENS,
        "system": "You are a capability probe. Follow the instruction exactly.",
    }
    ask_tool = {"role": "user", "content": "Call report_colour with colour blue and count 2."}
    try:
        try:
            msg = await adapter.create(
                {
                    **base,
                    "messages": [{"role": "user", "content": NEUTRAL_ASK}],
                    "tools": [PROBE_TOOL],
                    "tool_choice": {"type": "tool", "name": PROBE_TOOL["name"], "disable_parallel_tool_use": True},
                }
            )
            usage.add(msg)
            # a call the adapter emulated after the server answered in prose is not an honoured tool choice
            calls = [] if getattr(msg, "emulated", False) else _tool_calls(msg, PROBE_TOOL["name"])
            choice: bool | None = None if _cut_off(msg) else bool(calls)
        except Exception as exc:  # noqa: BLE001 - a server that rejects named tool choice answers 400
            calls = []
            choice = _failed(exc)
        if calls:
            found.update(tools=True, tool_choice=True, strict_tools=_valid(calls[0].input))
        else:
            found["tool_choice"] = choice
            try:
                msg = await adapter.create(
                    {
                        **base,
                        "messages": [ask_tool],
                        "tools": [PROBE_TOOL],
                        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
                    }
                )
                usage.add(msg)
                calls = _tool_calls(msg, PROBE_TOOL["name"])
                found["tools"] = None if _cut_off(msg) else bool(calls)
                if calls:
                    found["strict_tools"] = _valid(calls[0].input)
            except Exception as exc:  # noqa: BLE001
                found["tools"] = _failed(exc)
        try:
            msg = await adapter.create(
                {
                    **base,
                    "messages": [{"role": "user", "content": "Answer with the JSON object: answer = ok."}],
                    "output_config": {"format": {"type": "json_schema", "schema": PROBE_SCHEMA}},
                }
            )
            usage.add(msg)
            if _cut_off(msg):
                found["json_schema"] = None
            else:
                data = json.loads(_text(msg) or "null")
                found["json_schema"] = isinstance(data, dict) and isinstance(data.get("answer"), str)
        except Exception as exc:  # noqa: BLE001 - also an answer that is not JSON (a fact: False)
            found["json_schema"] = _failed(exc)
        try:
            msg = await adapter.create(
                {
                    **base,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {"type": "base64", "media_type": "image/png", "data": RED_PNG_B64},
                                },
                                {"type": "text", "text": "What colour is this square? Answer with one word."},
                            ],
                        }
                    ],
                }
            )
            usage.add(msg)
            if _cut_off(msg):
                found["vision"] = None
            else:
                found["vision"] = any(w in _text(msg).lower() for w in ("red", "kırmızı", "kirmizi", "rouge", "rot"))
        except Exception as exc:  # noqa: BLE001
            found["vision"] = _failed(exc)
        reader = getattr(adapter, "served_window", None)
        if usage.calls and inspect.iscoroutinefunction(reader):
            try:
                served = await reader(model)
            except Exception:  # noqa: BLE001 - a missing /api/ps leaves the window as synced
                served = None
            if served:
                found.update(context_window=served, context_verified=True)
    finally:
        adapter.capabilities = saved
    return record("probe", **found), usage


__all__ = [
    "BOOL_KEYS",
    "CAP_KEYS",
    "IMAGE_TOKENS",
    "MIN_OUTPUT_TOKENS",
    "NEEDS",
    "NEUTRAL_ASK",
    "PROBE_MAX_TOKENS",
    "PROBE_SCHEMA",
    "PROBE_TOOL",
    "RED_PNG_B64",
    "call_issue",
    "claude",
    "empty",
    "estimate_input_tokens",
    "fit_context",
    "for_listing",
    "gemini",
    "is_known",
    "llamacpp",
    "lmstudio",
    "merge",
    "ollama",
    "ollama_maximum",
    "ollama_served",
    "openai_cloud",
    "openrouter",
    "probe",
    "record",
    "route_issues",
    "smaller",
    "unverified_text",
    "vllm",
]
