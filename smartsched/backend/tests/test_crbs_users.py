"""Users: CSV import of real Bahar instructors (Turkish names, cp1254 / UTF-8, ``;`` / ``,``), username
login without regard to the Turkish dotted/dotless I, forced password change, one-time reset tokens
(shown to the admin without SMTP, e-mailed with SMTP), and LDAP login mocked at the ``ldap3`` boundary."""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

from app.core import db as dbmod
from app.core.identity import fold_username
from app.importers import normalize as n
from app.models import Instructor, Program
from app.services import bookings_ldap, bookings_notify
from ldap3.core.exceptions import LDAPSocketOpenError
from sqlalchemy import select

from tests.crbs_env import env  # noqa: F401
from tests.crbs_support import role_id

TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


async def _real_people(k: int = 2) -> list[Instructor]:
    async with dbmod.get_session_factory()() as s:
        rows = list((await s.execute(select(Instructor).order_by(Instructor.id))).scalars())
    turkish = [i for i in rows if any(ch in i.full_name for ch in "İŞĞÜÖÇışğüöç") and len(i.full_name.split()) >= 2]
    assert len(turkish) >= k
    return turkish[:k]


async def _program(name_like: str) -> Program:
    async with dbmod.get_session_factory()() as s:
        progs = list((await s.execute(select(Program))).scalars())
    return next(p for p in progs if n.tr_casefold(p.name).startswith(name_like))


