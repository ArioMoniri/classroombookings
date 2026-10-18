"""HB-23d: backend findings of the round-5 UX test and design review of the helper file router
(docs/testing/round5/hb23d-file-router-ux.md, hb23d-file-router-design.md): UX-06, UX-07/DS-07, UX-11, UX-12,
UX-14, UX-15/DS-13, UX-16, UX-20/DS-11, DS-12, UX-23/DS-21, UX-26. Synthetic files and the repository fixtures only.
"""

from __future__ import annotations

import json

import pytest
from app.ai.helper import files as hf
from app.core import kvkk_guard

from tests.api_fixtures import login
from tests.helper import test_file_router as router_tests
from tests.helper.test_file_router import (
    BAHAR_LIST,
    FIX,
    HF,
    UNI,
    C,
    card_of,
    mixed_headers_xlsx,
    person,
    random_headers_xlsx,
)

rc = router_tests.rc  # the router tests' API client fixture


def calendar_sync(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    from app.services import calendar_feeds

    async def enabled(session) -> bool:  # type: ignore[no-untyped-def]
        return on

    monkeypatch.setattr(calendar_feeds, "sync_enabled", enabled)


# UX-06: no "Takvimime ekle" when the institution has calendar sync off
async def test_academician_ics_with_calendar_sync_off_has_no_dead_end(rc, monkeypatch):
    calendar_sync(monkeypatch, False)
    admin = await login(rc)
    teacher = await person(rc, admin, "akad.ux@uni.edu.tr", role="TEACHER")
    out = await card_of(rc, teacher, HF / "seminar.ics")
    c = out["card"]
    assert c["state"] == "needs_planner" and c["kind"] == "calendar_ics"
    routes = ([c["primary"]] if c.get("primary") else []) + c["secondary"]
    assert not [r for r in routes if r["feature_id"] == "profile.calendar"]
    [w] = [w for w in c["warnings"] if w["code"] == "calendar_sync_off"]
    assert "Takvim aktarımı kurumunuzda kapalı" in w["message"]["tr"] and "kendiniz" in w["message"]["tr"]
    assert "calendar" in w["message"]["en"].lower()
    assert not [w for w in c["warnings"] if w["code"] == "ics_academic"]
    calendar_sync(monkeypatch, True)
    c = (await card_of(rc, teacher, HF / "seminar.ics"))["card"]
    assert c["primary"]["feature_id"] == "profile.calendar"


# UX-07 / DS-07: a broken PDF never shows exception text, and the Turkish text is Turkish
async def test_unreadable_pdf_shows_no_exception_text(rc):
    h = await login(rc)
    out = await card_of(rc, h, name="belge.pdf", data=b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\nbozuk\n")
    raw = json.dumps(out, ensure_ascii=False)
    for leak in ("Error", "PdfRead", "cannot read", "Traceback", "Exception"):
        assert leak not in raw, raw
    c = out["card"]
    assert c["type"] in ("refusal", "error", "file")
    tr = c["message"]["tr"] if "message" in c else c["title"]["tr"]
    assert tr and "PDF" in tr and "okuyamadım" in tr


# UX-11: the transposed grid's title reads naturally and says why the wizard
async def test_transposed_title_and_reason(rc):
    h = await login(rc)
    c = (await card_of(rc, h, UNI / "bahar_week1_transposed.xlsx"))["card"]
    assert "bir farklı düzende bir" not in c["title"]["tr"]
    assert c["title"]["tr"].count(" bir ") <= 1
    assert any(w["code"] == "layout_wizard" for w in c["warnings"])


# UX-12 / UX-26: the needs_planner title has no dangling "Sizin için:", the My classes line is soft
async def test_needs_planner_title_and_my_classes_line(rc):
    admin = await login(rc)
    teacher = await person(rc, admin, "akad.mc@uni.edu.tr", role="TEACHER")
    c = (await card_of(rc, teacher, BAHAR_LIST))["card"]
    assert not c["title"]["tr"].rstrip().endswith(":") and "Sizin için" not in c["title"]["tr"]
    assert not c["title"]["en"].rstrip().endswith(":")
    [w] = [w for w in c["warnings"] if w["code"] == "my_classes_known"]
    assert "zaten biliyor" not in w["message"]["tr"] and "Derslerim sayfasında" in w["message"]["tr"]
    assert "already knows" not in w["message"]["en"]


# UX-14: the term warning names the button and the term
async def test_term_mismatch_names_the_button_and_term(rc):
    h = await login(rc)
    c = (await card_of(rc, h, BAHAR_LIST))["card"]
    [w] = [w for w in c["warnings"] if w["code"] == "term_mismatch"]
    assert "İçe aktar düğmesi dosyayı Bahar 2026 dönemine aktarır." in w["message"]["tr"]
    assert "Düğme dosyanın dönemine" not in w["message"]["tr"]


# UX-15 / DS-13: the unknown card does not repeat its title
async def test_unknown_card_does_not_repeat_its_title(rc):
    h = await login(rc)
    c = (await card_of(rc, h, name="notlar.xlsx", data=random_headers_xlsx()))["card"]
    assert c["state"] == "unknown"
    assert all("tanıyamadım" not in line for line in c["evidence"]["tr"])
    assert all("couldn't recognise" not in line for line in c["evidence"]["en"])


# UX-16: a person's pick is not "most likely"
async def test_chooser_pick_is_the_persons_choice(rc):
    h = await login(rc)
    out = await card_of(rc, h, name="karisik.xlsx", data=mixed_headers_xlsx())
    token = out["card"]["args"]["upload_token"]
    r = await rc.post(f"{C}/route", json={"upload_token": token, "kind": "exam_list"}, headers=h)
    c = r.json()["card"]
    assert "olasılıkla" not in c["title"]["tr"] and "most likely" not in c["title"]["en"]
    assert c["title"]["tr"].startswith("Seçiminiz") and c["certainty"] == "sure"


# UX-20 / DS-11: room-master evidence in Turkish words, not raw keys
async def test_room_master_evidence_is_turkish(rc):
    h = await login(rc)
    c = (await card_of(rc, h, FIX / "room_master.csv"))["card"]
    line = c["evidence"]["tr"][0]
    assert "exam_capacity" not in line and "capacity" not in line and "derslik kodu" in line
    assert "exam capacity" in c["evidence"]["en"][0]


# DS-12: primary labels fit the 48-character budget
def test_import_labels_fit_48_characters():
    long_term = hf.TermGuess(1, ("Güz 2026-2027 Yaz Okulu", "Fall 2026-2027 Summer School"), "file_name", False)
    for kind in ("planning_list", "exam_list", "weekly_grid"):
        for term in (long_term, hf.TermGuess(2, ("Güz 2026-2027", "Fall 2026-2027"), "file_name", False), None):
            r = hf._import_route(kind, term, 2026)  # noqa: SLF001
            assert len(r.label[0]) <= 48 and len(r.label[1]) <= 48, r.label


# UX-23 / DS-21: no environment path in the KVKK guard's words
def test_kvkk_guard_text_has_no_env_path(monkeypatch):
    monkeypatch.setattr(kvkk_guard, "active", lambda: True)
    monkeypatch.setattr(kvkk_guard, "is_seed_workbook", lambda data: True)
    with pytest.raises(kvkk_guard.KvkkRefused) as exc:
        kvkk_guard.check(b"x", "a.xlsx")
    assert "$" not in exc.value.message_tr and "REC_WORKDIR" not in exc.value.message_en
    assert "maskelenmiş kopyayı kullanın" in exc.value.message_tr
    monkeypatch.setattr(kvkk_guard, "is_seed_workbook", lambda data: False)
    monkeypatch.setattr(kvkk_guard, "unmasked_hits", lambda data, name: 2)
    with pytest.raises(kvkk_guard.KvkkRefused) as exc:
        kvkk_guard.check(b"x", "a.xlsx")
    assert "$" not in exc.value.message_tr and "REC_WORKDIR" not in exc.value.message_en
    assert "maskelenmiş kopyayı kullanın" in exc.value.message_tr
