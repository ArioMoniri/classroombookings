"""The themed HTML shell (docs/design/v3/emails.md §3-§5, §10): table layout, inline styles, 600 px card,
dark-mode swaps by class, bulletproof 48 px button, accessible details table.

* only ``<table>`` layout and inline ``style``; the one ``<style>`` block holds the dark-mode (``prefers-color-scheme``,
  Outlook.com ``[data-ogsc]`` / ``[data-ogsb]``) and phone (``max-width:480px``) rules that clients without support
  ignore (the light design survives Gmail's forced inversion: no text in images, the tile has its own opaque blue);
* colours of §3.1 (opaque only), status always with a word (pill, bold callout label);
* no ``text-transform: uppercase`` (Turkish dotted / dotless i), system font stacks, 16 px body;
* every value reaching this module is already escaped by :mod:`app.emails.render`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

#: §3.1 tokens: name -> (light, dark)
T: dict[str, tuple[str, str]] = {
    "canvas": ("#EEF0F4", "#0D0E12"),
    "card": ("#FFFFFF", "#1B1C21"),
    "t1": ("#1D1D1F", "#F5F5F7"),
    "t2": ("#4B4B51", "#B6B6BD"),
    "t3": ("#5F5F66", "#A9A9B1"),
    "line": ("#D9DCE3", "#33343B"),
    "button": ("#0A63D1", "#4DA0FF"),
    "button_text": ("#FFFFFF", "#06101F"),
    "link": ("#0957BB", "#6CB0FF"),
    "detail": ("#F5F7FA", "#24252B"),
}
#: tone -> ((fg, bg) light, (fg, bg) dark)
TONES: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "success": (("#0F6430", "#E6F5EA"), ("#63E08B", "#11291A")),
    "danger": (("#A3211A", "#FCEBEA"), ("#FF9D95", "#351614")),
    "warning": (("#7C4800", "#FFF2D9"), ("#FFCC66", "#33270C")),
    "info": (("#0957BB", "#E8F1FC"), ("#6CB0FF", "#122238")),
    "neutral": (("#4B4B51", "#F5F7FA"), ("#B6B6BD", "#24252B")),
}
L = {k: v[0] for k, v in T.items()}


def _style() -> str:
    dark = {k: v[1] for k, v in T.items()}
    swaps = [
        f".em-canvas{{background-color:{dark['canvas']} !important}}",
        f".em-card{{background-color:{dark['card']} !important}}",
        f".em-t1{{color:{dark['t1']} !important}}",
        f".em-t2{{color:{dark['t2']} !important}}",
        f".em-t3{{color:{dark['t3']} !important}}",
        f".em-line{{border-color:{dark['line']} !important}}",
        f".em-detail{{background-color:{dark['detail']} !important}}",
        f".em-link{{color:{dark['link']} !important}}",
        f".em-btn{{background-color:{dark['button']} !important}}",
        f".em-btn-a{{color:{dark['button_text']} !important;border-color:{dark['button']} !important}}",
    ]
    for tone, (_light, (fg, bg)) in TONES.items():
        swaps.append(f".em-{tone}{{background-color:{bg} !important;color:{fg} !important}}")
        swaps.append(f".em-{tone}-fg{{color:{fg} !important}}")
        swaps.append(f".em-{tone}-bar{{border-left-color:{fg} !important}}")
    ogsc = [s for s in swaps if s.startswith((".em-t", ".em-link", ".em-btn-a")) or "-fg{" in s]  # text colours
    ogsb = [s for s in swaps if "background-color" in s]  # backgrounds
    return (
        ":root{color-scheme:light dark;supported-color-schemes:light dark}"
        "body{margin:0;padding:0;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}"
        "table{border-collapse:collapse;mso-table-lspace:0;mso-table-rspace:0}"
        "img{border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}"
        "@media only screen and (max-width:480px){"
        ".em-outer{padding:0 !important}"
        ".em-wrap{width:100% !important}"
        ".em-card{border-radius:0 !important}"
        ".em-pad{padding-left:20px !important;padding-right:20px !important}"
        ".em-h1{font-size:22px !important;line-height:30px !important}"
        ".em-btn-wrap,.em-btn-a{width:100% !important;display:block !important}"
        ".em-row th,.em-row td{display:block !important;width:auto !important;padding-left:16px !important}"
        ".em-row th{padding-bottom:0 !important;font-size:13px !important;line-height:18px !important}"
        "}"
        "@media (prefers-color-scheme:dark){"
        + "".join(swaps)
        + "}"
        + "".join(f"[data-ogsc] {s}" for s in ogsc)
        + "".join(f"[data-ogsb] {s}" for s in ogsb)
    )


@dataclass
class Page:
    """Everything the shell needs, escaped already."""

    lang: str
    title: str
    preheader: str
    tone: str
    status: str
    heading: str
    blocks: list[str]
    org: str
    logo_src: str
    footer_org: str
    footer_why: str
    footer_links: list[tuple[str, str]] = field(default_factory=list)  # (url, label)
    footer_auto: str = ""
    article_label: str = "e-posta"


def tone_colours(tone: str) -> tuple[str, str]:
    return TONES.get(tone, TONES["info"])[0]


def paragraph(html_text: str) -> str:
    return (
        f'<p class="em-t1" style="margin:0 0 16px 0;font-family:{FONT};font-size:16px;line-height:24px;'
        f'color:{L["t1"]};">{html_text}</p>'
    )


def note(html_text: str) -> str:
    return (
        f'<p class="em-t2" style="margin:0 0 16px 0;font-family:{FONT};font-size:14px;line-height:21px;'
        f'color:{L["t2"]};">{html_text}</p>'
    )


def items(rows: list[str]) -> str:
    cells = "".join(
        f'<tr><td data-block="item" class="em-t1 em-line" style="padding:10px 16px;font-family:{FONT};font-size:15px;'
        f'line-height:22px;color:{L["t1"]};border-top:1px solid {L["line"]};">{r}</td></tr>'
        for r in rows
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="em-detail em-line" '
        f'style="margin:0 0 24px 0;background-color:{L["detail"]};border:1px solid {L["line"]};border-radius:12px;'
        f'border-collapse:separate;">{cells}</table>'
    )


def callout(kind: str, tone: str, label: str, body: str) -> str:
    fg, bg = tone_colours(tone)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:0 0 24px 0;">'
        f'<tr><td data-block="{kind}" class="em-{tone} em-{tone}-bar" style="padding:14px 16px;background-color:{bg};'
        f"border-left:4px solid {fg};border-radius:8px;font-family:{FONT};font-size:15px;line-height:22px;"
        f'color:{L["t1"]};">'
        f'<strong class="em-{tone}-fg" style="display:block;color:{fg};font-size:15px;line-height:22px;'
        f'font-weight:600;">{label}</strong><span class="em-t1" style="color:{L["t1"]};'
        f'">{body}</span></td></tr></table>'
    )


def chips(rows: list[str]) -> str:
    return "".join(
        f'<span class="em-t1" style="display:inline-block;margin:6px 6px 0 0;padding:4px 10px;border-radius:999px;'
        f'border:1px solid #A9D0FF;font-family:{FONT};font-size:14px;line-height:20px;color:{L["t1"]};">{r}</span>'
        for r in rows
    )


def code_box(label: str, code: str, spelled: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:0 0 24px 0;">'
        '<tr><td data-block="code" class="em-detail em-t3" align="center" style="padding:16px;'
        f"background-color:{L['detail']};"
        f'border-radius:12px;font-family:{FONT};color:{L["t3"]};font-size:13px;line-height:18px;">{label}<br>'
        f'<span class="em-t1" aria-label="{spelled}" style="display:inline-block;margin-top:6px;font-family:{MONO};'
        f'font-size:24px;line-height:32px;font-weight:600;letter-spacing:2px;color:{L["t1"]};word-break:break-all;">'
        f"{code}</span></td></tr></table>"
    )


def details(rows: list[tuple[str, str]], tone: str | None = None) -> str:
    """Label/value rows read by screen readers as "Derslik, A 201" (a data table with ``<th scope="row">``)."""
    bar = f"border-left:4px solid {tone_colours(tone)[0]};" if tone and tone != "neutral" else ""
    bar_cls = f" em-{tone}-bar" if bar else ""
    cells = "".join(
        f'<tr class="em-row"><th scope="row" class="em-t3" style="padding:7px 12px 7px 16px;font-family:{FONT};'
        f"font-size:14px;line-height:24px;font-weight:500;color:{L['t3']};text-align:left;vertical-align:top;"
        f'width:154px;">{k}</th><td class="em-t1" style="padding:7px 16px 7px 0;font-family:{FONT};font-size:16px;'
        f'line-height:24px;font-weight:600;color:{L["t1"]};vertical-align:top;">{v}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" data-block="details" '
        f'class="em-detail em-line{bar_cls}" style="margin:0 0 24px 0;background-color:{L["detail"]};'
        f'border:1px solid {L["line"]};{bar}border-radius:12px;border-collapse:separate;padding:7px 0;">{cells}</table>'
    )


def button(url: str, label: str, plain_label_len: int) -> str:
    """Bulletproof (§5.7): the colour on the ``<td>`` (Outlook web keeps it), VML roundrect for classic Outlook."""
    width = max(240, int(9.5 * plain_label_len + 56))
    b, bt = L["button"], L["button_text"]
    return (
        '<table role="presentation" border="0" cellspacing="0" cellpadding="0" class="em-btn-wrap" style="margin:0 0'
        ' 24px 0;">'
        f'<tr><td align="center" bgcolor="{b}" class="em-btn" style="border-radius:12px;background-color:{b};">'
        "<!--[if mso]>"
        f'<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" '
        f'href="{url}" style="height:48px;v-text-anchor:middle;width:{width}px;" arcsize="25%" stroke="f" '
        f'fillcolor="{b}"><w:anchorlock/><center style="color:{bt};font-family:\'Segoe UI\',Arial,sans-serif;'
        f'font-size:16px;font-weight:600;">{label}</center></v:roundrect>'
        "<![endif]-->"
        "<!--[if !mso]><!-->"
        f'<a href="{url}" class="em-btn-a" target="_blank" style="display:inline-block;padding:14px 28px;'
        "min-width:184px;"
        f"border:1px solid {b};border-radius:12px;font-family:{FONT};font-size:16px;line-height:20px;font-weight:600;"
        f'color:{bt};text-decoration:none;text-align:center;mso-hide:all;">{label}</a>'
        "<!--<![endif]-->"
        "</td></tr></table>"
    )


def fallback(label: str, url: str) -> str:
    return (
        f'<p class="em-t2" style="margin:0 0 16px 0;font-family:{FONT};font-size:14px;line-height:21px;color:{L["t2"]};'
        f'word-break:break-all;">{label}<br><a href="{url}" class="em-link" style="color:{L["link"]};'
        f'text-decoration:underline;">{url}</a></p>'
    )


def page(p: Page) -> str:
    fg, bg = tone_colours(p.tone)
    pre_pad = "&#8199;&#65279;&#847;" * 90
    pill = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0;"><tr>'
        f'<td data-block="status" class="em-{p.tone}" style="padding:3px 10px;border-radius:13px;background-color:{bg};'
        f'color:{fg};font-family:{FONT};font-size:13px;line-height:18px;font-weight:600;">{p.status}</td></tr></table>'
        if p.status
        else ""
    )
    links = " · ".join(
        f'<a href="{u}" class="em-link" style="color:{L["link"]};text-decoration:underline;">{lbl}</a>'
        for u, lbl in p.footer_links
    )
    small = f"margin:0 0 6px 0;font-family:{FONT};font-size:13px;line-height:20px;"
    footer = (
        f'<p class="em-t2" style="{small}font-weight:600;color:{L["t2"]};">{p.footer_org}</p>'
        f'<p class="em-t3" style="{small}color:{L["t3"]};">{p.footer_why}</p>'
        + (f'<p class="em-t3" style="{small}color:{L["t3"]};">{links}</p>' if links else "")
        + (f'<p class="em-t3" style="{small}color:{L["t3"]};">{p.footer_auto}</p>' if p.footer_auto else "")
    )
    return (
        "<!DOCTYPE html>"
        f'<html lang="{p.lang}" dir="ltr" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" '
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
        f"<style>{_style()}</style>"
        "</head>"
        f'<body class="em-canvas" style="margin:0;padding:0;background-color:{L["canvas"]};">'
        f'<div data-role="preheader" style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;'
        f'mso-hide:all;font-size:1px;line-height:1px;color:{L["canvas"]};">{p.preheader}{pre_pad}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="em-canvas" '
        f'style="background-color:{L["canvas"]};"><tr><td align="center" class="em-outer" style="padding:24px 12px;">'
        '<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0"'
        ' border="0"><tr><td><![endif]-->'
        f'<table role="article" aria-roledescription="{p.article_label}" aria-label="{p.title}" width="600" '
        'cellpadding="0" cellspacing="0" border="0" class="em-wrap" style="width:100%;max-width:600px;">'
        f'<tr><td class="em-card em-pad" style="background-color:{L["card"]};border-radius:16px;padding:0 40px 32px'
        ' 40px;">'
        # header: tile + "SmartSched" (live text) left, the organisation right; 1 px line under
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="em-line" '
        f'style="border-bottom:1px solid {L["line"]};margin:0 0 24px 0;"><tr>'
        f'<td style="padding:20px 0;vertical-align:middle;width:38px;"><img src="{p.logo_src}" width="28" height="28" '
        'alt="" style="display:block;width:28px;height:28px;border:0;border-radius:7px;"></td>'
        f'<td class="em-t1" style="padding:20px 0;vertical-align:middle;font-family:{FONT};font-size:16px;'
        "line-height:20px;"
        f'font-weight:600;color:{L["t1"]};">SmartSched</td>'
        f'<td class="em-t3" align="right" style="padding:20px 0;vertical-align:middle;font-family:{FONT};'
        "font-size:13px;"
        f'line-height:18px;font-weight:500;color:{L["t3"]};">{p.org}</td>'
        "</tr></table>"
        f"{pill}"
        f'<h1 class="em-t1 em-h1" style="margin:0 0 8px 0;font-family:{FONT};font-size:24px;line-height:32px;'
        f'font-weight:600;color:{L["t1"]};">{p.heading}</h1>'
        f'<div style="height:8px;line-height:8px;font-size:8px;">&#8202;</div>'
        f"{''.join(p.blocks)}"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="em-line" '
        f'style="border-top:1px solid {L["line"]};margin:8px 0 0 0;"><tr><td style="padding-top:16px;'
        f'">{footer}</td></tr></table>'
        "</td></tr></table>"
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table>"
        "</body></html>"
    )
