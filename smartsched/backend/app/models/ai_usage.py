"""AI gateway metering (wave 3 W3-AI, alembic 0034_ai_usage; voice columns 0042_ai_usage_audio; units and
``ai_reservations`` 0046_ai_quota_units).

``ai_usage``: one row per model call that went through the gateway (``app/ai/client.py`` :class:`AIClient`) and
one row per call the gateway refused before it left the server. The row never holds prompt or answer text, only
who, which feature, which provider and model, the token counts, the estimated cost, the latency and the outcome:

* ``ok`` - the provider answered and the output passed the output guard;
* ``refused_by_guardrail`` - a guardrail refused the input (scope, prompt injection, rate limit) or the output
  (unexpected tool call, invalid structured output); ``reason_code`` says which;
* ``provider_error`` - the provider failed (auth, rate limit, 5xx, network, refusal by the provider's own
  safety system: ``reason_code`` ``provider_refusal``);
* ``limit_reached`` - a per-user token limit (``reason_code`` ``ai_limit_reached``) or the org budget
  (``ai_budget_exceeded``) was spent.

Research R-AI-04 (docs/research/2026-10-17-state-of-the-art.md §2.2): a hash and the length of the prompt, never the
text; the price-table version; the request id; the guard verdict; where inference ran.

Rows are ordinary rows (a KVKK erasure may delete a person's rows; ``user_id`` is set NULL when the account is
deleted so the org totals stay right).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

OUTCOMES = ("ok", "refused_by_guardrail", "provider_error", "limit_reached")
MODALITIES = ("text", "audio_in", "audio_out")


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_outcome_created", "outcome", "created_at"),
        Index("ix_ai_usage_created_faculty", "created_at", "faculty_id"),
        Index("ix_ai_usage_created_department", "created_at", "department_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    #: rules | chat | intake | explain | booking_nl | voice_stt | guard | test | other
    feature: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    #: a short, content-free note (the guard's rule name, the provider's error class); never prompt text
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: SHA-256 and length of the serialised request (system + messages + tools); the text itself is never stored
    prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)
    #: version of the price table the cost was estimated with (``app.ai.client.PRICE_TABLE_VERSION`` or ``synced``)
    price_version: Mapped[str | None] = mapped_column(String(24), nullable=True)
    #: the input guard's verdict: pass | flagged (uploaded text neutralised) | refused | skipped
    guard_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: where the provider says inference ran (Anthropic ``usage.inference_geo``; Bedrock / Vertex: the region)
    inference_geo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: voice (VO-02): milliseconds of audio a speech-to-text call processed (``prompt_sha256`` is then the SHA-256
    #: of the clip and ``prompt_chars`` its byte length; the audio itself is never stored)
    audio_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: ``text`` | ``audio_in`` (speech to text) | ``audio_out`` (read-aloud, later)
    modality: Mapped[str] = mapped_column(String(12), default="text", server_default="text")
    #: the caller's department (programme) and its faculty when the row was recorded (HB-10, 0046): a snapshot, so
    #: the faculty totals do not move when a person changes department; NULL for background jobs and old rows
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faculty_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def total_tokens(self) -> int:
        return (
            int(self.input_tokens or 0)
            + int(self.output_tokens or 0)
            + int(self.cache_read_tokens or 0)
            + int(self.cache_write_tokens or 0)
        )


class AIReservation(Base):
    """An in-flight gateway call's estimate (``kind = call``) or one counted request of the per-minute limit
    (``kind = rate``), shared by every API worker (HB-10, alembic 0046_ai_quota_units). Transient: a call row is
    deleted when the call settles and ignored after ``expires_at``; rate rows are swept after two minutes."""

    __tablename__ = "ai_reservations"
    __table_args__ = (
        Index("ix_ai_reservations_user_created", "user_id", "created_at"),
        Index("ix_ai_reservations_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: ``call`` | ``rate``
    kind: Mapped[str] = mapped_column(String(8), default="call", server_default="call")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    faculty_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    audio_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


__all__ = ["MODALITIES", "OUTCOMES", "AIReservation", "AIUsage"]
