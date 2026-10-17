"""``render(kind, locale, **ctx) -> Rendered(subject, html, text)``: one renderer for every e-mail.

Two ways in, one output:

* **template mode** (previews, new senders): the kind's shipped strings (:mod:`app.emails.strings`) with the
  ``{placeholders}`` filled from ``ctx``; lists (``items``, ``suggestions``) become rows and chips;
* **composed mode** (the wired send paths: approvals, bookings, KVKK, AI alerts): the caller passes ``subject`` and
  ``body`` -- the same words the in-app bell shows -- and the renderer themes them. The text part *starts with the
  body exactly* (only NBSP / trailing spaces cleaned), so "who gets what" stays the same; the HTML turns ``- `` lines
  into rows, ``Gerekçe: / Reason:`` into a callout and ``Önerilen derslikler / Suggested rooms`` into chips.

``strings`` are the organisation's overrides (translation set ``email``) and win over both; they are text, so they
are escaped like every user value (no HTML injection through an override). Unknown placeholders in an override stay
as written instead of failing the message. Links: only ``https``, ``http`` and ``mailto``; a relative link needs
``base_url`` (the panel's public URL) or the button is left out.
"""

from __future__ import annotations

import html as _html
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from app.emails import layout
from app.emails.kinds import KindSpec, spec
from app.emails.strings import shipped

LOGO_CID = "logo@smartsched"
_ASSETS = Path(__file__).with_name("assets")
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_SPACES = str.maketrans({"\xa0": " ", " ": " ", " ": " ", " ": " ", "﻿": ""})


def logo_png() -> bytes:
    """The app tile (96 px, shown at 40 px): readable on light and dark backgrounds (docs/design/brand.md)."""
    return (_ASSETS / "smartsched-tile-96.png").read_bytes()


@dataclass(frozen=True)
class Brand:
    org_name: str = ""
    base_url: str = ""
    logo_src: str = f"cid:{LOGO_CID}"
    reply_to: str | None = None


@dataclass(frozen=True)
class Rendered:
    subject: str
    html: str
    text: str
    kind: str = "generic"
    locale: str = "tr"
    preheader: str = ""
    cta_url: str | None = None

    def __iter__(self) -> Iterator[str]:  # ``subject, html, text = render(...)``
        return iter((self.subject, self.html, self.text))

    @property
    def uses_cid_logo(self) -> bool:
        return f"cid:{LOGO_CID}" in self.html


