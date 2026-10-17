"""Flow loop round 2, sweeper 3 (item 3): the ``booking_cancelled`` notification decodes the cancel-reason *codes*
the backend writes (``replaced_by_series:<id>``, ``undo_of:<id>``) into the reader's language instead of printing
"Gerekçe: replaced_by_series:8" raw (mirror of the frontend ``components/bookings/cancel-reason.ts``)."""

from __future__ import annotations

import pytest
from app.models import Translation
from app.services import bookings_i18n as i18n
from sqlalchemy.ext.asyncio import AsyncSession


def test_reason_code_parses_only_the_two_codes() -> None:
    assert i18n.cancel_reason_code("replaced_by_series:8") == ("replaced_by_series", 8)
    assert i18n.cancel_reason_code("undo_of:41") == ("undo_of", 41)
    assert i18n.cancel_reason_code("replaced_by_series:x") is None
    assert i18n.cancel_reason_code("Toplantı iptal") is None
    assert i18n.cancel_reason_code(None) is None


@pytest.mark.parametrize(
    ("reason", "lang", "expected"),
    [
        ("replaced_by_series:8", "tr", "Seri #8 ile değiştirildi"),
        ("replaced_by_series:8", "en", "Replaced by series #8"),
        ("undo_of:41", "tr", "Geri alma: #41"),
        ("undo_of:41", "en", "Undo of #41"),
        ("Toplantı iptal edildi", "tr", "Toplantı iptal edildi"),  # a person's words stay as typed
        ("", "tr", None),
        (None, "en", None),
    ],
)
async def test_cancel_reason_text_reads_in_the_readers_language(
    session: AsyncSession, reason: str | None, lang: str, expected: str | None
) -> None:
    assert await i18n.cancel_reason(session, lang, reason) == expected


async def test_cancel_reason_follows_the_admin_override(session: AsyncSession) -> None:
    session.add(
        Translation(
            language="tr", set="email", key="booking_cancelled.reason.replaced_by_series", text="Yeni seri: {id}"
        )
    )
    await session.commit()
    assert await i18n.cancel_reason(session, "tr", "replaced_by_series:3") == "Yeni seri: 3"
    # the body line still wraps it
    body = await i18n.text(
        session, "tr", "booking_cancelled.reason", reason=await i18n.cancel_reason(session, "tr", "undo_of:5")
    )
    assert body == "\nGerekçe: Geri alma: #5"
