"""Per-person exclusion from AI prompts (KVKK consent ``ai_personal``; backend asks batch 3 item 5).

A person who **withdrew** the ``ai_personal`` consent (``DELETE /me/consents/ai_personal``; their latest consent row
for that purpose has ``withdrawn_at``) is kept out of every request SmartSched sends to the model from then on:

* :func:`load_redactor` reads the excluded people (the account's full name, first + last name, e-mail, a dotted
  username, and the name of every instructor record linked to the account, with and without titles);
* :class:`AIClient <app.ai.client.AIClient>` gets the redactor from :func:`app.ai.client.get_client`, so every prompt
  builder honours it (elicitation, chat, explanations, the Ingestion Council): before a request, each of those
  names in ``system`` and ``messages`` -- Turkish-case-insensitive (İ/ı/I/i), ASCII-folded (``Işık`` = ``Isik``),
  NBSP / dots / underscores between the words -- becomes ``[KİŞİ_n]``; after the answer, a token in the model's text
  or tool input is mapped back to the person's name on the server, so a rule about that person still resolves.

What a never-given consent means is the setting ``kvkk.ai_personal_default`` (consent gates 2026-10-16; admin, ``PUT
/settings`` ``extra``): ``excluded`` (default, owner decision 2026-10-17 R1-M-07) -- "not granted = excluded", every
account without an active grant is kept out, so only people who granted ``ai_personal`` are sent by name; ``included``
(an admin's choice) -- never-granted is not withdrawn, the institution's AI sign-off (``app/ai/policy.py``) is the
basis until the person withdraws.

Images and scanned PDFs sent as binary blocks cannot be redacted (vision is off by default).
Streamed text deltas show the token; the final message carries the name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.importers import normalize as n

TOKEN = "[KİŞİ_{}]"
_TOKEN_RX = re.compile(r"\[\s*K[İIi][ŞS][İIi]_(\d+)\s*\]")
#: letters that Turkish data writes interchangeably (case, dotted / dotless i, ASCII folding)
_GROUPS = ("cçCÇ", "gğGĞ", "ıiIİ", "oöOÖ", "sşSŞ", "uüUÜ")
_SEP = r"[\s ._-]+"
#: block-level keys that are never prompt text (ids, tool names, binary data, signatures)
_SKIP_KEYS = frozenset({"type", "id", "tool_use_id", "media_type", "cache_control", "signature", "data", "url"})
_SKIP_BLOCKS = frozenset({"thinking", "redacted_thinking", "image"})


def _char(ch: str) -> str:
    for g in _GROUPS:
        if ch in g:
            return f"[{g}]" + ("̇?" if ch in "ıiIİ" else "")
    if ch.isalpha():
        return "[" + re.escape(ch.lower()) + re.escape(ch.upper()) + "]"
    return re.escape(ch)


def _pattern(variant: str) -> str | None:
    text = n.clean_text(variant) or ""
    if "@" in text:  # an e-mail address, as written (case-insensitive)
        return "".join(_char(c) for c in text) if len(text) >= 6 else None
    words = [w for w in re.split(r"[\s._-]+", text) if w]
    if len(words) < 2 or any(len(w) < 2 for w in words):
        return None  # one word ("Ali") is not a person: too many false hits
    return _SEP.join("".join(_char(c) for c in w) for w in words)


#: the letter equivalence of :func:`_char`, folded (``Ç``/``ç`` -> ``c``, ``İ``/``I``/``ı`` -> ``i`` ...)
_FOLD = {ch: g[0].lower() if g[0] != "ı" else "i" for g in _GROUPS for ch in g}
_SPLIT = re.compile(r"[\W_]+")
_CACHE_SIZE = 64


def _tokens(text: str) -> set[str]:
    """The words of ``text`` in the folded form the patterns match (the combining dot of ``i̇`` dropped)."""
    folded = "".join(_FOLD.get(ch) or ch.lower() for ch in text.replace("\u0307", ""))
    return {t for t in _SPLIT.split(folded) if t}


@dataclass
class Redactor:
    """``people`` = (display name, name variants) per excluded person, in a stable order (token ``[KİŞİ_<i>]``).

    A text is matched only against the people whose every name word occurs in it (a word prefilter: with
    ``kvkk.ai_personal_default = excluded`` every account without a grant is in the list, hundreds of people, and one
    alternation over all of them is far too slow). The prefilter tokenises the text and the variants the same way
    (folded letters, split at every non-word character), so it never drops a name the full pattern would match."""

    people: list[tuple[str, list[str]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        parts: list[tuple[int, str, frozenset[str]]] = []
        for i, (_, variants) in enumerate(self.people, start=1):
            for v in variants:
                p = _pattern(v)
                if p:
                    parts.append((i, p, frozenset(_tokens(n.clean_text(v) or ""))))
        parts.sort(key=lambda x: -len(x[1]))  # longest first: "Dr. Ayşe Yılmaz" before "Ayşe Yılmaz"
        self._index = [i for i, _, _ in parts]
        self._parts = [(p, words) for _, p, words in parts]
        self._compiled: dict[tuple[int, ...], re.Pattern[str]] = {}

    def __bool__(self) -> bool:
        return bool(self._parts)

    def _rx_for(self, value: str) -> re.Pattern[str] | None:
        words = _tokens(value)
        hit = tuple(k for k, (_, need) in enumerate(self._parts) if need <= words)
        if not hit:
            return None
        rx = self._compiled.get(hit)
        if rx is None:
            if len(self._compiled) >= _CACHE_SIZE:
                self._compiled.clear()
            rx = self._compiled[hit] = re.compile(
                "|".join(f"(?<!\\w)(?P<p{k}>{self._parts[k][0]})(?!\\w)" for k in hit)
            )
        return rx

    # ------------------------------------------------------------------ outgoing

    def text(self, value: str) -> str:
        if not self._parts or not value:
            return value
        rx = self._rx_for(value)
        if rx is None:
            return value

        def sub(m: re.Match[str]) -> str:
            k = int((m.lastgroup or "p0")[1:])
            return TOKEN.format(self._index[k])

        return rx.sub(sub, value)

    def payload(self, obj: Any, key: str | None = None) -> Any:
        """A redacted copy of ``system`` / ``messages`` (dicts and lists rebuilt; the caller's objects untouched)."""
        if not self._parts:
            return obj
        if isinstance(obj, str):
            return obj if key in _SKIP_KEYS else self.text(obj)
        if isinstance(obj, list):
            return [self.payload(x, key) for x in obj]
        if isinstance(obj, dict):
            if obj.get("type") in _SKIP_BLOCKS:
                return obj
            block = obj.get("type") in ("tool_use", "server_tool_use")
            return {
                k: (v if (k in _SKIP_KEYS or (block and k == "name")) else self.payload(v, k)) for k, v in obj.items()
            }
        return obj

    # ------------------------------------------------------------------ incoming

    def restore_text(self, value: str) -> str:
        if not self.people or not value:
            return value

        def sub(m: re.Match[str]) -> str:
            i = int(m.group(1))
            return self.people[i - 1][0] if 1 <= i <= len(self.people) else m.group(0)

        return _TOKEN_RX.sub(sub, value)

    def restore(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.restore_text(obj)
        if isinstance(obj, list):
            return [self.restore(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.restore(v) for k, v in obj.items()}
        return obj

    def restore_message(self, message: Any) -> Any:
        """Tokens in the answer's text and tool inputs -> the person's name (on the server, after the call)."""
        if not self.people:
            return message
        for block in getattr(message, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "text" and isinstance(getattr(block, "text", None), str):
                block.text = self.restore_text(block.text)
            elif kind in ("tool_use", "server_tool_use") and isinstance(getattr(block, "input", None), dict):
                block.input = self.restore(block.input)
        return message


async def excluded_user_ids(session: AsyncSession) -> list[int]:
    """Accounts kept out of AI requests: those whose latest ``ai_personal`` consent row is withdrawn (the per-person
    switch) and, with ``kvkk.ai_personal_default = excluded``, every account without an active grant."""
    from app.models import User
    from app.models.kvkk import Consent
    from app.services.kvkk import ai_personal_default

    q = select(Consent.user_id, Consent.withdrawn_at).where(Consent.purpose == "ai_personal").order_by(Consent.id)
    latest: dict[int, bool] = {}
    for uid, withdrawn in (await session.execute(q)).all():
        if uid is not None:
            latest[int(uid)] = withdrawn is not None
    if await ai_personal_default(session) == "excluded":
        everyone = (await session.execute(select(User.id))).scalars()
        return sorted(int(uid) for uid in everyone if latest.get(int(uid), True))
    return sorted(uid for uid, out in latest.items() if out)


async def load_redactor(session: AsyncSession) -> Redactor:
    from app.models import Instructor, User

    ids = await excluded_user_ids(session)
    if not ids:
        return Redactor()
    users = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars()}
    linked: dict[int, list[Instructor]] = {}
    for i in (await session.execute(select(Instructor).where(Instructor.user_id.in_(ids)))).scalars():
        linked.setdefault(int(i.user_id or 0), []).append(i)
    people: list[tuple[str, list[str]]] = []
    for uid in ids:
        u = users.get(uid)
        if u is None:
            continue
        variants = [u.full_name or "", f"{u.firstname or ''} {u.lastname or ''}", u.email or ""]
        if u.username and re.search(r"[._]", u.username):
            variants.append(u.username)
        for ins in linked.get(uid, []):
            variants += [ins.full_name or "", ins.canonical_name or ""]
        variants = [v for v in dict.fromkeys(n.clean_text(v) or "" for v in variants) if v]
        display = next((n.clean_text(i.full_name) for i in linked.get(uid, []) if i.full_name), None)
        people.append((display or n.clean_text(u.full_name) or TOKEN.format(len(people) + 1), variants))
    return Redactor(people)


__all__ = ["TOKEN", "Redactor", "excluded_user_ids", "load_redactor"]