class _Keep(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def clean(value: Any) -> str:
    """Text as a reader should see it: NBSP and narrow spaces as spaces, no trailing spaces, no BOM."""
    s = str(value).translate(_SPACES)
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").replace("\r", "\n").split("\n"))


def one_line(value: Any) -> str:
    return " ".join(clean(value).split())


def esc(value: Any) -> str:
    return _html.escape(str(value), quote=True)


def safe_url(url: Any, base_url: str = "") -> str | None:
    u = one_line(url or "")
    if not u:
        return None
    if u.startswith("/") and not u.startswith("//"):
        if not base_url:
            return None
        u = base_url.rstrip("/") + u
    scheme = urlsplit(u).scheme.lower()
    if scheme not in ("https", "http", "mailto"):
        return None
    return quote(u, safe=":/?#[]@!$&()*+,;=%~-._")


def _fill(template: str | None, values: Mapping[str, Any]) -> str | None:
    if template is None:
        return None
    try:
        return template.format_map(_Keep(values))
    except (ValueError, IndexError, KeyError, AttributeError):  # a stray "{" in an override
        return template


# --------------------------------------------------------------------------------------------------
# Body -> blocks
# --------------------------------------------------------------------------------------------------

_REASON = re.compile(r"^(?:Gerekçe|Reason)\s*:\s*(.+)$")
_SUGGEST = re.compile(r"^(?:Önerilen derslikler|Suggested rooms)\b[^:]*:\s*(.+?)\.?$")
_ITEM = re.compile(r"^\s*[-•]\s+(.+)$")


def _blocks(body: str, S: Mapping[str, str], tone: str) -> list[str]:
    out: list[str] = []
    para: list[str] = []
    rows: list[str] = []

    def flush() -> None:
        if para:
            out.append(layout.paragraph("<br>".join(esc(x) for x in para)))
            para.clear()
        if rows:
            out.append(layout.items([esc(x) for x in rows]))
            rows.clear()

    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        m = _ITEM.match(line)
        if m:
            if para:
                out.append(layout.paragraph("<br>".join(esc(x) for x in para)))
                para.clear()
            rows.append(m.group(1))
            continue
        if rows:
            flush()
        m = _REASON.match(line)
        if m:
            flush()
            danger = tone if tone in ("danger", "warning") else "danger"
            out.append(layout.callout("reason", danger, esc(S["layout.reason"]), esc(m.group(1))))
            continue
        m = _SUGGEST.match(line)
        if m:
            flush()
            names = [x.strip() for x in m.group(1).split(",") if x.strip()]
            out.append(layout.callout("suggestions", "info", esc(S["layout.suggestions"]), layout.chips([esc(x) for x in names])))
            continue
        para.append(line)
    flush()
    return out


# --------------------------------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------------------------------


def _values(kind: KindSpec, ctx: Mapping[str, Any], S: Mapping[str, str], brand: Brand) -> dict[str, Any]:
    v: dict[str, Any] = {}
    for k, val in ctx.items():
        if val is None:
            continue
        if isinstance(val, list | tuple):
            v[k] = [one_line(x) for x in val if x is not None and one_line(x)]
        else:
            v[k] = clean(val).strip()
    v.setdefault("org", brand.org_name or "SmartSched")
    v.setdefault("name", "")
    for f in kind.enums:
        if f in v and isinstance(v[f], str):
            v[f] = S.get(f"{kind.kind}.{f}.{v[f]}", v[f])
    if isinstance(v.get("items"), list):
        v["items"] = "\n".join(f"- {x}" for x in v["items"])
    sugg = v.get("suggestions")
    if isinstance(sugg, list):
        v["alt"] = f"\n{S['layout.suggestions']}: {', '.join(sugg)}." if sugg else ""
    v.setdefault("alt", "")
    if kind.kind == "booking_cancelled":
        reason = v.get("reason")
        if reason:
            from app.services.bookings_i18n import cancel_reason_code  # lazy: bookings_i18n imports app.emails

            code = cancel_reason_code(reason)
            if code is not None:
                reason = _fill(S.get(f"booking_cancelled.reason.{code[0]}"), {"id": code[1]}) or reason
            v["reason"] = _fill(S.get("booking_cancelled.reason"), {"reason": reason}) or ""
        else:
            v["reason"] = ""
    if kind.kind == "room_owner_booking" and "series" not in v:
        sid = v.get("series_id")
        v["series"] = _fill(S.get("room_owner.series"), {"series_id": sid}) if sid else ""
    for k, val in list(v.items()):
        if isinstance(val, list):
            v[k] = ", ".join(val)
    return v


def render(
    kind: str,
    locale: str = "tr",
    *,
    strings: Mapping[str, str] | None = None,
    brand: Brand | None = None,
    **ctx: Any,
) -> Rendered:
    """Render one e-mail. ``strings``: the organisation's overrides of set ``email`` (they win); ``brand``: the
    organisation's name, the panel's public URL (relative links) and the logo source. Context keys used by every
    kind: ``subject`` / ``heading`` / ``body`` (composed mode), ``cta_url`` or ``link`` (+ ``base_url``),
    ``cta_label``, ``preheader``, ``code``, ``details`` ([(label, value)]), ``note``; the rest fill placeholders."""
    lang = "tr" if (locale or "").lower().startswith("tr") else "en"
    k = spec(kind)
    overrides = dict(strings or {})
    S: dict[str, str] = {**shipped(lang), **overrides}
    brand = brand or Brand(org_name=one_line(ctx.get("org") or ""), base_url=str(ctx.get("base_url") or ""))
    base_url = brand.base_url or str(ctx.get("base_url") or "")
    keys = k.keys
    composed = ctx.get("body") is not None
    values = _values(k, {x: y for x, y in ctx.items() if x not in ("subject", "heading", "body")}, S, brand)

    def pick(part: str, given: Any = None) -> str | None:
        key = keys[part]
        if key in overrides and not (composed and k.caller_applies_overrides):
            return _fill(overrides[key], values)
        if given is not None:
            return clean(given)
        return _fill(S.get(key), values)

    subject = one_line(pick("subject", ctx.get("subject")) or (k.label_tr if lang == "tr" else k.label_en))[:255]
    heading = one_line(ctx.get("heading") or _fill(S.get(keys["heading"]), values) or subject)
    if composed:
        body = clean(ctx["body"]).strip("\n")
        lead = _fill(overrides[keys["intro"]], values) if keys["intro"] in overrides and not k.caller_applies_overrides else None
        if lead:
            body = f"{clean(lead).strip()}\n\n{body}"
    else:
        body = clean(pick("intro") or "").strip("\n")
    note_text = clean(ctx.get("note") or _fill(S.get(keys["note"]), values) or "").strip()
    code = one_line(ctx.get("code") or "")
    detail_rows = [(one_line(a), one_line(b)) for a, b in (ctx.get("details") or [])]
    cta_url = safe_url(ctx.get("cta_url") or ctx.get("link") or "", base_url)
    if cta_url is None and not ctx.get("cta_url") and not ctx.get("link") and k.path and base_url:
        cta_url = safe_url(k.path, base_url)
    cta_label = one_line(ctx.get("cta_label") or _fill(S.get(keys["cta"]), values) or "")
    if not cta_label:
        cta_url = None
    first = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
    preheader = one_line(ctx.get("preheader") or _fill(S.get(keys["preheader"]), values) or first)[:140]
    eyebrow = one_line(k.label_tr if lang == "tr" else k.label_en) if k.kind != "generic" else ""

    # --- HTML ---
    blocks = _blocks(body, S, k.tone)
    if code:
        blocks.append(layout.code_box(esc(S["layout.code"]), esc(code)))
    if detail_rows:
        blocks.append(layout.details([(esc(a), esc(b)) for a, b in detail_rows]))
    if cta_url:
        blocks.append(layout.button(esc(cta_url), esc(cta_label), esc(S["layout.button_fallback"])))
    if note_text:
        blocks.append(layout.note("<br>".join(esc(x) for x in note_text.split("\n"))))
    org = values.get("org") or "SmartSched"
    footer_reason = _fill(S["layout.footer.reason"], {"org": org}) or ""
    prefs_url = safe_url("/profile#notifications", base_url)
    footer_lines = [esc(footer_reason)]
    if not brand.reply_to:
        footer_lines.append(esc(S["layout.footer.no_reply"]))
    footer_lines.append(esc(S["layout.footer.sent_by"]))
    html_out = layout.page(
        layout.Page(
            lang=lang,
            title=esc(subject),
            preheader=esc(preheader),
            tone=k.tone,
            eyebrow=esc(eyebrow),
            heading=esc(heading),
            blocks=blocks,
            org=esc(org),
            logo_src=esc(brand.logo_src),
            logo_alt=esc(S["layout.logo_alt"]),
            footer_lines=footer_lines,
            prefs_url=esc(prefs_url) if prefs_url else None,
            prefs_label=esc(S["layout.footer.prefs"]),
        )
    )

    # --- text ---
    parts: list[str] = [body] if composed else [heading, body]
    if code:
        parts.append(f"{S['layout.code']}:\n{code}")
    if detail_rows:
        parts.append("\n".join(f"{a}: {b}" for a, b in detail_rows))
    if cta_url:
        parts.append(f"{cta_label}: {cta_url}")
    if note_text:
        parts.append(note_text)
    foot = [footer_reason]
    if prefs_url:
        foot.append(f"{S['layout.footer.prefs']}: {prefs_url}")
    foot.append(S["layout.footer.sent_by"])
    text_out = "\n\n".join(p for p in parts if p) + "\n\n-- \n" + "\n".join(foot) + "\n"
    return Rendered(subject, html_out, text_out, kind, lang, preheader, cta_url)


def placeholders_in(template: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(template or "")))
