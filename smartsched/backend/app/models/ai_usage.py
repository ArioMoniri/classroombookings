"""AI gateway metering (wave 3 W3-AI, alembic 0034_ai_usage).

``ai_usage``: one row per model call that went through the gateway (``app/ai/client.py`` :class:`AIClient`) and
one row per call the gateway refused before it left the server. The row never holds prompt or answer text, only
who, which feature, which provider and model, the token counts, the estimated cost, the latency and the outcome:

* ``ok`` - the provider answered and the output passed the output guard;
* ``refused_by_guardrail`` - a guardrail refused the input (scope, prompt injection, rate limit) or the output
  (unexpected tool call, invalid structured output); ``reason_code`` says which;
* ``provider_error`` - the provider failed (auth, rate limit, 5xx, network, refusal by the provider's own
  safety system: ``reason_code`` ``provider_refusal``);
* ``limit_reached`` - an org budget or a per-user token limit was spent (``reason_code`` ``ai_limit_reached``).

Rows are ordinary rows (a KVKK erasure may delete a person's rows; ``user_id`` is set NULL when the account is
deleted so the org totals stay right).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

OUTCOMES = ("ok", "refused_by_guardrail", "provider_error", "limit_reached")


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_outcome_created", "outcome", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    #: rules | chat | intake | explain | guard | test | other
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

    @property
    def total_tokens(self) -> int:
        return (
            int(self.input_tokens or 0)
            + int(self.output_tokens or 0)
            + int(self.cache_read_tokens or 0)
            + int(self.cache_write_tokens or 0)
        )


__all__ = ["OUTCOMES", "AIUsage"]
