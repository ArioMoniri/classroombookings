"""Card builders (HB-07): every card the helper sends is made here or in an action module from database values.

Text that comes from the database (room names, course titles, booking notes) passes :func:`clean` first: markup and
link fragments are replaced, so a room called ``<b>A 204</b>`` or a note with a URL can never break the "no URL, no
HTML" rule of :mod:`app.ai.helper.schema`. Nothing here takes text from the model except :func:`answer`.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Literal

from app.ai.guardrails import sanitize_output_text
from app.ai.helper import schema as s
from app.ai.helper.index import FeatureEntry, Hit

#: helper.md A8: rows shown in a helper list by default (the full list stays on the page)
LIST_ROWS = 5
LINK_MARK = s.LINK_MARK


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def clean(text: object, limit: int = 400) -> str:
    """Database text made safe for a card: no control characters, no angle brackets, no links; trimmed."""
    return s.scrub(text, limit)


def txt(tr: str, en: str | None = None) -> s.Txt:
    return s.Txt(tr=clean(tr), en=clean(en if en is not None else tr))


def nav(entry: FeatureEntry, allowed_actions: Iterable[str] = ()) -> s.NavCard:
    allowed = set(allowed_actions)
    return s.NavCard(
        id=new_id(),
        feature_id=entry.id,
        kind=entry.kind,
        title=s.Txt(tr=entry.title.tr, en=entry.title.en),
        path=s.Texts(tr=list(entry.path.tr), en=list(entry.path.en)),
        steps=s.Texts(tr=list(entry.steps.tr), en=list(entry.steps.en)),
        anchor=entry.anchor,
        actions=[a for a in entry.actions if a in allowed][:4],
    )


def nav_hits(hits: Sequence[Hit], allowed_actions: Iterable[str] = (), limit: int = 3) -> list[s.NavCard]:
    allowed = list(allowed_actions)
    return [nav(h.entry, allowed) for h in hits[:limit]]


def status(
    kind: str, code: str, tr: str, en: str, fallback: Sequence[s.NavCard] = (), action: str | None = None
) -> s.LimitCard | s.RefusalCard | s.ErrorCard:
    if kind == "limit":
        return s.LimitCard(id=new_id(), code=code, message=txt(tr, en), fallback=list(fallback)[:3], action=action)
    if kind == "refusal":
        return s.RefusalCard(id=new_id(), code=code, message=txt(tr, en), fallback=list(fallback)[:3], action=action)
    return s.ErrorCard(id=new_id(), code=code, message=txt(tr, en), fallback=list(fallback)[:3], action=action)


#: markdown images, inline ``![alt](src)`` and reference ``![alt][ref]`` (HB-17 P2: local models emit them)
_MD_IMAGE = re.compile(r"!\[[^\]\n]{0,300}\](?:\([^)\n]{0,2000}\)|\[[^\]\n]{0,100}\])")


def strip_markdown_images(text: str) -> str:
    """``text`` without markdown image syntax (alt text and source both go; the card never shows images)."""
    return re.sub(r"[ \t]{2,}", " ", _MD_IMAGE.sub("", text or ""))


def answer(text: str, lang: str, *, source: Literal["ai", "index"] = "ai") -> s.AnswerCard:
    """The model's words: markdown images removed, the gateway's output cleaning (links, code, active HTML
    removed), then :func:`clean`."""
    cleaned = sanitize_output_text_str(strip_markdown_images(text))
    return s.AnswerCard(id=new_id(), text=clean(cleaned, 1200), lang="en" if lang == "en" else "tr", source=source)


def sanitize_output_text_str(text: str) -> str:
    """:func:`app.ai.guardrails.sanitize_output_text` works on a provider message; wrap one text block."""

    class _Block:
        type = "text"

        def __init__(self, t: str) -> None:
            self.text = t

    class _Msg:
        def __init__(self, t: str) -> None:
            self.content = [_Block(t)]

    msg = _Msg(text)
    sanitize_output_text(msg, feature="helper")
    return str(msg.content[0].text)


def dump(card: s.CardBase) -> dict[str, object]:
    return card.model_dump(mode="json", exclude_none=True)


__all__ = [
    "LIST_ROWS",
    "answer",
    "clean",
    "dump",
    "nav",
    "nav_hits",
    "new_id",
    "status",
    "strip_markdown_images",
    "txt",
]
