"""Flow loop round 2, lane F (docs/ROADMAP.md "Flow loop tickets — round 2", ``rounds/round-2-tickets.json``):
admin screens, the audit undo and the server strings that still reached the Turkish admin UI.

* T-R2-31 (R2-S-09, R2-M-11): the undo of a booking create cancels the booking with a *coded* reason
  (``undo_of:<audit id>``) that the UI renders in its language ("Geri alma: #164"); no English "undo of" sentence
  is stored on the booking, the audit row or the event payload.
* T-R2-33 (R2-M-18, R1-M-17): a duplicate feature name is a coded 409 ``name_taken`` with ``message_tr``; a room
  photo that is no image is refused with a coded Turkish problem whose text carries no English tail; a feature
  value refusal through ``PUT /room-admin/rooms/{id}/fields`` carries the code and ``message_tr`` too.
* T-R2-32 (R2-M-20, F-05 S00): re-picking the instructor a login is already linked to writes no
  ``user.instructor_link`` audit row.
"""

from __future__ import annotations

import io
from datetime import date

from app.core import db as dbmod
from app.models import AuditEvent
from PIL import Image
from sqlalchemy import func, select

from tests.crbs_env import env  # noqa: F401
from tests.test_sso_admin import sso  # noqa: F401

MON = date(2026, 2, 16)
AUDIT = "/api/v1/audit"
FEAT = "/api/v1/room-admin/features"


async def _last(env, headers=None, **params):  # type: ignore[no-untyped-def]  # noqa: F811
    r = await env.client.get(AUDIT, params={"limit": 1, **params}, headers=headers or env.admin)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    return items[0] if items else None


# --------------------------------------------------------------------------------------------- T-R2-31


async def test_undo_of_a_create_stores_a_coded_reason_not_an_english_sentence(env):  # noqa: F811
    _, ayse = await env.user("ayse.undo@uni.edu.tr")
    c = env.client
    bid = (await env.book(ayse, "A101", MON, "P1")).json()["id"]
    created = await _last(env, ayse, entity_type="booking", entity_id=str(bid))
    r = await c.post(f"{AUDIT}/{created['id']}/undo", headers=ayse)
    assert r.status_code == 200, r.text
    booking = (await c.get(f"/api/v1/bookings/{bid}", headers=ayse)).json()
    assert booking["status"] == "CANCELLED"
    # the booking card shows the reason: a code the UI renders as "Geri alma: #<id>", never "undo of #<id>"
    assert booking["cancel_reason"] == f"undo_of:{created['id']}"
    undo_row = await _last(env, ayse, action="booking.cancel")
    assert undo_row["undo_of"] == created["id"]
    assert undo_row["reason"] == f"undo_of:{created['id']}"
    assert "undo of" not in (undo_row["reason"] or "")
    async with dbmod.get_session_factory()() as s:
        ev = await s.get(AuditEvent, undo_row["id"])
        assert ev is not None and "undo of" not in str(ev.reason)


async def test_undo_of_a_cancel_restores_without_a_reason_sentence(env):  # noqa: F811
    _, ayse = await env.user("ayse.restore@uni.edu.tr")
    c = env.client
    bid = (await env.book(ayse, "A106", MON, "P1")).json()["id"]
    assert (
        await c.post(f"/api/v1/bookings/{bid}/cancel", json={"reason": "yanlışlık"}, headers=ayse)
    ).status_code == 200
    cancel = await _last(env, ayse, action="booking.cancel")
    r = await c.post(f"{AUDIT}/{cancel['id']}/undo", headers=ayse)
    assert r.status_code == 200 and r.json()["action"] == "booking.restore", r.text
    booking = (await c.get(f"/api/v1/bookings/{bid}", headers=ayse)).json()
    assert booking["status"] == "BOOKED" and booking["cancel_reason"] is None
    restore = await _last(env, ayse, action="booking.restore")
    assert restore["undo_of"] == cancel["id"] and restore["reason"] == f"undo_of:{cancel['id']}"


# --------------------------------------------------------------------------------------------- T-R2-33


async def test_duplicate_feature_name_is_a_coded_turkish_409(env):  # noqa: F811
    c = env.client
    body = {"name": "Projeksiyon", "type": "BOOLEAN"}
    assert (await c.post(FEAT, json=body, headers=env.admin)).status_code == 201
    r = await c.post(FEAT, json={**body, "name": "projeksiyon"}, headers=env.admin)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "name_taken"
    assert detail["message_tr"] == "Bu adda bir özellik zaten var: projeksiyon"
    assert "exists" in detail["message"]  # English stays for English readers
    # the same on a rename
    other = (await c.post(FEAT, json={"name": "Akıllı tahta", "type": "BOOLEAN"}, headers=env.admin)).json()
    r = await c.put(f"{FEAT}/{other['id']}", json={"name": "PROJEKSİYON", "type": "BOOLEAN"}, headers=env.admin)
    assert r.status_code == 409 and r.json()["detail"]["message_tr"].startswith("Bu adda bir özellik zaten var")
    # a validation refusal is coded with Turkish too
    r = await c.post(FEAT, json={"name": "Koltuk türü", "type": "SELECT", "options": []}, headers=env.admin)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "options"
    assert r.json()["detail"]["message_tr"] == "Bu tür için seçenekler gerekir."


