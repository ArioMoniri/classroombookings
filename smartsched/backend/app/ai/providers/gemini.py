"""Google Gemini adapter (the Gemini API ``generativelanguage.googleapis.com/v1beta``, REST through ``httpx``; no
Google SDK is required).

Translation from the gateway's Anthropic shape:

* ``system`` -> ``systemInstruction``; roles ``user`` / ``assistant`` -> ``user`` / ``model``;
* text -> ``{"text"}``; base64 images and PDF documents -> ``inlineData`` (Gemini reads PDFs natively);
* ``tool_use`` -> ``functionCall``; ``tool_result`` -> ``functionResponse`` (the function name is looked up from
  the earlier ``tool_use`` with the same id);
* ``tools`` -> one ``functionDeclarations`` tool with ``parametersJsonSchema`` (full JSON Schema);
  ``functionCallingConfig.mode`` ``AUTO``;
* ``output_config.format`` -> ``responseMimeType: application/json`` + ``responseJsonSchema``;
* ``max_tokens`` -> ``maxOutputTokens``; ``effort`` -> ``thinkingConfig.thinkingLevel`` (``low`` / ``high``).

``finishReason`` ``STOP`` / ``MAX_TOKENS`` / ``SAFETY`` (and the other block reasons) -> ``end_turn`` (``tool_use``
when a function was called) / ``max_tokens`` / ``refusal``. Thinking tokens are billed as output.
"""

from __future__ import annotations

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
    system_text,
    tool_result_text,
)
from app.ai.providers.openai_compat import _status_error
from app.ai.providers.url_guard import ensure_safe

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_BLOCKED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"}
_LEVEL = {"low": "low", "medium": "low", "high": "high", "xhigh": "high", "max": "high"}


