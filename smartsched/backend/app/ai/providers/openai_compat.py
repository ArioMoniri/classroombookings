"""OpenAI-compatible adapter: OpenAI, Azure OpenAI (the ``/openai/v1`` API), OpenRouter and any server that speaks
the Chat Completions API at a ``base_url`` (a local Ollama ``http://127.0.0.1:11434/v1``, vLLM, LM Studio).

It talks REST through ``httpx`` (already a dependency of the ``anthropic`` SDK), so no extra SDK is required.
Requests arrive in the gateway's Anthropic shape and are translated:

* ``system`` -> a ``system`` message; text / image blocks -> content parts; a PDF ``document`` block is refused
  (:class:`ProviderUnsupported`: route intake of scanned PDFs to Anthropic, Bedrock or Gemini);
* ``tool_use`` blocks -> ``assistant.tool_calls``; ``tool_result`` blocks -> ``tool`` messages (before the user's
  text of the same turn); thinking blocks are dropped;
* ``tools`` -> ``{"type": "function", "function": {name, description, parameters, strict}}``; ``tool_choice`` stays
  ``auto`` (``parallel_tool_calls`` = not ``disable_parallel_tool_use``);
* ``output_config.format`` (JSON schema) -> ``response_format`` ``json_schema`` (strict);
* ``output_config.effort`` -> ``reasoning_effort`` on OpenAI / Azure reasoning models only.

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
    parse_json_object,
    system_text,
    tool_result_text,
)

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

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            resp = await http.request(method, f"{self.base_url}{path}", headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise _status_error(resp.status_code, self.name)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} answered something that is not JSON") from exc
        return data if isinstance(data, dict) else {"data": data}

    # ------------------------------------------------------------------ translation

    def build_payload(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        model = str(kwargs["model"])
        messages: list[dict[str, Any]] = []
        sys = system_text(kwargs.get("system"))
        if sys:
            messages.append({"role": "system", "content": sys})
        for msg in kwargs.get("messages") or []:
            messages.extend(_translate_message(msg))
        payload: dict[str, Any] = {"model": model, "messages": messages}
        limit = int(kwargs.get("max_tokens") or 0)
        if limit:
            payload["max_completion_tokens" if self.name in {"openai", "azure_openai"} else "max_tokens"] = limit
        tools = kwargs.get("tools") or []
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
            payload["tool_choice"] = "auto"
            choice = kwargs.get("tool_choice") or {}
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
                    input=parse_json_object(fn.get("arguments")),
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
        data = await self._request("POST", "/chat/completions", self.build_payload(kwargs))
        return self.parse_response(data, str(kwargs["model"]))

    async def list_models(self) -> list[ModelInfo]:
        data = await self._request("GET", "/models")
        out: list[ModelInfo] = []
        for m in data.get("data") or data.get("models") or []:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            pricing = m.get("pricing") or {}
            out.append(
                ModelInfo(
                    id=str(m["id"]),
                    display_name=str(m.get("name") or m["id"]),
                    created_at=str(m["created"]) if m.get("created") else None,
                    context_window=m.get("context_length"),
                    price_in=_per_mtok(pricing.get("prompt")),
                    price_out=_per_mtok(pricing.get("completion")),
                )
            )
        return out

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


def _translate_message(msg: dict[str, Any]) -> list[dict[str, Any]]:
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
            else:
                raise ProviderUnsupported(
                    "PDF documents cannot be sent to an OpenAI-compatible provider; route intake to Anthropic, "
                    "Bedrock or Gemini"
                )
    out_msgs = list(tool_msgs)
    if parts:
        if all(p["type"] == "text" for p in parts):
            out_msgs.append({"role": "user", "content": "\n\n".join(p["text"] for p in parts)})
        else:
            out_msgs.append({"role": "user", "content": parts})
    return out_msgs


__all__ = ["DEFAULT_BASE_URLS", "OpenAICompatAdapter"]
