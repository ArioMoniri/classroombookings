"""The per-call pipeline of the AI gateway (wave 3 W3-AI). :func:`app.ai.client.get_client` binds a
:class:`GatewayContext` to the :class:`~app.ai.client.AIClient`; every ``complete`` / ``stream_complete`` then runs:

1. route: the feature (declared scope or the call stack) -> provider + model + effort / caps / fallback;
2. KVKK transfer basis for a feature that can carry personal data (R-AI-03; 409 ``ai_transfer_basis_missing``);
3. tool-round cap, per-user requests per minute and concurrent calls;
4. the input guard on the person's typed text, once per interaction (+ the optional model-based scope check);
5. limits: reserve the estimated tokens / cost against the org budget and the user's limits;
6. caps (``max_tokens``, effort, timeout) and the guard preamble in ``system``;
7. the provider call (one retry on the route's fallback provider / model after a provider failure);
8. output guard (only offered tools, schema-valid structured output, no links / code in free text);
9. one ``ai_usage`` row per outcome, settle the reservation, threshold alerts, the W3-OPS metric hook.

A refused call raises :class:`AIGuardError` (an ``HTTPException`` with ``{code, message, message_tr, message_en}``:
422 guard, 429 limits / rate, 409 transfer basis); a bad answer raises :class:`app.ai.client.AIOutputRejected` (an
``AIUpstreamError``: nothing is applied, callers fall back like on any provider failure).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.ai import guardrails as g
from app.ai.context import current_actor, current_scope
from app.ai.gateway import PERSONAL_FEATURES, ResolvedRoute
from app.ai.providers import PROVIDERS, ProviderAdapter, has_credentials, make_adapter
from app.ai.providers.base import ProviderError, output_schema

log = logging.getLogger(__name__)

_RATE = g.RateLimiter()
_CONCURRENCY = g.ConcurrencyGate()
#: tests only: an ``httpx`` transport for the REST adapters (OpenAI-compatible, Gemini)
TEST_TRANSPORT: list[Any] = [None]


def reset_state() -> None:
    _RATE.reset()
    _CONCURRENCY.reset()


class AIGuardError(HTTPException):
    """A call the gateway refused before it left the server (guardrail, limit, rate, transfer basis)."""

    def __init__(self, code: str, status: int, *, rule: str | None = None) -> None:
        tr, en = g.message_for(code)
        super().__init__(status, {"code": code, "message": en, "message_en": en, "message_tr": tr})
        self.code, self.rule = code, rule

    def __str__(self) -> str:
        return str(self.detail["message_en"]) if isinstance(self.detail, dict) else str(self.detail)


_STATUS = {
    "ai_limit_reached": 429,
    "ai_budget_exceeded": 429,
    "rate_limited": 429,
    "too_many_concurrent": 429,
    "tool_rounds_exceeded": 429,
    "ai_transfer_basis_missing": 409,
}


@dataclass
class GatewayContext:
    feature: str
    routes: dict[str, ResolvedRoute]
    secrets: dict[str, dict[str, str]]
    configs: dict[str, dict[str, Any]]
    transfer: dict[str, bool]
    guards: dict[str, Any]
    limits: dict[str, Any]
    synced_prices: dict[str, dict[str, tuple[float | None, float | None]]]
    user_id: int | None = None
    timeout_s: float = 120.0
    max_retries: int = 3
    _adapters: dict[tuple[str, str], ProviderAdapter] = field(default_factory=dict)

    def usable(self, provider: str) -> bool:
        cfg = self.configs.get(provider) or {}
        if provider != "anthropic" and not cfg.get("enabled", True):
            return False
        return provider in PROVIDERS and has_credentials(provider, self.secrets.get(provider) or {})

    def adapter(self, provider: str, model: str, temperature: float | None) -> ProviderAdapter:
        key = (provider, model)
        if key not in self._adapters:
            self._adapters[key] = make_adapter(
                provider,
                model=model,
                secrets=self.secrets.get(provider) or {},
                config=self.configs.get(provider) or {},
                timeout_s=self.timeout_s,
                max_retries=self.max_retries,
                temperature=temperature,
                transport=TEST_TRANSPORT[0],
            )
        return self._adapters[key]


def _prompt_fingerprint(kwargs: dict[str, Any]) -> tuple[str, int]:
    blob = json.dumps(
        {k: kwargs.get(k) for k in ("system", "messages", "tools")}, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), len(blob)


def _with_preamble(system: Any) -> Any:
    """The guard preamble as the first system block: static, so it never moves a cache breakpoint."""
    if isinstance(system, str):
        return [dict(g.GUARD_PREAMBLE), {"type": "text", "text": system}] if system else [dict(g.GUARD_PREAMBLE)]
    if isinstance(system, list):
        return [dict(g.GUARD_PREAMBLE), *system]
    return system


def _usage_fields(message: Any) -> dict[str, Any]:
    usage = getattr(message, "usage", None)
    geo = getattr(usage, "inference_geo", None) if usage is not None else None
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        "inference_geo": str(geo)[:32] if geo else None,
        "request_id": str(getattr(message, "_request_id", "") or "")[:64] or None,
    }


def _ops_hook(**fields: Any) -> None:
    """Aggregated metric for W3-OPS (no user label); optional - the module may not exist yet."""
    try:
        from app.core import observability  # type: ignore[attr-defined, unused-ignore]

        hook = getattr(observability, "record_ai_call", None)
        if hook is not None:
            hook(**fields)
    except Exception:  # noqa: BLE001 - metrics never break a call
        return


async def run_call(
    client: Any, kwargs: dict[str, Any], *, stream: bool, on_event: Any, model_override: str | None
) -> Any:
    from app.ai.client import AIOutputRejected, effort_supported, estimate_cost_usd, price_version
    from app.services import ai_usage as meter

    gw: GatewayContext = client.gateway
    inter = current_scope()
    feature = inter.feature if inter is not None else gw.feature
    rr = gw.routes.get(feature) or gw.routes[gw.feature]
    route = rr.route
    if not gw.usable(route.provider):  # a feature routed to a provider without a key: the bound route serves it
        rr = gw.routes[gw.feature]
        route = rr.route
    provider = route.provider
    claude = PROVIDERS[provider].claude
    model = (model_override if (model_override and claude) else None) or route.model
    user_id = (
        (inter.user_id if inter is not None and inter.user_id is not None else None) or gw.user_id or current_actor()
    )
    sha, chars = _prompt_fingerprint(kwargs)
    base: dict[str, Any] = {
        "user_id": user_id,
        "feature": feature,
        "provider": provider,
        "model": model,
        "prompt_sha256": sha,
        "prompt_chars": chars,
    }
    started = time.monotonic()
    guard_verdict = "skipped"

    async def refuse(code: str, outcome: str, rule: str | None = None) -> AIGuardError:
        await meter.record(
            **base,
            outcome=outcome,
            reason_code=code,
            detail=rule,
            guard_verdict="refused",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return AIGuardError(code, _STATUS.get(code, 422), rule=rule)

    # 2. transfer basis
    if feature in PERSONAL_FEATURES and not gw.transfer.get(provider, provider == "anthropic"):
        raise await refuse("ai_transfer_basis_missing", "refused_by_guardrail", provider)
    # 3. tool rounds, rate, concurrency
    if inter is not None:
        inter.rounds += 1
        cap = int(route.max_tool_rounds or rr.caps.get("max_tool_rounds") or 0)
        if cap and inter.rounds > cap:
            raise await refuse("tool_rounds_exceeded", "refused_by_guardrail", f"rounds>{cap}")
    if user_id is not None and gw.guards.get("rate_limit", True):
        if not _RATE.hit(user_id, per_minute=int(gw.limits.get("requests_per_minute") or 0)):
            raise await refuse("rate_limited", "refused_by_guardrail", "per_minute")
    # 4. input guard (once per interaction)
    if inter is not None and inter.user_text and not inter.checked:
        inter.checked = True
        verdict = g.check_user_input(
            inter.user_text,
            feature,
            scope_check=bool(gw.guards.get("scope_check", True)),
            injection_check=bool(gw.guards.get("injection_check", True)),
        )
        if not verdict.allowed:
            raise await refuse(str(verdict.reason_code), "refused_by_guardrail", verdict.rule)
        guard_verdict = "pass"
        if verdict.unclear and gw.guards.get("model_scope_check"):
            if not await _model_scope_check(client, gw, inter.user_text):
                raise await refuse("model_scope_check", "refused_by_guardrail", "model")
    elif inter is not None and inter.checked:
        guard_verdict = "pass"
    if inter is not None and inter.flags:
        guard_verdict = "flagged"
    # 5. limits (reserve the estimate)
    max_tokens = int(kwargs.get("max_tokens") or 0)
    cap_tokens = int(route.max_tokens or rr.caps.get("max_tokens") or 0)
    if cap_tokens and max_tokens > cap_tokens:
        max_tokens = cap_tokens
    est_tokens = int(chars / 3.5) + min(max_tokens or 4000, 4000)
    rate = gw.synced_prices.get(provider, {}).get(model)
    est_cost = estimate_cost_usd(model, int(chars / 3.5), min(max_tokens or 4000, 4000), provider=provider, prices=rate)
    concurrency_key = user_id
    if concurrency_key is not None and not _CONCURRENCY.acquire(
        concurrency_key, limit=int(gw.limits.get("max_concurrent") or 0)
    ):
        raise await refuse("too_many_concurrent", "refused_by_guardrail", "concurrent")
    reservation = None
    try:
        from app.core.db import get_session_factory

        try:
            async with get_session_factory()() as s:
                reservation = await meter.reserve(s, user_id=user_id, est_tokens=est_tokens, est_cost=est_cost)
        except meter.LimitRefusal as exc:
            raise await refuse(exc.code, "limit_reached", exc.scope) from None
        # 6. caps + effort + preamble
        call = {k: v for k, v in kwargs.items() if k != "_effort"}
        call.update(model=model, max_tokens=max_tokens or kwargs.get("max_tokens"))
        effort = route.effort or kwargs.get("_effort")
        oc = {k: v for k, v in (call.get("output_config") or {}).items() if k != "effort"}
        if effort and (not claude or effort_supported(model)):
            oc["effort"] = effort
        if oc:
            call["output_config"] = oc
        else:
            call.pop("output_config", None)
        call["system"] = _with_preamble(call.get("system"))
        timeout = float(route.timeout_s or rr.caps.get("timeout_s") or 300)
        # 7. provider call with one fallback
        message, served_provider, served_model = await _call_with_fallback(
            client,
            gw,
            route,
            provider,
            model,
            call,
            stream=stream,
            on_event=on_event,
            timeout=timeout,
            base=base,
            started=started,
        )
        base.update(provider=served_provider, model=served_model)
        usage = _usage_fields(message)
        prices = gw.synced_prices.get(served_provider, {}).get(served_model)
        cost = estimate_cost_usd(
            served_model,
            usage["input_tokens"],
            usage["output_tokens"],
            usage["cache_read_tokens"],
            usage["cache_write_tokens"],
            provider=served_provider,
            prices=prices,
        )
        if not usage["inference_geo"] and served_provider == "bedrock":
            usage["inference_geo"] = str((gw.configs.get("bedrock") or {}).get("region") or "")[:32] or None
        common = {
            **base,
            **usage,
            "cost_usd": cost,
            "price_version": price_version(served_provider, served_model, prices),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "guard_verdict": guard_verdict,
        }
        if getattr(message, "stop_reason", None) == "refusal":
            await meter.record(**common, outcome="provider_error", reason_code="provider_refusal")
            return message  # AIClient._finish raises AIRefusal
        # 8. output guard
        if gw.guards.get("output_check", True):
            issues = g.check_output(message, tools=call.get("tools"), schema=output_schema(call), feature=feature)
            if issues:
                await meter.record(
                    **{**common, "guard_verdict": "refused"}, outcome="refused_by_guardrail", reason_code=issues[0]
                )
                tr, en = g.message_for(issues[0])
                raise AIOutputRejected(issues[0], tr, en)
            flags = g.sanitize_output_text(message, feature=feature)
            if flags:
                common["detail"] = ",".join(flags)[:255]
        await meter.record(**common, outcome="ok")
        _ops_hook(
            feature=feature,
            provider=served_provider,
            model=served_model,
            outcome="ok",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=cost,
            latency_ms=common["latency_ms"],
        )
        return message
    finally:
        meter.settle(reservation)
        if concurrency_key is not None:
            _CONCURRENCY.release(concurrency_key)
        await meter.check_alerts(user_id)


async def _call_with_fallback(
    client: Any,
    gw: GatewayContext,
    route: Any,
    provider: str,
    model: str,
    call: dict[str, Any],
    *,
    stream: bool,
    on_event: Any,
    timeout: float,
    base: dict[str, Any],
    started: float,
) -> tuple[Any, str, str]:
    from app.ai.client import AIUpstreamError
    from app.services import ai_usage as meter

    attempts = [(provider, model)]
    fb = route.fallback()
    if fb is not None and gw.usable(fb.provider) and (fb.provider, fb.model) != (provider, model):
        attempts.append((fb.provider, fb.model))
    last: Exception | None = None
    for i, (prov, mod) in enumerate(attempts):
        payload = {**call, "model": mod}
        try:
            adapter = gw.adapter(prov, mod, route.temperature)
            coro = adapter.stream(payload, on_event) if stream else adapter.create(payload)
            message = await asyncio.wait_for(coro, timeout=timeout)
            return message, prov, mod
        except (ProviderError, TimeoutError) as exc:
            mapped: Exception = exc
        except Exception as exc:  # noqa: BLE001 - SDK errors are translated by the adapter
            try:
                adapter = gw.adapter(prov, mod, route.temperature)
                mapped = adapter.translate_error(exc, mod)
            except ProviderError as perr:
                mapped = perr
            if mapped is exc and not isinstance(exc, ProviderError):
                await meter.record(
                    **{**base, "provider": prov, "model": mod},
                    outcome="provider_error",
                    reason_code="provider_error",
                    detail=type(exc).__name__,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
                raise
        text = "the AI provider did not answer in time" if isinstance(mapped, TimeoutError) else str(mapped)
        await meter.record(
            **{**base, "provider": prov, "model": mod},
            outcome="provider_error",
            reason_code="provider_unsupported"
            if mapped.__class__.__name__ == "ProviderUnsupported"
            else "provider_error",
            detail=text[:255],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        last = AIUpstreamError(text)
        if i + 1 < len(attempts):
            log.info("ai provider %s failed; trying the fallback %s", prov, attempts[i + 1][0])
    assert last is not None
    raise last


async def _model_scope_check(client: Any, gw: GatewayContext, text: str) -> bool:
    """Optional model-based scope check (``guard`` feature, metered). True = in scope; a failing check allows."""
    from app.ai.client import AIClient
    from app.ai.context import ai_scope

    schema = {
        "type": "object",
        "properties": {"in_scope": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["in_scope", "reason"],
        "additionalProperties": False,
    }
    guard_client = AIClient("", "", adapter=client._adapter, provider=client.provider, gateway=gw)
    guard_client.gateway = GatewayContext(**{**gw.__dict__, "feature": "guard", "_adapters": gw._adapters})
    guard_client.gateway.guards = {**gw.guards, "model_scope_check": False}
    try:
        with ai_scope("guard", user_id=gw.user_id):
            msg = await guard_client.complete(
                system=(
                    "Classify whether the user's request is about this institution's class / exam / room scheduling, "
                    "room booking or timetable data intake. Answer only with the JSON object."
                ),
                messages=[{"role": "user", "content": g.spotlight(text, "user_request")}],
                max_tokens=200,
                output_format={"type": "json_schema", "schema": schema},
                effort="low",
            )
        from app.ai.client import text_of

        return bool(json.loads(text_of(msg)).get("in_scope", True))
    except Exception:  # noqa: BLE001 - the deterministic check already passed; never block on a broken classifier
        log.info("model scope check unavailable; allowing")
        return True


__all__ = ["TEST_TRANSPORT", "AIGuardError", "GatewayContext", "reset_state", "run_call"]
