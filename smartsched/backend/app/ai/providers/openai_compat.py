"""OpenAI-compatible adapter: OpenAI, Azure OpenAI (the ``/openai/v1`` API), OpenRouter and any server that speaks
the Chat Completions API at a ``base_url`` (a local Ollama ``http://127.0.0.1:11434/v1``, vLLM, LM Studio).

It talks REST through ``httpx`` (already a dependency of the ``anthropic`` SDK), so no extra SDK is required.
Requests arrive in the gateway's Anthropic shape and are translated:

* ``system`` -> a ``system`` message; text / image blocks -> content parts; a PDF ``document`` block is rasterised
  to PNG page images (``app.council.formats_media.pdf_pages``, HB-13) unless the model is known not to read images
  (then :class:`ProviderUnsupported`);
* ``tool_use`` blocks -> ``assistant.tool_calls``; ``tool_result`` blocks -> ``tool`` messages (before the user's
  text of the same turn); thinking blocks are dropped;
* ``tools`` -> ``{"type": "function", "function": {name, description, parameters, strict}}``; ``tool_choice``
  ``auto`` (``parallel_tool_calls`` = not ``disable_parallel_tool_use``, left out when the server is known not to
  support it). A forced single tool (``{"type": "tool", "name"}``, HB-13) becomes the named function choice when the
  model supports ``tool_choice``; otherwise (Ollama, an unprobed server) it is **emulated**: no ``tools``, the tool's
  input schema as ``response_format``, and the JSON answer wrapped back into a ``tool_use`` block. A server that
  ignores the named choice and answers in prose gets one emulated retry;
* tool-call arguments that are not valid JSON become ``{"_invalid": ...}`` (the caller's schema check answers the
  model with an ``INVALID_JSON`` tool result) instead of failing the whole call;
* ``output_config.format`` (JSON schema) -> ``response_format`` ``json_schema`` (strict);
* ``output_config.effort`` -> ``reasoning_effort`` on OpenAI / Azure reasoning models only.

Capabilities (HB-12): :meth:`list_models` fills each model's record from the list (OpenRouter's
``supported_parameters``, vLLM's ``max_model_len``) and :meth:`sniff` asks a local server what it is, with the same
``url_guard`` check as every call: LM Studio ``GET /api/v0/models``, llama.cpp ``GET /props``, Ollama
``GET /api/version`` + ``POST /api/show``.

Answers come back as :class:`GMessage` (``finish_reason`` ``stop`` / ``tool_calls`` / ``length`` /
``content_filter`` -> ``end_turn`` / ``tool_use`` / ``max_tokens`` / ``refusal``; ``prompt_tokens_details
.cached_tokens`` -> cache reads). Error bodies are never surfaced (they can echo input).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from app.ai import capabilities as caps
from app.ai.providers.base import (
    GBlock,
    GMessage,
    GStopDetails,
    GUsage,
    ModelInfo,
    ProviderAdapter,
    ProviderError,
    ProviderUnsupported,
    content_blocks,
    output_schema,
    system_text,
    tool_input,
    tool_result_text,
)
from app.ai.providers.url_guard import ensure_safe

log = logging.getLogger(__name__)

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai_compatible": "http://127.0.0.1:11434/v1",
    "azure_openai": "",  # https://<resource>.openai.azure.com/openai/v1 (required)
}
_FINISH = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens"}
_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


def _is_reasoning_model(model: str) -> bool:
    m = model.lower().rsplit("/", 1)[-1]
    return m.startswith(("o1", "o3", "o4", "gpt-5"))


class OpenAICompatAdapter(ProviderAdapter):
    def __init__(
        self,
        flavor: str,
        *,
        api_key: str | None,
        base_url: str | None = None,
        timeout_s: float = 120.0,
        temperature: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_local: bool = False,
    ) -> None:
        if flavor not in DEFAULT_BASE_URLS:
            raise ValueError(f"unknown OpenAI-compatible flavor {flavor!r}")
        self.name = flavor
        self.base_url = (base_url or DEFAULT_BASE_URLS[flavor]).rstrip("/")
        if not self.base_url:
            raise ProviderError("this provider needs a base URL (Azure: https://<resource>.openai.azure.com/openai/v1)")
        if flavor in {"openai", "openrouter", "azure_openai"} and not api_key:
            raise ProviderError("no API key configured for this provider")
        self._key = api_key or ""
        self._timeout = timeout_s
        self._transport = transport
        #: the administrator's opt-in for a local server (openai_compatible only; url_guard.py)
        self._allow_local = allow_local and flavor == "openai_compatible"
        self.temperature = temperature

    def __repr__(self) -> str:
        return f"OpenAICompatAdapter({self.name!r}, base_url={self.base_url!r})"

    # ------------------------------------------------------------------ http

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._key:
            if self.name == "azure_openai":
                h["api-key"] = self._key
            else:
                h["Authorization"] = f"Bearer {self._key}"
        if self.name == "openrouter":
            h["X-Title"] = "SmartSched"
        return h

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None, *, root: bool = False
    ) -> dict[str, Any]:
        """``root``: the path is on the server root (``/api/show``, ``/props``), not under the ``/v1`` base."""
        base = self._root() if root else self.base_url
        if self._transport is None:  # a real socket: SSRF guard after DNS resolution (docs/SECURITY.md R12)
            await ensure_safe(base, allow_local=self._allow_local)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            resp = await http.request(method, f"{base}{path}", headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise _status_error(resp.status_code, self.name)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} answered something that is not JSON") from exc
        return data if isinstance(data, dict) else {"data": data}

    def _root(self) -> str:
        base = self.base_url
        for suffix in ("/api/v1", "/v1"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base

    # ------------------------------------------------------------------ translation

    def _cap(self, key: str) -> Any:
        return (self.capabilities or {}).get(key)

    def force_mode(self, kwargs: dict[str, Any]) -> str | None:
        """How a forced single tool is sent: ``named`` (the server supports ``tool_choice``), ``emulate`` (JSON-schema
        output wrapped as the tool call) or ``auto`` (neither is known to work); ``None`` = nothing is forced."""
        choice = kwargs.get("tool_choice") or {}
        if choice.get("type") != "tool" or not kwargs.get("tools"):
            return None
        if self.name in {"openai", "azure_openai"} or self._cap("tool_choice") is True:
            return "named"
        if self._cap("json_schema") is False:
            return "auto"
        return "emulate"

    def build_payload(self, kwargs: dict[str, Any], *, mode: str | None = None) -> dict[str, Any]:
        model = str(kwargs["model"])
        mode = self.force_mode(kwargs) if mode is None else mode
        messages: list[dict[str, Any]] = []
        sys = system_text(kwargs.get("system"))
        forced = _forced_tool(kwargs)
        if mode == "emulate" and forced is not None:
            hint = (
                f"Answer with only one JSON object: the arguments of the tool {forced['name']} "
                f"({forced.get('description', '')}). No other text."
            )
            sys = f"{sys}\n\n{hint}" if sys else hint
        if sys:
            messages.append({"role": "system", "content": sys})
        vision = self._cap("vision")
        for msg in kwargs.get("messages") or []:
            messages.extend(_translate_message(msg, vision=vision))
        payload: dict[str, Any] = {"model": model, "messages": messages}
        limit = int(kwargs.get("max_tokens") or 0)
        if limit:
            payload["max_completion_tokens" if self.name in {"openai", "azure_openai"} else "max_tokens"] = limit
        tools = kwargs.get("tools") or []
        if mode == "emulate" and forced is not None:
            tools = []
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": forced["name"],
                    "schema": forced.get("input_schema") or {"type": "object", "properties": {}},
                    "strict": bool(forced.get("strict")),
                },
            }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
                        **({"strict": True} if t.get("strict") else {}),
                    },
                }
                for t in tools
            ]
            choice = kwargs.get("tool_choice") or {}
            if mode == "named" and forced is not None:
                payload["tool_choice"] = {"type": "function", "function": {"name": forced["name"]}}
            else:
                payload["tool_choice"] = "auto"
            if self._cap("parallel_tools") is not False:
                payload["parallel_tool_calls"] = not bool(choice.get("disable_parallel_tool_use"))
        schema = output_schema(kwargs)
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": True},
            }
        effort = (kwargs.get("output_config") or {}).get("effort")
        reasoning = self.name in {"openai", "azure_openai"} and _is_reasoning_model(model)
        if effort and reasoning:
            payload["reasoning_effort"] = _EFFORT.get(str(effort), "medium")
        temperature = kwargs.get("temperature", self.temperature)
        if temperature is not None and not reasoning:
            payload["temperature"] = float(temperature)
        return payload

    @staticmethod
    def parse_response(data: dict[str, Any], model: str) -> GMessage:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("the provider answered without a choice")
        choice = choices[0] or {}
        msg = choice.get("message") or {}
        blocks: list[GBlock] = []
        if isinstance(msg.get("content"), str) and msg["content"].strip():
            blocks.append(GBlock(type="text", text=msg["content"]))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            blocks.append(
                GBlock(
                    type="tool_use",
                    id=str(call.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                    name=str(fn.get("name") or ""),
                    input=tool_input(fn.get("arguments")),
                )
            )
        finish = str(choice.get("finish_reason") or "stop")
        stop = _FINISH.get(finish, "end_turn")
        details = None
        if finish == "content_filter" or msg.get("refusal"):
            stop, details = "refusal", GStopDetails(category="provider_safety", explanation=None)
        elif any(b.type == "tool_use" for b in blocks) and stop == "end_turn":
            stop = "tool_use"
        usage = data.get("usage") or {}
        cached = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
        prompt = int(usage.get("prompt_tokens") or 0)
        return GMessage(
            content=blocks,
            stop_reason=stop,
            model=str(data.get("model") or model),
            usage=GUsage(
                input_tokens=max(prompt - cached, 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                cache_read_input_tokens=cached,
            ),
            stop_details=details,
            _request_id=str(data.get("id")) if data.get("id") else None,
        )

    # ------------------------------------------------------------------ adapter API

    async def create(self, kwargs: dict[str, Any]) -> GMessage:
        model = str(kwargs["model"])
        mode = self.force_mode(kwargs)
        data = await self._request("POST", "/chat/completions", self.build_payload(kwargs, mode=mode))
        forced = _forced_tool(kwargs)
        if mode == "emulate" and forced is not None:
            return _wrap_emulated(self.parse_response(data, model), forced["name"])
        message = self.parse_response(data, model)
        if (
            mode == "named"
            and forced is not None
            and self._cap("json_schema") is not False
            and not any(b.type == "tool_use" and b.name == forced["name"] for b in message.content)
            and message.stop_reason not in {"max_tokens", "refusal"}
        ):
            # the server ignored the named choice and answered in prose: one emulated retry (HB-13)
            log.info("%s ignored the forced tool; retrying with JSON-schema emulation", self.name)
            data = await self._request("POST", "/chat/completions", self.build_payload(kwargs, mode="emulate"))
            retry = _wrap_emulated(self.parse_response(data, model), forced["name"])
            retry.usage.input_tokens += message.usage.input_tokens
            retry.usage.output_tokens += message.usage.output_tokens
            retry.usage.cache_read_input_tokens += message.usage.cache_read_input_tokens
            return retry
        return message

    async def list_models(self) -> list[ModelInfo]:
        data = await self._request("GET", "/models")
        out: list[ModelInfo] = []
        for m in data.get("data") or data.get("models") or []:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            pricing = m.get("pricing") or {}
            window = m.get("context_length") or m.get("max_model_len")
            out.append(
                ModelInfo(
                    id=str(m["id"]),
                    display_name=str(m.get("name") or m["id"]),
                    created_at=str(m["created"]) if m.get("created") else None,
                    context_window=window,
                    price_in=_per_mtok(pricing.get("prompt")),
                    price_out=_per_mtok(pricing.get("completion")),
                    capabilities=caps.for_listing(self.name, str(m["id"]), m, window),
                )
            )
            if m.get("max_model_len"):
                self._server_kind = "vllm"
        return out

    _server_kind: str | None = None

    async def _try(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        try:
            return await self._request(method, path, payload, root=True)
        except (ProviderError, httpx.HTTPError, ValueError) as exc:
            log.debug("capability sniff %s %s: %s", method, path, type(exc).__name__)
            return None

    async def sniff(self, models: list[ModelInfo]) -> str | None:
        """Which local server this is and what each model can do (HB-12). Only safe reads on the same host, each
        through ``url_guard``; a failing or foreign answer is ignored."""
        if self.name != "openai_compatible":
            return None
        by_id = {m.id: m for m in models}

        def add(model: ModelInfo, layer: dict[str, Any]) -> None:
            model.capabilities = caps.merge(model.capabilities, layer)
            if layer.get("context_window"):
                model.context_window = layer["context_window"]

        listing = await self._try("GET", "/api/v0/models")
        entries = [e for e in (listing or {}).get("data") or [] if isinstance(e, dict) and e.get("type")]
        if entries:
            for e in entries:
                if str(e.get("id")) in by_id:
                    add(by_id[str(e["id"])], caps.lmstudio(e))
            return "lmstudio"
        props = await self._try("GET", "/props")
        if props and (isinstance(props.get("default_generation_settings"), dict) or props.get("n_ctx")):
            layer = caps.llamacpp(props)
            for m in models:
                add(m, layer)
            return "llamacpp"
        version = await self._try("GET", "/api/version")
        if version and isinstance(version.get("version"), str):
            for m in models[:40]:
                show = await self._try("POST", "/api/show", {"model": m.id})
                if show and ("capabilities" in show or "model_info" in show):
                    add(m, caps.ollama(show))
            return "ollama"
        return self._server_kind

    def translate_error(self, exc: Exception, model: str) -> Exception:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return ProviderError(f"{self.name} did not answer in time")
        if isinstance(exc, httpx.HTTPError):
            return ProviderError(f"could not reach {self.name} ({type(exc).__name__})")
        return exc


def _per_mtok(per_token: Any) -> float | None:
    try:
        value = float(per_token)
    except (TypeError, ValueError):
        return None
    return round(value * 1_000_000, 6) if value >= 0 else None


def _status_error(status: int, name: str) -> ProviderError:
    if status == 401:
        return ProviderError(f"{name} rejected the API key (authentication error)")
    if status == 403:
        return ProviderError(f"the {name} key lacks permission for this model")
    if status == 404:
        return ProviderError(f"{name}: model or endpoint not found")
    if status == 429:
        return ProviderError(f"rate limited by {name}; retry later")
    if status == 400:
        return ProviderError(f"{name} rejected the request (bad request)")
    return ProviderError(f"{name} API error {status}")


def _image_part(block: dict[str, Any]) -> dict[str, Any]:
    src = block.get("source") or {}
    if src.get("type") == "base64":
        url = f"data:{src.get('media_type', 'image/png')};base64,{src.get('data', '')}"
    elif src.get("type") == "url":
        url = str(src.get("url"))
    else:
        raise ProviderUnsupported("this image source cannot be sent to an OpenAI-compatible provider")
    return {"type": "image_url", "image_url": {"url": url}}


def _forced_tool(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    choice = kwargs.get("tool_choice") or {}
    if choice.get("type") != "tool":
        return None
    return next((t for t in kwargs.get("tools") or [] if t.get("name") == choice.get("name")), None)


def _wrap_emulated(message: GMessage, name: str) -> GMessage:
    """The JSON answer of an emulated forced tool as a ``tool_use`` block (the caller validates it as before)."""
    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return message  # prose: the caller sees "no tool call", as with any model that does not call the tool
    if not isinstance(data, dict):
        return message
    message.content = [GBlock(type="tool_use", id=f"call_{uuid.uuid4().hex[:12]}", name=name, input=data)]
    if message.stop_reason == "end_turn":
        message.stop_reason = "tool_use"
    return message


def _pdf_parts(block: dict[str, Any], vision: bool | None) -> list[dict[str, Any]]:
    """A base64 PDF document block as PNG page images (HB-13; at most ``formats_media.MAX_PAGES`` pages)."""
    import base64

    if vision is False:
        raise ProviderUnsupported(
            "this model cannot read images, so a PDF cannot be sent to it; route scans to a vision model"
        )
    from app.core import safe_files
    from app.council import formats_media as fm

    src = block.get("source") or {}
    try:
        data = base64.standard_b64decode(str(src.get("data") or ""))
        pages, total = fm.pdf_pages(data)
    except (ValueError, safe_files.UnsafeFileError) as exc:
        raise ProviderUnsupported("the PDF could not be read for page images") from exc
    if total > fm.MAX_PAGES:
        raise ProviderUnsupported(f"scanned PDF with {total} pages: AI vision reads at most {fm.MAX_PAGES}; split it")
    parts: list[dict[str, Any]] = []
    for i, png in enumerate(pages, start=1):
        parts.append({"type": "text", "text": f"Page {i}:"})
        parts.append(
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}
        )
    return parts


def _translate_message(msg: dict[str, Any], *, vision: bool | None = None) -> list[dict[str, Any]]:
    role = msg.get("role")
    blocks = content_blocks(msg.get("content"))
    if role == "assistant":
        text = "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text").strip()
        calls = [
            {
                "id": str(b.get("id")),
                "type": "function",
                "function": {"name": b.get("name"), "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)},
            }
            for b in blocks
            if b.get("type") == "tool_use"
        ]
        out: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            out["tool_calls"] = calls
        return [out]
    tool_msgs: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    for b in blocks:
        kind = b.get("type")
        if kind == "tool_result":
            text = tool_result_text(b)
            tool_msgs.append({"role": "tool", "tool_call_id": str(b.get("tool_use_id")), "content": text})
        elif kind == "text":
            parts.append({"type": "text", "text": str(b.get("text") or "")})
        elif kind == "image":
            parts.append(_image_part(b))
        elif kind == "document":
            src = b.get("source") or {}
            if src.get("type") == "text":
                parts.append({"type": "text", "text": str(src.get("data") or "")})
            elif src.get("type") == "base64" and src.get("media_type", "application/pdf") == "application/pdf":
                parts.extend(_pdf_parts(b, vision))
            else:
                raise ProviderUnsupported("this document source cannot be sent to an OpenAI-compatible provider")
    out_msgs = list(tool_msgs)
    if parts:
        if all(p["type"] == "text" for p in parts):
            out_msgs.append({"role": "user", "content": "\n\n".join(p["text"] for p in parts)})
        else:
            out_msgs.append({"role": "user", "content": parts})
    return out_msgs


__all__ = ["DEFAULT_BASE_URLS", "OpenAICompatAdapter"]
