"""The transcription flow and the mic's status (VO-03).

:func:`transcribe` checks, in order, and refuses with a :class:`~app.ai.voice.errors.VoiceError`:

1. the target (``chat`` / ``rules`` need ``planning.edit``, ``guard`` the AI admin rights);
2. voice switched on and a speech route whose provider is usable (409 ``voice_not_configured``);
3. the person's KVKK consent ``voice`` (403 ``voice_consent_required``);
4. the clip: not empty, ≤ 5 MB, an accepted type whose magic bytes match, ≤ ``max_seconds`` by its header;
5. the KVKK transfer record of the cloud provider (409 ``ai_transfer_basis_missing``; ``voice_stt`` is personal);
6. the per-person rate and concurrency gates of the text gateway;
7. the audio-second limits and the org cost budget (reserve, then settle with the real length; 429);

then calls the route's provider with one fallback, checks the provider's reported length again, cleans the text
(control and bidi characters out, Unicode NFC, the target's length cap), writes one ``ai_usage`` row and returns
the transcript. The transcript is **not** guarded here: it goes back only to the same person, who reviews and
sends it through the target's own endpoint, where the full text pipeline runs. Audio bytes stay in this
request's memory; nothing here logs the transcript.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway as gw
from app.ai import pipeline
from app.ai.guardrails import DEFAULT_MAX_INPUT_CHARS, MAX_INPUT_CHARS
from app.ai.providers import PROVIDERS
from app.ai.providers.base import ProviderError
from app.ai.sanitize import strip_controls
from app.ai.voice import audio as clip_checks
from app.ai.voice import registry
from app.ai.voice.errors import VoiceError
from app.ai.voice.speech import Transcript
from app.ai.voice.vocabulary import catalog_terms
from app.models import User

log = logging.getLogger(__name__)

FEATURE = "voice_stt"
PURPOSE = "voice"
#: where a transcript may be dictated into, and the permissions (any of) each needs
TARGETS: dict[str, tuple[str, ...]] = {
    "chat": ("planning.edit",),
    "rules": ("planning.edit",),
    "guard": ("planning.admin", "setup.settings"),
}
#: seconds of slack over the cap before the provider's own length refuses a clip (encoder padding)
GRACE_S = 2.0
#: why the mic is hidden (configuration) vs shown but blocked (the person can act or wait)
CONFIG_REASONS = ("disabled", "not_configured", "provider_unusable", "transfer_basis_missing")


def allowed_targets(perms: frozenset[str] | set[str]) -> list[str]:
    return [t for t, need in TARGETS.items() if any(p in perms for p in need)]


@dataclass
class Attempt:
    provider: str
    model: str
    config: dict[str, Any]
    secrets: dict[str, str]
    transfer_ok: bool


@dataclass
class Setup:
    settings: dict[str, Any]
    caps: dict[str, Any]
    source: str
    attempts: list[Attempt] = field(default_factory=list)
    #: the primary route's provider even when it is not usable (for the status text)
    provider: str = ""
    model: str = ""

    @property
    def primary(self) -> Attempt | None:
        return self.attempts[0] if self.attempts else None


async def _attempt(session: AsyncSession, provider: str, model: str, speech: set[str]) -> Attempt | None:
    if not provider or not model or not registry.speech_capable(provider) or model not in speech:
        return None
    if not await gw.provider_usable(session, provider):
        return None
    cfg = await gw.provider_config(session, provider)
    record = await gw.transfer_record(session, provider)
    secrets = await gw.provider_secrets(session, provider)
    return Attempt(provider, model, cfg, secrets, gw.transfer_ok(provider, cfg, record))


async def load_setup(session: AsyncSession) -> Setup:
    settings = await gw.get_voice(session)
    rr = await gw.resolve_route(session, FEATURE)
    setup = Setup(settings, rr.caps, rr.source, provider=rr.route.provider, model=rr.route.model)
    if rr.source == "none":
        return setup
    pairs = [(rr.route.provider, rr.route.model)]
    if rr.route.fallback_provider and rr.route.fallback_model:
        pairs.append((rr.route.fallback_provider, rr.route.fallback_model))
    for i, (prov, model) in enumerate(pairs):
        if i and (prov, model) == pairs[0]:
            continue
        speech = registry.speech_model_ids((await gw.synced_models(session, prov)).get("models") or [])
        att = await _attempt(session, prov, model, speech)
        if att is not None:
            setup.attempts.append(att)
        elif i == 0:
            return setup  # an unusable primary: the fallback alone does not make voice "available"
    return setup


def _config_reason(setup: Setup) -> str | None:
    if setup.source == "none":
        return "not_configured"
    if not setup.settings["enabled"]:
        return "disabled"
    if setup.primary is None:
        return "provider_unusable"
    if not setup.primary.transfer_ok:
        return "transfer_basis_missing"
    return None


def _max_seconds(setup: Setup) -> int:
    return min(int(setup.settings["max_seconds"]), int(setup.caps.get("max_audio_s") or gw.VOICE_MAX_SECONDS))


# ---------------------------------------------------------------------------------------------- status


async def status(session: AsyncSession, user: User, perms: frozenset[str]) -> dict[str, Any]:
    """What the mic button needs: ``available`` + ``reason`` (``disabled`` | ``not_configured`` |
    ``provider_unusable`` | ``transfer_basis_missing`` hide the mic; ``not_permitted`` | ``consent_required`` |
    ``limit_reached`` show it blocked), the provider and region for the consent sheet, the caps and the minutes."""
    from app.services import ai_usage as meter
    from app.services import kvkk

    setup = await load_setup(session)
    targets = allowed_targets(perms)
    consent = await kvkk.has_consent(session, user.id, PURPOSE)
    limits = await gw.get_limits(session)
    own = meter.user_audio_limits(limits, user)
    t = await meter.totals(session, user_id=user.id)
    day_s, month_s = round(t["day_audio_ms"] / 1000), round(t["month_audio_ms"] / 1000)
    reason = _config_reason(setup)
    if reason is None and not targets:
        reason = "not_permitted"
    if reason is None and not consent:
        reason = "consent_required"
    if reason is None and (
        (own["daily_s"] and day_s >= own["daily_s"]) or (own["monthly_s"] and month_s >= own["monthly_s"])
    ):
        reason = "limit_reached"
    att = setup.primary
    spec = PROVIDERS.get(setup.provider)
    record = await gw.transfer_record(session, setup.provider) if spec else {}
    return {
        "available": reason is None,
        "reason": reason,
        "hide_mic": reason in CONFIG_REASONS,
        "consent": consent,
        "consent_purpose": PURPOSE,
        "targets": targets,
        "provider": setup.provider or None,
        "provider_label": spec.label_tr if spec else None,
        "provider_label_en": spec.label_en if spec else None,
        "model": setup.model or None,
        "region": (record.get("region") or (att.config.get("region") if att else None)) if spec else None,
        "language": setup.settings["language"],
        "languages": list(gw.VOICE_LANGUAGES),
        "max_seconds": _max_seconds(setup),
        "max_bytes": int(setup.caps.get("max_bytes") or 5_000_000),
        "mime_types": list(clip_checks.TYPES),
        "live_captions": setup.settings["live_captions"],
        "review_required": True,
        "retention_days": 0,
        "usage": {
            "day_s": day_s,
            "day_limit_s": own["daily_s"],
            "month_s": month_s,
            "month_limit_s": own["monthly_s"],
        },
    }


# ---------------------------------------------------------------------------------------------- transcribe


def clean_text(text: str, target: str) -> tuple[str, list[str]]:
    out = unicodedata.normalize("NFC", strip_controls(text or ""))
    out = " ".join(out.split())
    warnings: list[str] = []
    cap = MAX_INPUT_CHARS.get(target, DEFAULT_MAX_INPUT_CHARS)
    if len(out) > cap:
        out, warnings = out[:cap].rstrip(), ["truncated"]
    if not out:
        warnings.append("empty")
    return out, warnings


async def transcribe(
    session: AsyncSession,
    user: User,
    perms: frozenset[str],
    data: bytes,
    content_type: str | None,
    *,
    target: str,
    lang: str | None,
) -> dict[str, Any]:
    from app.ai.client import estimate_stt_cost
    from app.core.db import get_session_factory
    from app.services import ai_usage as meter
    from app.services import kvkk

    # 1. target and permission
    if target not in TARGETS:
        raise VoiceError("unknown_target", targets=list(TARGETS))
    if target not in allowed_targets(perms):
        raise VoiceError("not_permitted")
    # 2. configured
    setup = await load_setup(session)
    reason = _config_reason(setup)
    if reason in ("disabled", "not_configured", "provider_unusable"):
        raise VoiceError("voice_not_configured", reason=reason)
    assert setup.primary is not None
    # 3. consent
    if not await kvkk.has_consent(session, user.id, PURPOSE):
        raise VoiceError(
            "voice_consent_required",
            purpose=PURPOSE,
            grant_api=f"POST /api/v1/me/consents/{PURPOSE}",
            grant_path=kvkk.GRANT_PATH,
        )
    # 4. the clip
    max_bytes = int(setup.caps.get("max_bytes") or 5_000_000)
    max_s = _max_seconds(setup)
    if not data:
        raise VoiceError("empty_audio")
    if len(data) > max_bytes:
        raise VoiceError("too_large", max_bytes=max_bytes)
    kind = clip_checks.canonical_type(content_type)
    if kind is None or clip_checks.sniff(data) != kind:
        raise VoiceError("unsupported_audio", mime_types=list(clip_checks.TYPES))
    header_s = clip_checks.duration_s(data, kind)
    if header_s is not None and header_s > max_s + 0.5:
        raise VoiceError("too_long", max_seconds=max_s)
    language = lang if lang in gw.VOICE_LANGUAGES else setup.settings["language"]
    user_id = user.id
    sha = hashlib.sha256(data).hexdigest()
    started = time.monotonic()
    base: dict[str, Any] = {
        "user_id": user_id,
        "feature": FEATURE,
        "modality": "audio_in",
        "prompt_sha256": sha,
        "prompt_chars": len(data),
        "detail": f"target={target}",
    }

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    # 5. transfer basis
    attempts = [a for a in setup.attempts if a.transfer_ok]
    if not setup.primary.transfer_ok:
        await meter.record(
            **base,
            provider=setup.primary.provider,
            model=setup.primary.model,
            outcome="refused_by_guardrail",
            reason_code="ai_transfer_basis_missing",
            guard_verdict="refused",
            latency_ms=elapsed(),
        )
        raise VoiceError("ai_transfer_basis_missing", provider=setup.primary.provider)
    # 6. rate and concurrency (the text gateway's per-person gates)
    limits = await gw.get_limits(session)
    guards = await gw.get_guardrails(session)
    if guards.get("rate_limit", True) and not pipeline._RATE.hit(
        user_id, per_minute=int(limits.get("requests_per_minute") or 0)
    ):
        raise VoiceError("rate_limited")
    if not pipeline._CONCURRENCY.acquire(user_id, limit=int(limits.get("max_concurrent") or 0)):
        raise VoiceError("too_many_concurrent")
    reservation = None
    try:
        # 7. limits: reserve this clip's length (the cap when the header has none)
        est_s = header_s if header_s is not None else float(max_s)
        prices = setup.settings.get("prices_per_min") or {}
        est_cost, _ = estimate_stt_cost(setup.primary.provider, setup.primary.model, est_s, prices=prices)
        try:
            async with get_session_factory()() as s:
                reservation = await meter.reserve_audio(s, user_id=user_id, est_audio_s=est_s, est_cost=est_cost)
        except meter.LimitRefusal as exc:
            await meter.record(
                **base,
                provider=setup.primary.provider,
                model=setup.primary.model,
                outcome="limit_reached",
                reason_code=exc.code,
                guard_verdict="refused",
                latency_ms=elapsed(),
            )
            if exc.code == "ai_budget_exceeded":
                raise VoiceError("ai_budget_exceeded", scope=exc.scope) from None
            raise VoiceError(
                "ai_voice_limit_reached",
                scope=exc.scope,
                used_s=round(exc.used),
                limit_s=round(exc.limit),
                used_min=round(exc.used / 60, 1),
                limit_min=round(exc.limit / 60, 1),
            ) from None
        vocabulary = await catalog_terms(session) if setup.settings["vocabulary"] == "catalog" else []
        timeout = float(setup.caps.get("timeout_s") or 60)
        # 8. the provider, one fallback
        result: Transcript | None = None
        served: Attempt | None = None
        for att in attempts:
            try:
                adapter = registry.make_speech_adapter(
                    att.provider,
                    secrets=att.secrets,
                    config=att.config,
                    timeout_s=timeout,
                    transport=pipeline.TEST_TRANSPORT[0],
                )
                result = await asyncio.wait_for(
                    adapter.transcribe(data, kind, model=att.model, language=language, vocabulary=vocabulary),
                    timeout=timeout + 5,
                )
                served = att
                break
            except (ProviderError, TimeoutError) as exc:
                text = "the speech provider did not answer in time" if isinstance(exc, TimeoutError) else str(exc)
                await meter.record(
                    **base,
                    provider=att.provider,
                    model=att.model,
                    outcome="provider_error",
                    reason_code="provider_error",
                    detail=text[:255],
                    latency_ms=elapsed(),
                )
                log.info("voice provider %s failed (%s)", att.provider, type(exc).__name__)
        if result is None or served is None:
            raise VoiceError("provider_error")
        # 9. meter with the real length; a clip longer than the cap by the provider's count is refused
        seconds = result.duration_s if result.duration_s is not None else (header_s or 0.0)
        cost, version = estimate_stt_cost(served.provider, served.model, seconds, prices=prices)
        row: dict[str, Any] = {
            **base,
            "provider": served.provider,
            "model": served.model,
            "audio_ms": int(round(seconds * 1000)),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": cost,
            "price_version": version,
            "request_id": (result.request_id or "")[:64] or None,
            "inference_geo": str(served.config.get("region") or "")[:32] or None,
            "latency_ms": elapsed(),
            "guard_verdict": "skipped",
        }
        if seconds > max_s + GRACE_S:
            await meter.record(**row, outcome="refused_by_guardrail", reason_code="too_long")
            raise VoiceError("too_long", max_seconds=max_s)
        text, warnings = clean_text(result.text, target)
        await meter.record(**row, outcome="ok")
        return {
            "text": text,
            "duration_s": round(seconds, 2),
            "language": (result.language or language)[:8],
            "provider": served.provider,
            "model": served.model,
            "target": target,
            "review_required": True,
            "warnings": warnings,
        }
    finally:
        meter.settle(reservation)
        pipeline._CONCURRENCY.release(user_id)


__all__ = [
    "CONFIG_REASONS",
    "FEATURE",
    "PURPOSE",
    "TARGETS",
    "allowed_targets",
    "clean_text",
    "load_setup",
    "status",
    "transcribe",
]