async def test_csv_import_of_real_instructors(env):  # noqa: F811
    p1, p2 = await _real_people()
    psy = await _program("psikoloji")
    first1, *rest1 = p1.full_name.split()
    first2, *rest2 = p2.full_name.split()
    user1 = f"{first1}.{rest1[-1]}"  # keeps Turkish letters, e.g. "Ayşe.Kılıç"
    lines = [
        "Kullanıcı adı;Ad;Soyad;E-posta;Parola;Rol;Bölüm;Parola değişikliği",
        f"{user1};{first1};{rest1[-1]};{n.tr_lower(first1).translate(TR)}@uni.edu.tr;ilk-parola-1;TEACHER;{n.tr_upper(psy.name)};",
        f"{first2.translate(TR)}.{rest2[-1].translate(TR)};{first2};{rest2[-1]};;;teacher;;Evet",
        f"{n.tr_upper(user1)};X;Y;;parola-123;;;",
        ";Boş;Kullanıcı;;parola-123;;;",
        "gecersiz.posta;A;B;not-an-email;parola-123;;;",
    ]
    data = ("\r\n".join(lines) + "\r\n").encode("cp1254")  # Excel's "CSV (semicolon)" on Turkish Windows
    teacher = await role_id(env.client, env.admin, "TEACHER")
    r = await env.client.post(
        "/api/v1/users/import",
        files={"file": ("ogretim-elemanlari.csv", data, "text/csv")},
        data={"password": "varsayilan-parola", "enabled": "true"},
        headers=env.admin,
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["created"] == 2
    status = [x["status"] for x in res["results"]]
    assert status == ["success", "success", "username_exists", "username_empty", "invalid"]
    users = {
        u["username"]: u for u in (await env.client.get("/api/v1/users", headers=env.admin)).json() if u["username"]
    }
    u1 = users[fold_username(user1)]
    assert u1["role_id"] == teacher and u1["department_id"] == psy.id and u1["displayname"] == f"{first1} {rest1[-1]}"
    assert u1["email"].endswith("@uni.edu.tr") and u1["force_password_reset"] is False
    u2 = next(u for k, u in users.items() if k.startswith(fold_username(first2.translate(TR))))
    assert u2["email"] is None and u2["force_password_reset"] is True

    # username login is case- and dotted/dotless-I-insensitive; the stored form is folded
    for typed in (user1, n.tr_upper(user1), user1.upper(), n.tr_lower(user1)):
        r = await env.client.post("/api/v1/auth/login", json={"username": typed, "password": "ilk-parola-1"})
        assert r.status_code == 200, (typed, r.text)
    # the historic "email" field accepts a username too
    assert (
        await env.client.post("/api/v1/auth/login", json={"email": user1, "password": "ilk-parola-1"})
    ).status_code == 200

    # the second user got the default password and must change it first
    login = await env.client.post(
        "/api/v1/auth/login", json={"username": u2["username"], "password": "varsayilan-parola"}
    )
    assert login.status_code == 200 and login.json()["password_change_required"] is True
    h2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    blocked = await env.client.get("/api/v1/bookings/context", headers=h2)
    assert blocked.status_code == 403 and blocked.json()["detail"] == "password_change_required"
    assert (await env.client.get("/api/v1/auth/me", headers=h2)).status_code == 200
    same = await env.client.post("/api/v1/auth/change-password", json={"new_password": "varsayilan-parola"}, headers=h2)
    assert same.status_code == 422  # must differ (CRBS is_not_current_password)
    ok = await env.client.post("/api/v1/auth/change-password", json={"new_password": "yeni-parola-2026"}, headers=h2)
    assert ok.status_code == 200
    assert (await env.client.get("/api/v1/bookings/context", headers=h2)).status_code == 200


class FakeSMTP:
    sent: list[EmailMessage] = []
    fail: bool = False

    def __init__(self, host: str, port: int, timeout: int = 15, **_: Any) -> None:
        self.host, self.port = host, port

    def starttls(self, **_: Any) -> None: ...

    def login(self, user: str, password: str) -> None:
        assert password == "smtp-gizli"

    def send_message(self, msg: EmailMessage) -> None:
        if FakeSMTP.fail:
            raise OSError("connection refused")
        FakeSMTP.sent.append(msg)

    def quit(self) -> None: ...

    def close(self) -> None: ...


async def test_reset_tokens_with_and_without_smtp(env, monkeypatch):  # noqa: F811
    c = env.client
    uid, _ = await env.user("unutkan@uni.edu.tr")
    r = await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)
    assert r.status_code == 200
    first = r.json()
    assert first["emailed"] is False and len(first["token"]) >= 20  # no SMTP: the admin passes it on
    second = (await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)).json()
    assert (
        await c.post("/api/v1/auth/password-reset/confirm", json={"token": first["token"], "password": "yeni-parola-1"})
    ).status_code == 400  # revoked
    assert (
        await c.post(
            "/api/v1/auth/password-reset/confirm", json={"token": second["token"], "password": "yeni-parola-1"}
        )
    ).status_code == 200
    assert (
        await c.post(
            "/api/v1/auth/password-reset/confirm", json={"token": second["token"], "password": "yeni-parola-2"}
        )
    ).status_code == 400  # one-time
    assert (
        await c.post("/api/v1/auth/login", json={"email": "unutkan@uni.edu.tr", "password": "yeni-parola-1"})
    ).status_code == 200

    # public request without SMTP: recorded for the admins, never reveals whether the account exists
    assert (
        await c.post("/api/v1/auth/password-reset/request", json={"email": "unutkan@uni.edu.tr"})
    ).status_code == 202
    assert (await c.post("/api/v1/auth/password-reset/request", json={"email": "yok@uni.edu.tr"})).status_code == 202
    box = (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
    assert [o["kind"] for o in box].count("password_reset_request") == 1

    # with SMTP the code is e-mailed and not shown; the outbox keeps no live code
    monkeypatch.setattr(bookings_notify.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []
    r = await c.put(
        "/api/v1/org/smtp",
        json={
            "host": "smtp.uni.edu.tr",
            "port": 587,
            "username": "bildirim",
            "password": "smtp-gizli",
            "from_address": "Bildirim@Uni.edu.tr",
        },
        headers=env.admin,
    )
    assert r.status_code == 200 and r.json()["configured"] is True
    assert r.json()["password"] == {"set": True, "masked": "smtp********izli"}
    assert "smtp-gizli" not in str(r.json())
    issued = (await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)).json()
    assert issued["emailed"] is True and issued["token"] is None
    msg = FakeSMTP.sent[-1]
    assert msg["To"] == "unutkan@uni.edu.tr" and msg["From"].endswith("<bildirim@uni.edu.tr>")
    code = next(line for line in msg.get_content().splitlines() if line and " " not in line)
    assert (
        await c.post("/api/v1/auth/password-reset/confirm", json={"token": code, "password": "yeni-parola-3"})
    ).status_code == 200
    box = (await c.get("/api/v1/booking-admin/outbox", headers=env.admin)).json()
    sent = next(o for o in box if o["kind"] == "password_reset")
    assert sent["status"] == "SENT" and code not in sent["body"]
    # SMTP failure: recorded as FAILED with the error; the admin gets the code instead
    FakeSMTP.fail = True
    try:
        failed = (await c.post(f"/api/v1/users/{uid}/reset-token", headers=env.admin)).json()
    finally:
        FakeSMTP.fail = False
    assert failed["emailed"] is False and failed["token"]
    box = (await c.get("/api/v1/booking-admin/outbox", params={"status": "FAILED"}, headers=env.admin)).json()
    assert box and "connection refused" in box[0]["error"]
    # test message endpoint
    t = (await c.post("/api/v1/org/smtp/test", json={"to": "Hoca@Uni.edu.tr"}, headers=env.admin)).json()
    assert t["status"] == "SENT" and FakeSMTP.sent[-1]["To"] == "hoca@uni.edu.tr"


class _Values:
    def __init__(self, v: str) -> None:
        self.values = [v]


class _Entry:
    def __init__(self, dn: str, attrs: dict[str, str]) -> None:
        self.entry_dn = dn
        self._attrs = attrs
        self.entry_attributes = list(attrs)

    def __getitem__(self, k: str) -> _Values:
        return _Values(self._attrs[k])


class FakeDirectory:
    """Stands in for ``ldap3.Connection``: one person, password ``doğru-parola``."""

    people = {
        "ilker.sahin": {"givenName": "İlker", "sn": "Şahin", "mail": "Ilker.Sahin@Uni.edu.tr"},
    }
    password = "doğru-parola"
    down = False
    binds: list[str] = []

    def __init__(self, server: Any, user: str, password: str, **_: Any) -> None:
        if FakeDirectory.down:
            raise LDAPSocketOpenError("socket connection error")
        self.user, self.pw = user, password
        self.entries: list[_Entry] = []
        self.result: dict[str, Any] = {}

    def bind(self) -> bool:
        FakeDirectory.binds.append(self.user)
        uid = self.user.split(",")[0].removeprefix("uid=").lower()  # LDAP uid matching ignores case
        ok = uid in FakeDirectory.people and self.pw == FakeDirectory.password
        self.result = {} if ok else {"description": "invalidCredentials"}
        return ok

    def search(self, base: str, flt: str, attributes: Any = None) -> bool:
        uid = flt.removeprefix("(uid=").removesuffix(")").lower()
        person = FakeDirectory.people.get(uid)
        self.entries = [_Entry(f"uid={uid},{base}", person)] if person else []
        return True

    def unbind(self) -> None: ...


async def test_ldap_login_creates_updates_and_falls_back(env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(bookings_ldap.ldap3, "Connection", FakeDirectory)
    FakeDirectory.down, FakeDirectory.binds = False, []
    c = env.client
    teacher = await role_id(c, env.admin, "TEACHER")
    cfg = {
        "enabled": True,
        "server": "ldap.uni.edu.tr",
        "port": 389,
        "bind_dn_format": "uid=:user,ou=people,dc=uni,dc=edu,dc=tr",
        "base_dn": "ou=people,dc=uni,dc=edu,dc=tr",
        "search_filter": "(uid=:user)",
        "attr_firstname": "givenName",
        "attr_lastname": "sn",
        "attr_displayname": ":givenName :sn",
        "attr_email": "mail",
        "default_role_id": teacher,
    }
    assert (await c.put("/api/v1/org/auth/ldap", json=cfg, headers=env.admin)).status_code == 200
    probe = (
        await c.post(
            "/api/v1/org/auth/ldap/test",
            json={"username": "ilker.sahin", "password": "doğru-parola"},
            headers=env.admin,
        )
    ).json()
    assert probe["ok"] and probe["mapped"] == {
        "firstname": "İlker",
        "lastname": "Şahin",
        "displayname": "İlker Şahin",
        "email": "Ilker.Sahin@Uni.edu.tr",
    }
    assert (await c.get("/api/v1/org/public")).json()["ldap_enabled"] is True

    r = await c.post("/api/v1/auth/login", json={"username": "ILKER.SAHIN", "password": "doğru-parola"})
    assert r.status_code == 200, r.text
    assert FakeDirectory.binds[-1] == "uid=ILKER.SAHIN,ou=people,dc=uni,dc=edu,dc=tr"  # bound as typed
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await c.get("/api/v1/auth/me", headers=h)).json()
    assert me["username"] == "ilker.sahin" and me["role"] == "TEACHER" and me["auth_source"] == "ldap"
    assert me["email"] == "ilker.sahin@uni.edu.tr" and me["full_name"] == "İlker Şahin"
    assert (
        await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "yanlış"})
    ).status_code == 401

    # directory unreachable: the local copy of the last good password is used (CRBS fallback)
    FakeDirectory.down = True
    assert (
        await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "doğru-parola"})
    ).status_code == 200
    FakeDirectory.down = False

    # a disabled account is refused even though the directory would accept it
    await c.put(f"/api/v1/users/{me['id']}", json={"is_active": False}, headers=env.admin)
    assert (
        await c.post("/api/v1/auth/login", json={"username": "ilker.sahin", "password": "doğru-parola"})
    ).status_code == 403
    # unknown people are not created when create_users is off
    FakeDirectory.people["yeni.kisi"] = {"givenName": "Yeni", "sn": "Kişi", "mail": "yeni@uni.edu.tr"}
    await c.put("/api/v1/org/auth/ldap", json={"create_users": False}, headers=env.admin)
    assert (
        await c.post("/api/v1/auth/login", json={"username": "yeni.kisi", "password": "doğru-parola"})
    ).status_code == 401
    del FakeDirectory.people["yeni.kisi"]