async def test_feature_value_refusal_through_room_fields_carries_message_tr(env):  # noqa: F811
    c = env.client
    f = (await c.post(FEAT, json={"name": "PC sayısı", "type": "NUMBER"}, headers=env.admin)).json()
    r = await c.put(
        f"/api/v1/room-admin/rooms/{env.rooms['A101']}/fields", json={str(f["id"]): "çok"}, headers=env.admin
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_values"
    assert detail["message_tr"] == "PC sayısı: 'çok' bir sayı değil"
    assert detail["errors_tr"] == ["PC sayısı: 'çok' bir sayı değil"] and "is not a number" in detail["message"]


async def test_room_photo_refusals_are_coded_and_turkish(env):  # noqa: F811
    c, a101 = env.client, env.rooms["A101"]
    url = f"/api/v1/room-admin/rooms/{a101}/photo"
    # not an image at all, named like one: refused before decoding, in Turkish, with a code
    r = await c.post(url, files={"file": ("foto.png", b"not a picture at all", "image/png")}, headers=env.admin)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "image_not_image"
    assert "the file" not in detail["message_tr"] and detail["message_tr"].endswith("görseli değil.")
    # a PNG header with corrupt data gets past the magic bytes and fails in the decoder: still coded, still Turkish
    broken = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = await c.post(url, files={"file": ("foto.png", broken, "image/png")}, headers=env.admin)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "image_unreadable"
    assert detail["message_tr"] == "Dosya okunabilir bir jpg, png ya da gif görseli değil."
    assert "the file is not" not in detail["message_tr"] and "readable" in detail["message"]
    # a real image still works
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 30)).save(buf, "PNG")
    r = await c.post(url, files={"file": ("foto.png", buf.getvalue(), "image/png")}, headers=env.admin)
    assert r.status_code == 200 and r.json()["photo_url"], r.text


def test_image_errors_carry_a_code_and_turkish_text():
    from app.core.images import ImageError, sanitize_image

    cases = {
        b"": ("image_empty", "Dosya boş."),
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32: (
            "image_unreadable",
            "Dosya okunabilir bir jpg, png ya da gif görseli değil.",
        ),
        b"x" * 11: ("image_too_large", "Görsel 0 MB'tan büyük."),
    }
    for data, (code, tr) in cases.items():
        try:
            sanitize_image(data, max_bytes=10) if code == "image_too_large" else sanitize_image(data)
        except ImageError as exc:
            assert (exc.code, exc.message_tr) == (code, tr), data[:8]
        else:  # pragma: no cover - the call must refuse
            raise AssertionError(f"{data[:8]!r} was accepted")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "WEBP")
    try:
        sanitize_image(buf.getvalue())
    except ImageError as exc:
        assert exc.code == "image_type" and exc.message_tr == "Desteklenmeyen görsel türü; jpg, png ya da gif yükleyin."
    else:  # pragma: no cover
        raise AssertionError("webp was accepted by the jpg/png/gif sanitizer")


# --------------------------------------------------------------------------------------------- T-R2-32


async def test_relinking_the_same_instructor_writes_no_audit_row(sso):  # noqa: F811
    from app.models import Instructor

    async with dbmod.get_session_factory()() as s:
        a = Instructor(full_name="DR. ÖĞR. ÜYESİ ŞEHRİBAN SERBEST", canonical_name="sehriban serbest r2f")
        s.add(a)
        await s.commit()
        ia = a.id
    r = await sso.client.post(
        "/api/v1/auth/sso/admin/invites", json={"email": "r2f.serbest@uni.edu.tr"}, headers=sso.admin
    )
    assert r.status_code == 201, r.text
    uid = r.json()["user_id"]
    url = f"/api/v1/auth/sso/admin/users/{uid}/instructor"

    async def links() -> int:
        async with dbmod.get_session_factory()() as s:
            return (
                await s.execute(
                    select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "user.instructor_link")
                )
            ).scalar_one()

    before = await links()
    assert (await sso.client.put(url, json={"instructor_id": ia}, headers=sso.admin)).status_code == 200
    assert await links() == before + 1  # the real change is audited once
    r = await sso.client.put(url, json={"instructor_id": ia}, headers=sso.admin)
    assert r.status_code == 200 and r.json() == {"user_id": uid, "instructor_id": ia}
    assert await links() == before + 1  # F-05 S00: picking the same instructor again is not a change
