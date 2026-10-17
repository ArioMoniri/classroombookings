"""W3-MAIL: one renderer for every e-mail (``app.emails.render(kind, locale, **ctx) -> (subject, html, text)``).

Every kind x locale is rendered with its sample data (real Bahar 2026 rooms and people from the fixtures: A 201
is the TIP room of the weekly grid, BME 419 the 102-seat cohort of docs/DATA_ANALYSIS.md) and checked for:
well-formed table-based HTML, inline styles only (no <style> beyond the dark-mode media block), 600 px, a preheader,
a plain-text part, no unrendered ``{placeholders}``, every user value escaped, Turkish casing and NBSP cleaned.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from app import emails
from app.emails import KINDS, Rendered, render, sample_context

LOCALES = ("tr", "en")
VOID = {"br", "img", "meta", "hr", "input", "link", "col", "area", "base", "source", "wbr"}


class _Checker(HTMLParser):
    """Tags are balanced (void elements aside); counts what the assertions need."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.tags: dict[str, int] = {}
        self.text: list[str] = []
        self.links: list[str] = []
        self.imgs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "a":
            self.links.append(dict(attrs).get("href") or "")
        if tag == "img":
            self.imgs.append(dict(attrs))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "img":
            self.imgs.append(dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _check(html: str) -> _Checker:
    # Outlook conditional comments carry VML; the parser treats them as comments, which is what the clients do
    c = _Checker()
    c.feed(html)
    c.close()
    assert not c.errors, c.errors
    assert not c.stack, f"unclosed: {c.stack}"
    return c


PLACEHOLDER = re.compile(r"\{[a-z_][a-z0-9_]*\}")


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_kind_renders_valid_themed_html_and_text(kind: str, locale: str) -> None:
    out = render(kind, locale, **sample_context(kind, locale))
    assert isinstance(out, Rendered)
    subject, html, text = out  # the tuple contract
    assert subject and "\n" not in subject and len(subject) <= 255
    assert html.startswith("<!DOCTYPE html>") and f'lang="{locale}"' in html
    c = _check(html)
    assert c.tags.get("table", 0) >= 3  # table layout, not divs
    assert 'width="600"' in html and "max-width:600px" in html.replace(" ", "")
    assert 'name="color-scheme"' in html and "prefers-color-scheme" in html  # dark-mode safe
    assert 'data-role="preheader"' in html
    # EM-19: the tile is decorative (alt="") because the live text "SmartSched" follows; role="article" + label
    assert any(img.get("src", "").startswith(("cid:", "https://")) and img.get("alt") == "" for img in c.imgs)
    assert ">SmartSched</td>" in html and 'role="article"' in html and "aria-label=" in html
    for blob in (subject, html, text):  # EM-01
        assert not PLACEHOLDER.search(blob), (kind, locale, PLACEHOLDER.findall(blob))
        assert "\xa0" not in blob.replace("&nbsp;", "")
        assert "replaced_by_series:" not in blob and "PENDING" not in blob
    assert len(html.encode()) < 90_000  # EM-02 (Gmail clips at 102 KB)
    assert c.tags.get("h1") == 1 and html.count('class="em-btn-a"') <= 1  # EM-03
    assert out.preheader and out.preheader != subject and len(out.preheader) <= 140  # EM-05
    assert text.strip() and "<" not in text.replace("<https", "").replace("<http", "")
    # the button (if any) works in Outlook too: a VML roundrect inside a conditional comment (EM-09)
    if out.cta_url:
        assert "v:roundrect" in html and out.cta_url in text and html.count(f'href="{out.cta_url}"') >= 2
    # EM-14: security and legal kinds cannot be switched off and carry no preferences link
    spec = KINDS[kind]
    if spec.footer in ("security", "legal"):
        assert "profile?tab=notifications" not in html and ("kapatılamaz" in text or "cannot be turned off" in text)


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_turkish_and_english_differ_and_turkish_is_turkish(kind: str) -> None:
    tr = render(kind, "tr", **sample_context(kind, "tr"))
    en = render(kind, "en", **sample_context(kind, "en"))
    assert tr.subject != en.subject
    assert tr.html != en.html
    # the footer explains why the person got the message, in the reader's language (§5.9)
    assert "Örnek Üniversitesi · SmartSched" in tr.text
    assert any(w in tr.text for w in ("Bu e-postayı", "kapatılamaz"))
    assert any(w in en.text for w in ("You received this", "cannot be turned off"))


def test_user_values_are_escaped_everywhere() -> None:
    evil = '<script>alert("x")</script> & <b>"Ayşe"</b>'
    out = render(
        "approval_rejected",
        "tr",
        who=evil,
        what="A 201, 18.02.2026 P3 10:10-11:00",
        reason=evil,
        suggestions=["A 101", evil],
        cta_url="https://plan.uni.edu.tr/bookings/mine?request=7&x=<y>",
    )
    assert "<script>" not in out.html and "<b>" not in out.html
    assert "&lt;script&gt;" in out.html and "&amp;" in out.html
    assert 'href="https://plan.uni.edu.tr/bookings/mine?request=7&amp;x=%3Cy%3E"' in out.html
    assert evil in out.text  # plain text carries the words as typed


def test_unsafe_link_schemes_are_dropped() -> None:
    out = render("booking_created", "tr", **{**sample_context("booking_created", "tr"), "cta_url": "javascript:alert(1)"})
    assert "javascript:" not in out.html and out.cta_url is None


def test_admin_override_wins_and_is_escaped_with_placeholders_filled() -> None:
    ctx = sample_context("approval_approved", "tr")
    out = render(
        "approval_approved",
        "tr",
        strings={"approval_approved.subject": "Onay: {what} <tamam>", "approval_approved.intro": "Merhaba {name}!"},
        **ctx,
    )
    assert out.subject.startswith("Onay: A 201") and "<tamam>" in out.subject  # subject is plain text
    assert "Merhaba Ayşe Yılmaz!" in out.text
    assert "&lt;tamam&gt;" in out.html
    # a placeholder the kind does not know stays readable instead of failing the e-mail
    odd = render("approval_approved", "tr", strings={"approval_approved.intro": "Selam {bilinmeyen}"}, **ctx)
    assert "Selam {bilinmeyen}" in odd.text


def test_precomposed_body_keeps_the_plain_text_and_themes_lists_and_reasons() -> None:
    """The wired send paths (approvals, bookings, KVKK, AI alerts) keep their copy: the text part starts with the
    body exactly as the bell shows it; the HTML turns '- ' lines into rows and 'Gerekçe:' into a callout."""
    body = (
        "Gözde Ayrancıgil talebinizi reddetti: A 201, 18.02.2026 P3 10:10-11:00.\n"
        "Gerekçe: Kapasite yetersiz: 102 kişilik BME 419 için küçük\n"
        "Önerilen derslikler (otomatik): A 101, B 207."
    )
    out = render(
        "approval_rejected",
        "tr",
        subject="Oda talebiniz reddedildi: A 201, 18.02.2026 P3 10:10-11:00",
        body=body,
        cta_url="https://plan.uni.edu.tr/bookings/mine?request=7",
    )
    assert out.text.startswith(body)
    assert 'data-block="reason"' in out.html and "Kapasite yetersiz" in out.html
    assert 'data-block="suggestions"' in out.html and "B 207" in out.html
    items = render(
        "booking_created",
        "en",
        subject="A booking was made for you",
        body="Fatih Bey made 2 booking(s) for you:\n- A 101, Tuesday, 17 February 2026 P1 08:30-09:10\n- A 102, x\n",
    )
    assert items.html.count('data-block="item"') == 2


def test_turkish_text_is_normalised() -> None:
    out = render("booking_cancelled", "tr", subject="Rezervasyonunuz\xa0iptal edildi", body="İptal\xa0edildi:\n- A\xa0101")
    assert "\xa0" not in out.subject and "\xa0" not in out.text
    assert out.subject == "Rezervasyonunuz iptal edildi"


def test_password_reset_text_keeps_the_code_on_its_own_line() -> None:
    out = render("password_reset", "tr", code="AbCdEfGh12345678XyZ", valid_hours=24, name="Ayşe Yılmaz")
    lines = out.text.splitlines()
    assert "AbCdEfGh12345678XyZ" in lines
    assert next(line for line in lines if line and " " not in line) == "AbCdEfGh12345678XyZ"
    assert 'data-block="code"' in out.html and "24" in out.text


def test_unknown_kind_is_a_generic_themed_message() -> None:
    out = render("something_new", "en", subject="Hello", body="Plain words")
    assert out.subject == "Hello" and out.text.startswith("Plain words")
    _check(out.html)


def test_kind_catalogue_covers_every_system_message() -> None:
    expected = {
        "password_reset",
        "invitation",
        "account_created",
        "new_device_sign_in",
        "booking_created",
        "room_owner_booking",
        "approval_submitted",
        "approval_requested",
        "approval_approved",
        "approval_rejected",
        "approval_withdrawn",
        "approval_expired",
        "booking_cancelled",
        "booking_reminder",
        "series_created",
        "series_changed",
        "calendar_consent",
        "kvkk_request",
        "ai_usage_alert",
        "ops_alert",
        "timetable_published",
        "booking_conflict_resolved",
        "preference_accepted",
        "preference_rejected",
        "smtp_test",
    }
    assert expected <= set(KINDS)
    for kind, spec in KINDS.items():
        assert spec.label_tr and spec.label_en, kind
        assert spec.tone in {"info", "success", "danger", "warning", "neutral"}, kind


def test_invitation_names_the_identity_provider() -> None:
    ms = render("invitation", "tr", **{**sample_context("invitation", "tr"), "provider": "microsoft"})
    local = render("invitation", "tr", **{**sample_context("invitation", "tr"), "provider": "local"})
    assert "Microsoft" in ms.text and "Microsoft" not in local.text


def test_approver_mail_has_no_decision_links() -> None:
    """EM-15: decisions are made in the app (link scanners pre-fetch GET links)."""
    for locale in LOCALES:
        out = render("approval_requested", locale, **sample_context("approval_requested", locale))
        assert "/decide" not in out.html and "approve=" not in out.html and "reject" not in out.html.lower()


def test_variants_pick_their_sentences() -> None:
    ms = render("invitation", "en", **sample_context("invitation", "en"))
    assert "Sign in with Microsoft" in ms.text and ms.preheader.startswith("Join with your Microsoft")
    oidc = render("invitation", "tr", **{**sample_context("invitation", "tr"), "provider": "oidc"})
    assert "Kampüs girişi ile giriş yap" in oidc.text and "Kampüs girişi (kurumsal giriş)" not in oidc.subject
    resolved = render("ops_alert", "tr", **{**sample_context("ops_alert", "tr"), "state": "resolved", "duration": "12 dk"})
    assert resolved.subject.startswith("Çözüldü:") and 'data-block="status"' in resolved.html and "Çözüldü" in resolved.html
    assert "#63E08B" in resolved.html  # success tone in dark mode
    held = render("approval_submitted", "tr", **{**sample_context("approval_submitted", "tr"), "hold": "held", "held_until": "19 Şubat 2026 12:00"})
    assert "tutulur" in held.text
    plain = render("approval_submitted", "tr", **sample_context("approval_submitted", "tr"))
    assert "tutulur" not in plain.text and "onaylanan talep dersliği alır" in plain.text
    undo = render("booking_cancelled", "en", **{**sample_context("booking_cancelled", "en"), "reason": "undo_of:41"})
    assert "Undo (#41)" in undo.text and undo.preheader == "An action was undone."
    words = render("booking_cancelled", "tr", **{**sample_context("booking_cancelled", "tr"), "reason": "Bölüm toplantısı"})
    assert "Gerekçe: Bölüm toplantısı" in words.text and words.preheader == "Fatih Demir iptal etti."


def test_composed_mode_never_shows_an_unfillable_shipped_part() -> None:
    out = render("booking_created", "tr", subject="Sizin adınıza rezervasyon yapıldı", body="Fatih Bey sizin adınıza 1 rezervasyon yaptı:\n- A 101")
    assert not PLACEHOLDER.search(out.html + out.text) and "<h1" in out.html
    kv = render("kvkk_request", "tr", subject="Kişisel veri (silme) talebiniz reddedildi", body="Yasal saklama süresi dolmadı.")
    assert "Kişisel veri (silme) talebiniz reddedildi</h1>" in kv.html  # variant-dependent heading: the subject


def test_logo_is_shipped_for_cid() -> None:
    data = emails.logo_png()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) < 20_000