async def test_search_profile_and_delete_keeps_booking_history(env):  # noqa: F811
    c = env.client
    uid, h = await env.user("şükrü.öztürk@uni.edu.tr", displayname="Şükrü Öztürk", username="sukru.ozturk")
    found = (await c.get("/api/v1/users/search", params={"q": "ŞÜKRÜ"}, headers=env.admin)).json()
    assert found["total"] == 1 and found["items"][0]["id"] == uid
    assert (await c.get("/api/v1/users/search", params={"q": "sukru"}, headers=env.admin)).json()["total"] == 1
    teacher = await role_id(c, env.admin, "TEACHER")
    by_role = (await c.get("/api/v1/users/search", params={"role_id": teacher}, headers=env.admin)).json()
    assert uid in [u["id"] for u in by_role["items"]]
    assert (await c.get("/api/v1/users/search", headers=h)).status_code == 403

    prof = await c.put(
        "/api/v1/auth/profile",
        json={"firstname": "Şükrü", "lastname": "Öztürk", "ext": "4073", "language": "tr"},
        headers=h,
    )
    assert prof.status_code == 200 and prof.json()["ext"] == "4073" and prof.json()["role_name"] == "Teacher"
    assert (await c.put("/api/v1/auth/profile", json={"language": "xx"}, headers=h)).status_code == 422
    wrong = await c.post("/api/v1/auth/change-password", json={"current_password": "yanlış", "new_password": "yeni-parola-9"}, headers=h)
    assert wrong.status_code == 403

    b = (await env.book(h, "A101", __import__("datetime").date(2026, 2, 16), "P1", notes="Seminer")).json()
    assert (await c.delete(f"/api/v1/users/{uid}", headers=env.admin)).status_code == 204
    detail = (await c.get(f"/api/v1/bookings/{b['id']}", headers=env.admin)).json()
    assert detail["status"] == "BOOKED" and detail["user_id"] is None and detail["notes"] == "Seminer"
