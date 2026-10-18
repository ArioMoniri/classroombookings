"""What a model can do: capability detection at sync, the active probe at "Test", admin overrides, and the per-feature
needs that route validation enforces (HB-12; docs/research/2026-10-17-ai-helper-architecture.md §5.8).

A capability record (stored on each synced model as ``capabilities``)::

    {tools, tool_choice, strict_tools, json_schema, vision, pdf, context_window, parallel_tools, source, checked_at}

``True`` / ``False`` are facts, ``None`` is unknown. ``pdf`` means *this gateway can send a PDF document block to the
model*: it is ``False`` for every OpenAI-compatible server (the adapter rasterises the pages to PNG instead, HB-13).

Three layers, later ones win per field (a ``None`` never overwrites a fact):

1. **sync** (``source: provider``): Claude providers know everything; OpenAI / Azure / OpenRouter come from the model
   list; an ``openai_compatible`` server is sniffed with safe requests on the same host, through the same
   ``url_guard`` check as every call (:meth:`app.ai.providers.openai_compat.OpenAICompatAdapter.sniff`);
2. **probe** (``source: probe``, ``POST /ai/admin/providers/{p}/test?probe=true``, metered as ``test``): a forced
   single-tool call, a JSON-schema call and a 32×32 image, under 1000 tokens in total (:func:`probe`);
3. **admin** (``source: admin``, audited ``ai.provider.capabilities``): for servers that hide what they can do.

:func:`route_issues` turns the per-feature needs into route errors (``model_lacks_capability``,
``context_too_small``) and warnings (``capability_unknown``): a fact refuses, an unknown only warns.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib
from datetime import UTC, datetime
from typing import Any

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
    of the last layer that contributed a value."""
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


def ollama(show: dict[str, Any]) -> dict[str, Any]:
    """Ollama ``POST /api/show``: ``capabilities`` (``completion``, ``tools``, ``vision``, …) and
    ``model_info.<arch>.context_length``. Ollama has no ``tool_choice`` and does not enforce ``strict``; its JSON
    ``format`` is grammar-constrained. A ``num_ctx`` in the model's parameters is the window actually served."""
    caps = {str(c) for c in show.get("capabilities") or []}
    ctx: int | None = None
    for k, v in (show.get("model_info") or {}).items():
        if str(k).endswith(".context_length"):
            ctx = _int(v)
    for line in str(show.get("parameters") or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "num_ctx":
            served = _int(parts[1])
            if served:
                ctx = min(ctx, served) if ctx else served
    return record(
        tools=("tools" in caps) if caps else None,
        tool_choice=False,
        strict_tools=False,
        json_schema=True,
        vision=("vision" in caps) if caps else None,
        pdf=False,
        parallel_tools=False,
        context_window=ctx,
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
    return [b for b in getattr(message, "content", None) or [] if getattr(b, "type", "") == "tool_use" and b.name == name]


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


async def probe(adapter: Any, model: str) -> tuple[dict[str, Any], ProbeUsage]:
    """Three tiny calls (each ≤ 64 output tokens) on ``adapter``: a forced single-tool call (``tools``,
    ``tool_choice``, ``strict_tools``; an ``auto`` retry tells "tools without tool choice" apart), a JSON-schema
    answer (``json_schema``) and a 32×32 red square (``vision``). A failing call is a ``False``; nothing raises."""
    usage = ProbeUsage()
    found: dict[str, Any] = {}
    # the adapter must send exactly what the probe asks (no capability-based degrade while probing)
    saved = getattr(adapter, "capabilities", None)
    adapter.capabilities = {"tool_choice": True, "json_schema": True, "pdf": False}
    base = {"model": model, "max_tokens": 64, "system": "You are a capability probe. Follow the instruction exactly."}
    ask_tool = {"role": "user", "content": "Call report_colour with colour blue and count 2."}
    try:
        try:
            msg = await adapter.create(
                {
                    **base,
                    "messages": [ask_tool],
                    "tools": [PROBE_TOOL],
                    "tool_choice": {"type": "tool", "name": PROBE_TOOL["name"], "disable_parallel_tool_use": True},
                }
            )
            usage.add(msg)
            calls = _tool_calls(msg, PROBE_TOOL["name"])
        except Exception:  # noqa: BLE001 - a server that rejects named tool choice answers 400
            calls = []
            found["tool_choice"] = False
        if calls:
            found.update(tools=True, tool_choice=found.get("tool_choice", True), strict_tools=_valid(calls[0].input))
        else:
            found["tool_choice"] = False
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
                found["tools"] = bool(calls)
                if calls:
                    found["strict_tools"] = _valid(calls[0].input)
            except Exception:  # noqa: BLE001
                found["tools"] = False
        try:
            msg = await adapter.create(
                {
                    **base,
                    "messages": [{"role": "user", "content": "Answer with the JSON object: answer = ok."}],
                    "output_config": {"format": {"type": "json_schema", "schema": PROBE_SCHEMA}},
                }
            )
            usage.add(msg)
            data = json.loads(_text(msg) or "null")
            found["json_schema"] = isinstance(data, dict) and isinstance(data.get("answer"), str)
        except Exception:  # noqa: BLE001
            found["json_schema"] = False
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
            found["vision"] = any(w in _text(msg).lower() for w in ("red", "kırmızı", "kirmizi", "rouge", "rot"))
        except Exception:  # noqa: BLE001
            found["vision"] = False
    finally:
        adapter.capabilities = saved
    return record("probe", **found), usage


__all__ = [
    "BOOL_KEYS",
    "CAP_KEYS",
    "NEEDS",
    "PROBE_SCHEMA",
    "PROBE_TOOL",
    "RED_PNG_B64",
    "claude",
    "empty",
    "for_listing",
    "gemini",
    "is_known",
    "llamacpp",
    "lmstudio",
    "merge",
    "ollama",
    "openai_cloud",
    "openrouter",
    "probe",
    "record",
    "route_issues",
    "vllm",
]
