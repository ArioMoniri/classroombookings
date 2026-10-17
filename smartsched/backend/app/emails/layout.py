"""The themed HTML shell: table layout, inline styles, 600 px, dark-mode-safe colours, bulletproof button.

Rules (docs/design/brand.md, tokens.md; the e-mail spec docs/design/v3/emails.md):

* only ``<table>`` layout and inline ``style``; the one ``<style>`` block holds the dark-mode and phone media queries
  that clients without support simply ignore (light colours stay readable everywhere);
* brand blue ``#0A63D1`` for the button (white text 5.65:1), status colours of tokens.md §2.2 for the eyebrow chip
  and the callouts, each with a word, never colour alone;
* no ``text-transform: uppercase`` (Turkish dotted / dotless i), system font stack, 16 px body, 44 px button;
* every value reaching this module is already escaped by :mod:`app.emails.render`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

LIGHT = {"bg": "#EEF0F4", "card": "#FFFFFF", "t1": "#1D1D1F", "t2": "#48484A", "t3": "#6E6E73", "hair": "#E5E5EA"}
BRAND = "#0A63D1"
#: tone -> (fg, bg) light, (fg, bg) dark  (tokens.md §2.2 status colours; info = brand blue / navy)
TONES: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "info": (("#0A63D1", "#E8F1FC"), ("#A9D0FF", "#0B3F86")),
    "success": (("#15803D", "#DCFCE7"), ("#4ADE80", "#14532D")),
    "danger": (("#B91C1C", "#FEE2E2"), ("#FCA5A5", "#7F1D1D")),
    "warning": (("#B45309", "#FEF3C7"), ("#FCD34D", "#78350F")),
    "neutral": (("#48484A", "#F2F2F7"), ("#C7C7CC", "#2C2C31")),
}

_STYLE = """
:root{color-scheme:light dark;supported-color-schemes:light dark}
body{margin:0;padding:0;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}
table{border-collapse:collapse;mso-table-lspace:0;mso-table-rspace:0}
img{border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}
a{color:#0A63D1}
@media only screen and (max-width:620px){
.ss-container{width:100% !important}
.ss-pad{padding-left:20px !important;padding-right:20px !important}
.ss-h1{font-size:22px !important;line-height:28px !important}
.ss-btn a{display:block !important}
}
@media (prefers-color-scheme:dark){
.ss-bg{background-color:#0D0E12 !important}
.ss-card{background-color:#1B1C21 !important}
.ss-t1{color:#F5F5F7 !important}
.ss-t2{color:#C7C7CC !important}
.ss-t3{color:#AEAEB2 !important}
.ss-hair{border-color:#2C2C31 !important}
.ss-code{background-color:#222328 !important;color:#F5F5F7 !important}
%(dark_tones)s
}
[data-ogsc] .ss-t1{color:#F5F5F7 !important}
[data-ogsc] .ss-t2{color:#C7C7CC !important}
"""


def _dark_tones() -> str:
    out = []
    for tone, (_light, (fg, bg)) in TONES.items():
        out.append(f".ss-{tone}{{background-color:{bg} !important;color:{fg} !important}}")
        out.append(f".ss-{tone}-fg{{color:{fg} !important}}")
    return "\n".join(out)


@dataclass
class Page:
    """Everything the shell needs, escaped already."""

    lang: str
    title: str
    preheader: str
    tone: str
    eyebrow: str
    heading: str
    blocks: list[str]
    org: str
    logo_src: str
    logo_alt: str
    footer_lines: list[str] = field(default_factory=list)
    prefs_url: str | None = None
    prefs_label: str = ""


def tone_colours(tone: str) -> tuple[str, str]:
    return TONES.get(tone, TONES["info"])[0]


def paragraph(html_text: str) -> str:
    return (
        f'<p class="ss-t1" style="margin:0 0 16px 0;font-family:{FONT};font-size:16px;line-height:24px;'
        f'color:{LIGHT["t1"]};">{html_text}</p>'
    )


def note(html_text: str) -> str:
    return (
        f'<p class="ss-t2" style="margin:0 0 16px 0;font-family:{FONT};font-size:14px;line-height:20px;'
        f'color:{LIGHT["t2"]};">{html_text}</p>'
    )


def items(rows: list[str]) -> str:
    cells = "".join(
        f'<tr><td data-block="item" class="ss-t1 ss-hair" style="padding:10px 12px;font-family:{FONT};font-size:15px;'
        f'line-height:22px;color:{LIGHT["t1"]};border-top:1px solid {LIGHT["hair"]};">{r}</td></tr>'
        for r in rows
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="ss-hair" '
        f'style="margin:0 0 16px 0;border-bottom:1px solid {LIGHT["hair"]};">{cells}</table>'
    )


def callout(kind: str, tone: str, label: str, body: str) -> str:
    fg, bg = tone_colours(tone)
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px 0;">'
        f'<tr><td data-block="{kind}" class="ss-{tone}" style="padding:12px 14px;background-color:{bg};'
        f'border-left:4px solid {fg};border-radius:8px;font-family:{FONT};font-size:15px;line-height:22px;color:{LIGHT["t1"]};">'
        f'<strong class="ss-{tone}-fg" style="display:block;color:{fg};font-size:13px;line-height:18px;'
        f'margin-bottom:2px;">{label}</strong>{body}</td></tr></table>'
    )


def chips(rows: list[str]) -> str:
    return "".join(
        f'<span style="display:inline-block;margin:4px 6px 0 0;padding:4px 10px;border-radius:999px;'
        f'border:1px solid #A9D0FF;font-family:{FONT};font-size:14px;line-height:20px;">{r}</span>'
        for r in rows
    )


def code_box(label: str, code: str) -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px 0;">'
        f'<tr><td data-block="code" class="ss-code" align="center" style="padding:16px;background-color:#F2F2F7;'
        f'border-radius:10px;font-family:{FONT};color:{LIGHT["t2"]};font-size:13px;line-height:18px;">{label}<br>'
        f'<span style="display:inline-block;margin-top:6px;font-family:{MONO};font-size:22px;line-height:30px;'
        f'letter-spacing:1px;color:{LIGHT["t1"]};word-break:break-all;" class="ss-t1">{code}</span></td></tr></table>'
    )


def details(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<tr><td class="ss-t2 ss-hair" style="padding:8px 12px 8px 0;font-family:{FONT};font-size:14px;line-height:20px;'
        f'color:{LIGHT["t2"]};border-top:1px solid {LIGHT["hair"]};width:40%;vertical-align:top;">{k}</td>'
        f'<td class="ss-t1 ss-hair" style="padding:8px 0;font-family:{FONT};font-size:14px;line-height:20px;'
        f'color:{LIGHT["t1"]};border-top:1px solid {LIGHT["hair"]};vertical-align:top;">{v}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" data-block="details" '
        f'style="margin:0 0 16px 0;">{cells}</table>'
    )


def button(url: str, label: str, fallback_label: str) -> str:
    """Bulletproof: a VML roundrect for Outlook on Windows, a padded link for everyone else; 44 px high."""
    width = max(200, min(520, 11 * len(label) + 56))
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" class="ss-btn" style="margin:8px 0 16px 0;">'
        "<tr><td>"
        "<!--[if mso]>"
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" '
        f'href="{url}" style="height:44px;v-text-anchor:middle;width:{width}px;" arcsize="23%" stroke="f" '
        f'fillcolor="{BRAND}"><w:anchorlock/><center style="color:#FFFFFF;font-family:Arial,sans-serif;font-size:16px;'
        f'font-weight:bold;">{label}</center></v:roundrect>'
        "<![endif]-->"
        "<!--[if !mso]><!-- -->"
        f'<a href="{url}" target="_blank" style="display:inline-block;background-color:{BRAND};color:#FFFFFF;'
        f"font-family:{FONT};font-size:16px;font-weight:600;line-height:44px;min-height:44px;padding:0 24px;"
        f'border-radius:10px;text-decoration:none;text-align:center;mso-hide:all;">{label}</a>'
        "<!--<![endif]-->"
        "</td></tr></table>"
        f'<p class="ss-t3" style="margin:0 0 16px 0;font-family:{FONT};font-size:13px;line-height:18px;'
        f'color:{LIGHT["t3"]};word-break:break-all;">{fallback_label}<br>'
        f'<a href="{url}" style="color:{BRAND};text-decoration:underline;">{url}</a></p>'
    )


def page(p: Page) -> str:
    fg, bg = tone_colours(p.tone)
    style = _STYLE.replace("%(dark_tones)s", _dark_tones())
    pre_pad = "&#847;&zwnj;&nbsp;" * 40
    footer = "".join(
        f'<p class="ss-t3" style="margin:0 0 6px 0;font-family:{FONT};font-size:12px;line-height:18px;'
        f'color:{LIGHT["t3"]};">{line}</p>'
        for line in p.footer_lines
    )
    prefs = (
        f'<p style="margin:0 0 6px 0;font-family:{FONT};font-size:12px;line-height:18px;">'
        f'<a href="{p.prefs_url}" style="color:{BRAND};text-decoration:underline;">{p.prefs_label}</a></p>'
        if p.prefs_url
        else ""
    )
    eyebrow = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0;"><tr>'
        f'<td class="ss-{p.tone}" style="padding:4px 10px;border-radius:999px;background-color:{bg};color:{fg};'
        f'font-family:{FONT};font-size:13px;line-height:18px;font-weight:600;">{p.eyebrow}</td></tr></table>'
        if p.eyebrow
        else ""
    )
    return (
        "<!DOCTYPE html>"
        f'<html lang="{p.lang}" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge">'
        '<meta name="x-apple-disable-message-reformatting">'
        '<meta name="color-scheme" content="light dark">'
        '<meta name="supported-color-schemes" content="light dark">'
        '<meta name="format-detection" content="telephone=no,date=no,address=no,email=no">'
        f"<title>{p.title}</title>"
        "<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch>"
        "</o:OfficeDocumentSettings></xml></noscript><![endif]-->"
        f"<style>{style}</style>"
        "</head>"
        f'<body class="ss-bg" style="margin:0;padding:0;background-color:{LIGHT["bg"]};">'
        f'<div data-role="preheader" style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;'
        f'mso-hide:all;font-size:1px;line-height:1px;color:{LIGHT["bg"]};">{p.preheader}{pre_pad}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="ss-bg" '
        f'style="background-color:{LIGHT["bg"]};"><tr><td align="center" style="padding:24px 12px;">'
        '<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" class="ss-container" '
        'style="width:600px;max-width:600px;">'
        # header: the app tile (readable on light and dark) + the organisation's name
        '<tr><td class="ss-pad" style="padding:8px 32px 16px 32px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="vertical-align:middle;"><img src="{p.logo_src}" width="40" height="40" alt="{p.logo_alt}" '
        'style="display:block;width:40px;height:40px;border:0;border-radius:10px;"></td>'
        f'<td class="ss-t1" style="vertical-align:middle;padding-left:12px;font-family:{FONT};font-size:15px;'
        f'line-height:20px;font-weight:600;color:{LIGHT["t1"]};">{p.org}</td>'
        "</tr></table></td></tr>"
        # card
        f'<tr><td class="ss-card ss-pad" style="background-color:{LIGHT["card"]};border-radius:16px;'
        'padding:32px 32px 16px 32px;">'
        f"{eyebrow}"
        f'<h1 class="ss-t1 ss-h1" style="margin:0 0 16px 0;font-family:{FONT};font-size:24px;line-height:30px;'
        f'font-weight:700;color:{LIGHT["t1"]};">{p.heading}</h1>'
        f"{''.join(p.blocks)}"
        "</td></tr>"
        # footer
        f'<tr><td class="ss-pad" style="padding:20px 32px 8px 32px;">{footer}{prefs}</td></tr>'
        "</table>"
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table>"
        "</body></html>"
    )
