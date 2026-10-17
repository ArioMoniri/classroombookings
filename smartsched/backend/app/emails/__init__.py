"""Themed e-mails (wave 3b W3-MAIL): one renderer for every message the system sends.

    from app import emails
    subject, html, text = emails.render("approval_rejected", "tr", who="Gözde Ayrancıgil", what="A 201 ...",
                                        reason="Kapasite yetersiz", suggestions=["A 101"], cta_url="https://...")

:func:`render` is pure (no database); :func:`app.services.mail.render_for` adds the organisation's overrides and
brand. The catalogue is :data:`KINDS`; previews use :func:`sample_context`. Visual spec: docs/design/v3/emails.md.
"""

from app.emails.kinds import GENERIC, KINDS, KindSpec, spec
from app.emails.render import LOGO_CID, Brand, Rendered, clean, logo_png, placeholders_in, render, safe_url
from app.emails.samples import sample_context

__all__ = [
    "GENERIC",
    "KINDS",
    "LOGO_CID",
    "Brand",
    "KindSpec",
    "Rendered",
    "clean",
    "logo_png",
    "placeholders_in",
    "render",
    "safe_url",
    "sample_context",
    "spec",
]