class GeminiAdapter(ProviderAdapter):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_s: float = 120.0,
        temperature: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("no API key configured for Gemini")
        self._key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout_s
        self._transport = transport
        self.temperature = temperature

    def __repr__(self) -> str:
        return f"GeminiAdapter(base_url={self.base_url!r})"

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"x-goog-api-key": self._key, "Content-Type": "application/json"}
        if self._transport is None:  # a real socket: SSRF guard after DNS resolution (docs/SECURITY.md R12)
            await ensure_safe(self.base_url, allow_local=False)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            resp = await http.request(method, f"{self.base_url}{path}", headers=headers, json=payload)
        if resp.status_code >= 400:
            raise _status_error(resp.status_code, "Gemini")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Gemini answered something that is not JSON") from exc
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ translation

    def build_payload(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        names: dict[str, str] = {}
        contents: list[dict[str, Any]] = []
        for msg in kwargs.get("messages") or []:
            role = "model" if msg.get("role") == "assistant" else "user"
            parts: list[dict[str, Any]] = []
            for b in content_blocks(msg.get("content")):
                kind = b.get("type")
                if kind == "text" and str(b.get("text") or ""):
                    parts.append({"text": str(b["text"])})
                elif kind == "tool_use":
                    names[str(b.get("id"))] = str(b.get("name"))
                    parts.append(
                        {"functionCall": {"id": str(b.get("id")), "name": b.get("name"), "args": b.get("input") or {}}}
                    )
                elif kind == "tool_result":
                    tid = str(b.get("tool_use_id"))
                    parts.append(
                        {
                            "functionResponse": {
                                "id": tid,
                                "name": names.get(tid, "tool"),
                                "response": {"result": tool_result_text(b)},
                            }
                        }
                    )
                elif kind in {"image", "document"}:
                    src = b.get("source") or {}
                    if src.get("type") == "base64":
                        parts.append({"inlineData": {"mimeType": src.get("media_type"), "data": src.get("data")}})
                    elif src.get("type") == "text":
                        parts.append({"text": str(src.get("data") or "")})
                    else:
                        raise ProviderUnsupported("this attachment source cannot be sent to Gemini")
            if parts:
                contents.append({"role": role, "parts": parts})
        payload: dict[str, Any] = {"contents": contents}
        sys = system_text(kwargs.get("system"))
        if sys:
            payload["systemInstruction"] = {"parts": [{"text": sys}]}
        tools = kwargs.get("tools") or []
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parametersJsonSchema": t.get("input_schema") or {"type": "object", "properties": {}},
                        }
                        for t in tools
                    ]
                }
            ]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        gen: dict[str, Any] = {}
        if kwargs.get("max_tokens"):
            gen["maxOutputTokens"] = int(kwargs["max_tokens"])
        schema = output_schema(kwargs)
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = schema
        effort = (kwargs.get("output_config") or {}).get("effort")
        if effort:
            gen["thinkingConfig"] = {"thinkingLevel": _LEVEL.get(str(effort), "low")}
        temperature = kwargs.get("temperature", self.temperature)
        if temperature is not None:
            gen["temperature"] = float(temperature)
        if gen:
            payload["generationConfig"] = gen
        return payload

    @staticmethod
    def parse_response(data: dict[str, Any], model: str) -> GMessage:
        candidates = data.get("candidates") or []
        feedback = data.get("promptFeedback") or {}
        usage_md = data.get("usageMetadata") or {}
        cached = int(usage_md.get("cachedContentTokenCount") or 0)
        usage = GUsage(
            input_tokens=max(int(usage_md.get("promptTokenCount") or 0) - cached, 0),
            output_tokens=int(usage_md.get("candidatesTokenCount") or 0) + int(usage_md.get("thoughtsTokenCount") or 0),
            cache_read_input_tokens=cached,
        )
        if not candidates:
            if feedback.get("blockReason"):
                return GMessage(
                    content=[],
                    stop_reason="refusal",
                    model=model,
                    usage=usage,
                    stop_details=GStopDetails(category="provider_safety"),
                )
            raise ProviderError("Gemini answered without a candidate")
        cand = candidates[0] or {}
        blocks: list[GBlock] = []
        for part in (cand.get("content") or {}).get("parts") or []:
            if part.get("thought"):
                continue
            if "text" in part and str(part["text"]).strip():
                blocks.append(GBlock(type="text", text=str(part["text"])))
            elif "functionCall" in part:
                fc = part["functionCall"] or {}
                args = fc.get("args") or {}
                if not isinstance(args, dict):
                    raise ProviderError("Gemini sent function arguments that are not an object")
                blocks.append(
                    GBlock(
                        type="tool_use",
                        id=str(fc.get("id") or f"call_{uuid.uuid4().hex[:12]}"),
                        name=str(fc.get("name") or ""),
                        input=args,
                    )
                )
        finish = str(cand.get("finishReason") or "STOP")
        details = None
        if finish in _BLOCKED:
            stop, details = "refusal", GStopDetails(category="provider_safety")
        elif finish == "MAX_TOKENS":
            stop = "max_tokens"
        elif any(b.type == "tool_use" for b in blocks):
            stop = "tool_use"
        else:
            stop = "end_turn"
        return GMessage(
            content=blocks,
            stop_reason=stop,
            model=str(data.get("modelVersion") or model),
            usage=usage,
            stop_details=details,
            _request_id=str(data["responseId"]) if data.get("responseId") else None,
        )

    # ------------------------------------------------------------------ adapter API

    async def create(self, kwargs: dict[str, Any]) -> GMessage:
        model = str(kwargs["model"]).removeprefix("models/")
        data = await self._request("POST", f"/models/{model}:generateContent", self.build_payload(kwargs))
        return self.parse_response(data, model)

    async def list_models(self) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        token: str | None = None
        for _page in range(20):
            data = await self._request("GET", "/models?pageSize=1000" + (f"&pageToken={token}" if token else ""))
            for m in data.get("models") or []:
                if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                    continue
                out.append(
                    ModelInfo(
                        id=str(m.get("name") or "").removeprefix("models/"),
                        display_name=str(m.get("displayName") or m.get("name")),
                        context_window=m.get("inputTokenLimit"),
                        max_output=m.get("outputTokenLimit"),
                    )
                )
            token = data.get("nextPageToken")
            if not token:
                break
        return out

    def translate_error(self, exc: Exception, model: str) -> Exception:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return ProviderError("Gemini did not answer in time")
        if isinstance(exc, httpx.HTTPError):
            return ProviderError(f"could not reach Gemini ({type(exc).__name__})")
        return exc


__all__ = ["DEFAULT_BASE_URL", "GeminiAdapter"]
