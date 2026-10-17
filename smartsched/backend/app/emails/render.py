"""``render(kind, locale, **ctx) -> Rendered(subject, html, text)``: one renderer for every e-mail.

Two ways in, one output (design: docs/design/v3/emails.md):

* **template mode** (previews, new senders): the kind's shipped strings (:mod:`app.emails.strings`) with the
  ``{placeholders}`` filled from ``ctx``; a variant ``<kind>.<field>.<value>.<part>`` wins over ``<kind>.<part>`` for
  every enum field of the kind; lists (``items``, ``suggestions``) become rows and chips;
* **composed mode** (the wired send paths: approvals, bookings, KVKK, AI alerts): the caller passes ``subject`` and
  ``body`` -- the same words the in-app bell shows -- and the renderer themes them. The text part *starts with the
  body exactly* (only NBSP / trailing spaces cleaned), so "who gets what" stays the same; the HTML turns ``- `` lines
  into rows, ``Gerekçe: / Reason:`` into a callout and ``Önerilen derslikler / Suggested rooms`` into chips. A shipped
  part whose placeholders the composed context cannot fill is left out (never a literal ``{room}``).

``strings`` are the organisation's overrides (translation set ``email``) and win over both; they are text, so they
are escaped like every user value (no HTML injection through an override). Unknown placeholders in an override stay
as written instead of failing the message. Links: only ``https``, ``http`` and ``mailto``; a relative link needs
``base_url`` (the panel's public URL) or the button is left out (§6 "Public URL").
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
    """The app tile (96 px, shown at 28 px): its own opaque blue, readable on light, dark and inverted mail."""
    return (_ASSETS / "smartsched-tile-96.png").read_bytes()


@dataclass(frozen=True)
class Brand:
    org_name: str = ""
    base_url: str = ""
    logo_src: str = f"cid:{LOGO_CID}"
    reply_to: str | None = None
    kvkk_url: str | None = None


@dataclass(frozen=True)
class Rendered:
    subject: str
    html: str
    text: str
    kind: str = "generic"
    locale: str = "tr"
    preheader: str = ""
    cta_url: str | None = None
    #: the message's own words without heading, button and footer: what the outbox stores as the body (= the bell)
    content: str = ""

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


def _tidy(text: str) -> str:
    # an empty name leaves "Merhaba , ..." / "Hello , ..."
    text = re.sub(r"[ \t]+([,.;:])", r"\1", text)
    return text.replace("SmartSched SmartSched", "SmartSched")  # no organisation name configured


def _fill(template: str | None, values: Mapping[str, Any]) -> str | None:
    """Fill ``template``; unknown placeholders stay as written (admin overrides)."""
    if template is None:
        return None
    try:
        return _tidy(template.format_map(_Keep(values)))
    except (ValueError, IndexError, KeyError, AttributeError):  # a stray "{" in an override
        return template


def _fill_strict(template: str | None, values: Mapping[str, Any]) -> str | None:
    """Fill a *shipped* string; ``None`` when one of its placeholders has no value (the part is left out)."""
    if template is None:
        return None
    if any(p not in values for p in _PLACEHOLDER.findall(template)):
        return None
    return _fill(template, values)


def spelled(code: str) -> str:
    """``K7Q4M2X9`` -> ``K 7 Q 4, M 2 X 9`` for screen readers (emails.md §10)."""
    groups = [code[i : i + 4] for i in range(0, len(code), 4)]
    return ", ".join(" ".join(g) for g in groups)


# --------------------------------------------------------------------------------------------------
# Body -> blocks
# --------------------------------------------------------------------------------------------------

_REASON = re.compile(r"^(?:Gerekçe|Reason)\s*:\s*(.+)$")
_SUGGEST = re.compile(
    r"^(?:Önerilen derslikler|Suggested rooms|Aynı saatte boş derslikler|Rooms free at the same "
    r"time)\b[^:]*:\s*(.+?)\.?$"
)
_ITEM = re.compile(r"^\s*[-•]\s+(.+)$")


def _blocks(body: str, S: Mapping[str, str], tone: str) -> list[str]:
    out: list[str] = []
    para: list[str] = []
    rows: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(layout.paragraph("<br>".join(esc(x) for x in para)))
            para.clear()

    def flush() -> None:
        flush_para()
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
            flush_para()
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
            out.append(
                layout.callout(
                    "suggestions", "info", esc(S["layout.suggestions"]), layout.chips([esc(x) for x in names])
                )
            )
            continue
        para.append(line)
    flush()
    return out


# --------------------------------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------------------------------


def _values(
    kind: KindSpec, ctx: Mapping[str, Any], S: Mapping[str, str], brand: Brand
) -> tuple[dict[str, Any], dict[str, str]]:
    """(placeholder values, raw enum values)."""
    v: dict[str, Any] = {}
    for k, val in ctx.items():
        if val is None or k == "details":
            continue
        if isinstance(val, list | tuple):
            v[k] = [one_line(x) for x in val if x is not None and one_line(x)]
        else:
            v[k] = clean(val).strip()
    if brand.org_name or "org" not in v:
        v["org"] = brand.org_name or v.get("org") or "SmartSched"
    v.setdefault("name", "")
    raw: dict[str, str] = {}
    if kind.kind == "booking_cancelled":
        reason = v.get("reason")
        if "body" not in ctx:
            from app.services.bookings_i18n import cancel_reason_code  # lazy: bookings_i18n imports app.emails

            code = cancel_reason_code(reason) if reason else None
            raw["cause"] = code[0] if code else ("admin" if reason else "none")
            if code is not None:
                reason = _fill(S.get(f"booking_cancelled.reason.{code[0]}"), {"id": code[1]}) or reason
            v["reason"] = (_fill(S.get("booking_cancelled.reason"), {"reason": reason}) or "") if reason else ""
    for f in kind.enums:
        if f in v and isinstance(v[f], str):
            raw[f] = v[f]
            label = S.get(f"{kind.kind}.{f}.{v[f]}")
            if label is not None:
                v[f] = _fill(label, v) or v[f]
    if isinstance(v.get("items"), list):
        v["items"] = "\n".join(f"- {x}" for x in v["items"])
    sugg = v.get("suggestions")
    if isinstance(sugg, list):
        v["alt"] = f"\n{S['layout.suggestions']}: {', '.join(sugg)}." if sugg else ""
    v.setdefault("alt", "")
    if kind.kind == "room_owner_booking" and "series" not in v:
        sid = v.get("series_id")
        v["series"] = _fill(S.get("room_owner.series"), {"series_id": sid}) if sid else ""
    for k, val in list(v.items()):
        if isinstance(val, list):
            v[k] = ", ".join(val)
    return v, raw


def render(
    kind: str,
    locale: str = "tr",
    *,
    strings: Mapping[str, str] | None = None,
    brand: Brand | None = None,
    **ctx: Any,
) -> Rendered:
    """Render one e-mail. ``strings``: the organisation's overrides of set ``email`` (they win); ``brand``: the
    organisation's name, the panel's public URL (relative links), the logo source, Reply-To and the KVKK notice URL.
    Context keys used by every kind: ``subject`` / ``heading`` / ``body`` (composed mode), ``cta_url`` or ``link``
    (+ ``base_url``), ``cta_label``, ``preheader``, ``code``, ``details`` ([(label, value)]), ``note``; enum fields of
    the kind pick variants; the rest fill placeholders."""
    lang = "tr" if (locale or "").lower().startswith("tr") else "en"
    k = spec(kind)
    overrides = dict(strings or {})
    S: dict[str, str] = {**shipped(lang), **overrides}
    brand = brand or Brand(org_name=one_line(ctx.get("org") or ""), base_url=str(ctx.get("base_url") or ""))
    base_url = brand.base_url or str(ctx.get("base_url") or "")
    keys = k.keys
    composed = ctx.get("body") is not None
    values, raw = _values(k, {x: y for x, y in ctx.items() if x not in ("subject", "heading", "body")}, S, brand)
    if composed and "body" in ctx:
        values.setdefault("what", "")

    base_strings = shipped(lang)

    def shipped_part(part: str) -> str | None:
        """The override or shipped string of ``part``, variant first. A shipped string whose placeholders the context
        cannot fill is left out in composed mode (never a literal ``{room}`` in a wired e-mail)."""
        base = keys[part]
        candidates = [f"{k.kind}.{f}.{raw[f]}.{part}" for f in k.enums if f in raw]
        if base.rsplit(".", 1)[0] != k.kind:  # CRBS keys (booking_created.body): kind-keyed parts come first
            candidates.append(f"{k.kind}.{part}")
        candidates.append(base)
        for key in candidates:
            if key in overrides and not (composed and k.caller_applies_overrides):
                return _fill(overrides[key], values)
            if key in base_strings:
                filled = _fill_strict(base_strings[key], values)
                if filled is None and not composed:
                    filled = _fill(base_strings[key], values)
                return filled
        return None

    def varies(part: str) -> bool:
        """Whether ``part`` has variants (a composed context cannot tell which applies: use the caller's subject)."""
        prefixes = tuple(f"{k.kind}.{f}." for f in k.enums)
        return bool(prefixes) and any(key.startswith(prefixes) and key.endswith(f".{part}") for key in base_strings)

    def override(part: str) -> str | None:
        key = keys[part]
        if key in overrides and not (composed and k.caller_applies_overrides):
            return _fill(overrides[key], values)
        return None

    # --- parts ---
    if composed:
        subject = one_line(override("subject") or ctx.get("subject") or (k.label_tr if lang == "tr" else k.label_en))
        heading_src = ctx.get("heading") or (None if varies("heading") else shipped_part("heading"))
        heading = one_line(heading_src or subject)
        body = clean(ctx["body"]).strip("\n")
        lead = override("intro")
        if lead:
            body = f"{clean(lead).strip()}\n\n{body}"
        status = "" if varies("status") else one_line(shipped_part("status") or "")
    else:
        subject = one_line(shipped_part("subject") or (k.label_tr if lang == "tr" else k.label_en))
        heading = one_line(ctx.get("heading") or shipped_part("heading") or subject)
        body = clean(shipped_part("intro") or "").strip("\n")
        status = one_line(shipped_part("status") or "")
    subject = subject[:255]
    after = clean(shipped_part("after") or "").strip()
    note_text = clean(ctx.get("note") or shipped_part("note") or "").strip()
    code = one_line(ctx.get("code") or "")
    detail_rows = [(one_line(a), one_line(b)) for a, b in (ctx.get("details") or [])]
    cta_url = safe_url(ctx.get("cta_url") or ctx.get("link") or "", base_url)
    if cta_url is None and not ctx.get("cta_url") and not ctx.get("link") and k.path and base_url:
        cta_url = safe_url(k.path, base_url)
    cta_label = one_line(ctx.get("cta_label") or shipped_part("cta") or "")
    if not cta_label:
        cta_url = None
    first = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
    preheader = one_line(ctx.get("preheader") or shipped_part("preheader") or first)
    if preheader == subject:
        preheader = first if first != subject else preheader
    preheader = preheader[:140]
    tone = k.tone_for(raw)

    org = values.get("org") or "SmartSched"
    if k.footer == "security":
        why = S["layout.footer.security"]
    elif k.footer == "legal":
        why = S["layout.footer.legal"]
    else:
        why = _fill_strict(S.get(keys["why"]), values) or S["layout.footer.reason"]
    prefs_url = safe_url("/profile?tab=notifications", base_url) if k.footer == "switchable" else None
    kvkk_url = safe_url(brand.kvkk_url or "", base_url) if brand.kvkk_url else None
    auto = (
        _fill(S["layout.footer.reply_to"], {"reply_to": brand.reply_to})
        if brand.reply_to
        else S["layout.footer.no_reply"]
    ) or ""
    footer_org = _fill(S["layout.footer.org"], {"org": org}) or org

    # --- HTML ---
    blocks = _blocks(body, S, tone)
    if code:
        blocks.append(layout.code_box(esc(S["layout.code"]), esc(code), esc(spelled(code))))
    if detail_rows:
        blocks.append(layout.details([(esc(a), esc(b)) for a, b in detail_rows], tone))
    if cta_url:
        blocks.append(layout.button(esc(cta_url), esc(cta_label), len(cta_label)))
        if k.fallback_url:
            blocks.append(layout.fallback(esc(S["layout.button_fallback"]), esc(cta_url)))
    if after:
        blocks.append(layout.note("<br>".join(esc(x) for x in after.split("\n"))))
    if note_text:
        if k.footer == "security" and "?" in note_text:  # §8.1 "Bu isteği siz yapmadınız mı?" as an info callout
            q, rest = note_text.split("?", 1)
            blocks.append(layout.callout("note", "info", esc(q.strip() + "?"), esc(rest.strip())))
        else:
            blocks.append(layout.note("<br>".join(esc(x) for x in note_text.split("\n"))))
    links: list[tuple[str, str]] = []
    if prefs_url:
        links.append((esc(prefs_url), esc(S["layout.footer.prefs"])))
    if kvkk_url:
        links.append((esc(kvkk_url), esc(S["layout.footer.kvkk"])))
    html_out = layout.page(
        layout.Page(
            lang=lang,
            title=esc(subject),
            preheader=esc(preheader),
            tone=tone,
            status=esc(status),
            heading=esc(heading),
            blocks=blocks,
            org=esc(org),
            logo_src=esc(brand.logo_src),
            footer_org=esc(footer_org),
            footer_why=esc(why),
            footer_links=links,
            footer_auto=esc(auto),
            article_label=esc(S["layout.article"]),
        )
    )

    # --- text (§5.10: heading, intro, details, button, note, --, footer) ---
    parts: list[str] = [body] if composed else [heading, body]
    if code:
        parts.append(f"{S['layout.code']}:\n{code}")
    if detail_rows:
        parts.append("\n".join(f"{a}: {b}" for a, b in detail_rows))
    if cta_url:
        parts.append(f"{cta_label}: {cta_url}")
    if after:
        parts.append(after)
    if note_text:
        parts.append(note_text)
    foot = [footer_org, why]
    if prefs_url:
        foot.append(f"{S['layout.footer.prefs']}: {prefs_url}")
    if kvkk_url:
        foot.append(f"{S['layout.footer.kvkk']}: {kvkk_url}")
    foot.append(auto)
    text_out = "\n\n".join(p for p in parts if p) + "\n\n--\n" + "\n".join(f for f in foot if f) + "\n"
    content = "\n\n".join(
        p for p in [body, *(parts[2:] if not composed else parts[1:])] if p and not p.startswith(f"{cta_label}: ")
    )
    return Rendered(
        subject, html_out, text_out, k.kind if k.kind != "generic" else kind, lang, preheader, cta_url, content.strip()
    )


def placeholders_in(template: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(template or "")))
