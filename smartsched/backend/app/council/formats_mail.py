"""E-mail (.eml, RFC 5322) in the format registry (Phase 19 P19-A3).

* Parsed with :mod:`email` (``policy.default``). Of the headers only ``Subject`` and ``Date`` are kept (KVKK:
  ``From`` / ``To`` / ``Cc`` / ``Received`` name people and machines); the body is the plain-text part, or the
  HTML part with its markup removed by :mod:`html.parser` (scripts and styles dropped).
* Attachments re-enter the registry as files of the same job (:func:`attachments`, called by
  ``POST /council/jobs``): at most :data:`MAX_ATTACHMENTS`, depth 1 (an attached e-mail is read as a file, its own
  attachments are not unpacked), each with its own upload precheck, so an xlsx planning list sent by e-mail goes
  through the same importer as an uploaded one.
* The body is free text: the route is ``ai`` (its rows need a person, :mod:`app.council.airows`).
"""

from __future__ import annotations

import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import PurePath
from typing import Any

from app.core import safe_files
from app.council import text as tx
from app.council.formats import FormatLimits, FormatSpec, MiB, Probe, register
from app.council.render import Rendered, RenderError, Unit

MAX_ATTACHMENTS = 10
_HEADER_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9-]{1,40}):[ \t]?.*$")
_KNOWN = {"from", "to", "subject", "date", "mime-version", "received", "message-id", "cc", "return-path", "reply-to"}
_SAFE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    p.close()
    return "".join(p.parts)


def parse(data: bytes) -> EmailMessage:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"cannot read the e-mail: {type(exc).__name__}") from exc
    assert isinstance(msg, EmailMessage)
    return msg


def body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):
        raw = part.get_payload(decode=True)
        content = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else ""
    if not isinstance(content, str):
        return ""
    return html_text(content) if part.get_content_subtype() == "html" else content


def _safe_name(name: str, k: int) -> str:
    base = PurePath(name.replace("\\", "/")).name or f"attachment-{k}"
    return (_SAFE.sub("_", base).strip(" .") or f"attachment-{k}")[:120]


def attachments(data: bytes) -> list[tuple[str, bytes]]:
    """(file name, bytes) of the attachments (at most :data:`MAX_ATTACHMENTS`; inline text parts excluded)."""
    msg = parse(data)
    out: list[tuple[str, bytes]] = []
    for k, part in enumerate(msg.iter_attachments(), start=1):
        if len(out) >= MAX_ATTACHMENTS:
            break
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            continue
        out.append((_safe_name(part.get_filename() or f"attachment-{k}", k), payload))
    return out


def _render(data: bytes, out: Rendered, lim: FormatLimits) -> None:
    msg = parse(data)
    n = 0
    for header in ("Subject", "Date"):
        v = msg.get(header)
        if v:
            n += 1
            out.units.append(Unit({"header": header.lower()}, tx.cell_text(str(v))))
    for i, line in enumerate(body_text(msg).splitlines(), start=1):
        t = tx.cell_text(line.lstrip(">*-• \t"))
        if t:
            out.units.append(Unit({"part": "body", "line": i}, t))
    names = [a for a, _ in attachments(data)]
    total = sum(1 for _ in msg.iter_attachments())
    if names:
        out.warnings.append(
            f"{len(names)} attachment(s) are read as files of this job: " + ", ".join(names[:MAX_ATTACHMENTS])
        )
    if total > MAX_ATTACHMENTS:
        out.warnings.append(f"only the first {MAX_ATTACHMENTS} of {total} attachments were read")
    out.warnings.append("only the Subject and Date headers were kept (sender and recipients are not read)")


def _precheck(data: bytes, lim: FormatLimits) -> None:
    msg = parse(data)
    if sum(1 for _ in msg.walk()) > 500:
        raise safe_files.UnsafeFileError(413, "the e-mail has more than 500 MIME parts")


def _sniff(p: Probe) -> float:
    if p.family != "text":
        return 0.0
    lines = p.text.lstrip("﻿").splitlines()[:40]
    names: set[str] = set()
    for line in lines:
        if not line.strip():
            break
        if line[:1] in (" ", "\t"):
            continue
        m = _HEADER_LINE.match(line)
        if not m:
            return 0.0
        names.add(m.group(1).lower())
    hits = len(names & _KNOWN)
    if hits >= 3 or (hits >= 2 and p.ext == ".eml"):
        return 0.95
    return 0.0


register(
    FormatSpec(
        "eml",
        "e-mail",
        "text",
        (".eml",),
        "ai",
        _sniff,
        _render,
        FormatLimits(max_bytes=15 * MiB),
        _precheck,
    )
)

__all__ = ["MAX_ATTACHMENTS", "attachments", "body_text", "html_text", "parse"]
