"""RF-12 and the W3-IDP open items (idp-2026-10-18): the SAML federation metadata signature check, encrypted
assertions (EncryptedAssertion with the SP decryption key, kept encrypted like the other secrets) and the optional
SP AuthnRequest signing (HTTP-Redirect binding), on the YETKİM-shaped fixture of test_w3b_idp_saml.py.

The IdP side (signing the federation aggregate, encrypting an assertion to the SP certificate) is done here with
signxml and cryptography, as Shibboleth / ADFS would; nothing leaves the process."""

from __future__ import annotations

import base64
import json
import logging
import os
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlsplit

import pytest

pytest.importorskip("signxml")
from app.core import db as dbmod
from app.core.security import decrypt_secret
from app.models import AuditEvent
from app.models.sso import SsoProvider, UserIdentity
from app.services.identity import saml as idp_saml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from lxml import etree
from signxml import XMLSigner
from sqlalchemy import select

from tests.test_w3b_idp_fakes import PANEL, idp, query_of  # noqa: F401
from tests.test_w3b_idp_saml import (
    CERT,
    IDP_ENTITY,
    KEY,
    METADATA_URL,
    OTHER_CERT,
    OTHER_KEY,
    SSO_URL,
    SamlIdp,
    _b64_cert,
    _keypair,
    federation_metadata,
    saml_response,
)

ADMIN = "/api/v1/auth/sso/admin/providers"
XENC = "http://www.w3.org/2001/04/xmlenc#"
XENC11 = "http://www.w3.org/2009/xmlenc11#"
DS = "http://www.w3.org/2000/09/xmldsig#"
SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
MD = "urn:oasis:names:tc:SAML:2.0:metadata"
#: the federation operator's metadata signing key (YETKİM signs its aggregate; the IdP signs assertions)
FED_KEY, FED_CERT = _keypair("YETKİM Metadata İmzalama")


# ------------------------------------------------------------------------------------------------ IdP-side helpers


def signed_metadata(
    *, key: bytes = FED_KEY, cert: bytes = FED_CERT, valid_days: int = 7, tamper: bool = False
) -> bytes:
    """The aggregate of test_w3b_idp_saml.py signed at its root (an enveloped signature over ``#_yetkim``), with a
    ``validUntil`` as federations publish it."""
    root = etree.fromstring(federation_metadata())
    root.set("ID", "_yetkim")
    until = datetime.now(UTC) + timedelta(days=valid_days)
    root.set("validUntil", until.strftime("%Y-%m-%dT%H:%M:%SZ"))
    signed = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
        root, key=key, cert=cert.decode(), reference_uri="#_yetkim"
    )
    if tamper:  # a man in the middle swaps the IdP's SSO URL after signing
        sso = signed.find(f".//{{{MD}}}SingleSignOnService[@Binding='{idp_saml.REDIRECT_BINDING}']")
        sso.set("Location", "https://evil.example/sso")
    return etree.tostring(signed)


def wrapped_metadata() -> bytes:
    """Signature wrapping: a signed copy of the IdP entity hidden inside an unsigned aggregate root."""
    root = etree.fromstring(federation_metadata())
    ent = root.findall(f"{{{MD}}}EntityDescriptor")[1]
    ent.set("ID", "_idp")
    copy = etree.fromstring(etree.tostring(ent))
    signed = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
        copy, key=FED_KEY, cert=FED_CERT.decode(), reference_uri="#_idp"
    )
    ent.append(signed.find(f"{{{DS}}}Signature"))
    return etree.tostring(root)


def _oaep(alg: str, digest: Any = None, mgf: Any = None) -> asym.OAEP:
    if alg == XENC + "rsa-oaep-mgf1p":
        return asym.OAEP(mgf=asym.MGF1(hashes.SHA1()), algorithm=digest or hashes.SHA1(), label=None)
    return asym.OAEP(mgf=asym.MGF1(mgf or hashes.SHA1()), algorithm=digest or hashes.SHA1(), label=None)


def encrypt_assertion(
    response_b64: str,
    sp_cert_pem: str,
    *,
    data_alg: str = XENC11 + "aes128-gcm",
    key_alg: str = XENC + "rsa-oaep-mgf1p",
    key_in_keyinfo: bool = False,
    sha256: bool = False,
) -> str:
    """Replace the (signed) Assertion of a test response by an EncryptedAssertion for the SP certificate, the way
    Shibboleth (EncryptedKey beside EncryptedData, AES-GCM) or ADFS (EncryptedKey inside KeyInfo, AES-CBC) do."""
    root = etree.fromstring(base64.b64decode(response_b64))
    assertion = root.find(f"{{{SAML_NS}}}Assertion")
    plain = etree.tostring(assertion)
    size = {"128": 16, "192": 24, "256": 32}[data_alg.split("aes")[1][:3]]
    sym = os.urandom(size)
    if data_alg.endswith("gcm"):
        iv = os.urandom(12)
        cipher = iv + AESGCM(sym).encrypt(iv, plain, None)
    else:
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        body = padder.update(plain) + padder.finalize()
        enc = Cipher(algorithms.AES(sym), modes.CBC(iv)).encryptor()
        cipher = iv + enc.update(body) + enc.finalize()
    pub = x509.load_pem_x509_certificate(sp_cert_pem.encode()).public_key()
    digest = mgf = None
    if sha256:
        digest, mgf = hashes.SHA256(), hashes.SHA256()
    if key_alg == XENC + "rsa-1_5":
        wrapped = pub.encrypt(sym, asym.PKCS1v15())  # type: ignore[union-attr]
    else:
        wrapped = pub.encrypt(sym, _oaep(key_alg, digest, mgf))  # type: ignore[union-attr]
    digest_xml = f'<ds:DigestMethod Algorithm="{XENC}sha256"/>' if sha256 else ""
    mgf_xml = f'<xenc11:MGF Algorithm="{XENC11}mgf1sha256"/>' if sha256 else ""
    ek = (
        f'<xenc:EncryptedKey Id="_ek1"><xenc:EncryptionMethod Algorithm="{key_alg}">{digest_xml}{mgf_xml}'
        "</xenc:EncryptionMethod>"
        f"<ds:KeyInfo><ds:X509Data><ds:X509Certificate>{_b64_cert(sp_cert_pem.encode())}</ds:X509Certificate>"
        "</ds:X509Data></ds:KeyInfo>"
        f"<xenc:CipherData><xenc:CipherValue>{base64.b64encode(wrapped).decode()}</xenc:CipherValue>"
        "</xenc:CipherData></xenc:EncryptedKey>"
    )
    keyinfo = ek if key_in_keyinfo else f'<ds:RetrievalMethod Type="{XENC}EncryptedKey" URI="#_ek1"/>'
    xml = (
        f'<saml:EncryptedAssertion xmlns:saml="{SAML_NS}" xmlns:xenc="{XENC}" xmlns:xenc11="{XENC11}" '
        f'xmlns:ds="{DS}"><xenc:EncryptedData Type="{XENC}Element">'
        f'<xenc:EncryptionMethod Algorithm="{data_alg}"/><ds:KeyInfo>{keyinfo}</ds:KeyInfo>'
        f"<xenc:CipherData><xenc:CipherValue>{base64.b64encode(cipher).decode()}</xenc:CipherValue>"
        f"</xenc:CipherData></xenc:EncryptedData>{'' if key_in_keyinfo else ek}</saml:EncryptedAssertion>"
    )
    root.replace(assertion, etree.fromstring(xml))
    return base64.b64encode(etree.tostring(root)).decode()


def sign_response(response_b64: str, key: bytes = KEY, cert: bytes = CERT) -> str:
    """Sign the whole samlp:Response (enveloped), as an IdP set to sign responses does."""
    root = etree.fromstring(base64.b64decode(response_b64))
    signed = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
        root, key=key, cert=cert.decode(), reference_uri="#" + root.get("ID")
    )
    # saml2 core: the Signature follows the Issuer
    sig = signed.find(f"{{{DS}}}Signature")
    signed.remove(sig)
    signed.insert(1, sig)
    return base64.b64encode(etree.tostring(signed)).decode()


# ------------------------------------------------------------------------------------------------ fixtures


class Federation:
    """The federation's metadata URL; ``doc`` is what it serves now."""

    def __init__(self) -> None:
        self.doc = signed_metadata()


@pytest.fixture
async def fed(idp, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    from app.services import sso as sso_service

    federation = Federation()
    previous = sso_service.transport

    async def route(req: Any) -> Any:
        if str(req.url) == METADATA_URL:
            return sso_service.http.Response(200, content=federation.doc)
        return await previous.handle_async_request(req)

    monkeypatch.setattr(sso_service, "transport", sso_service.http.MockTransport(route))
    p = await idp.create("saml", preset="yetkim")
    return idp, federation, p


async def _configure(env: Any, pid: int, **body: Any) -> dict[str, Any]:
    body = {"metadata_url": METADATA_URL, "idp_entity_id": IDP_ENTITY, "invite_only": False, **body}
    r = await env.put(pid, **body)
    assert r.status_code == 200, r.text
    return r.json()


def _row(checks: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(c for c in checks if c["key"] == key)


# ------------------------------------------------------------------------------------------------ RF-12 metadata


def test_parse_metadata_checks_the_federation_signature() -> None:
    cert = FED_CERT.decode()
    meta = idp_saml.parse_metadata(signed_metadata(), IDP_ENTITY, signing_cert=cert)
    assert meta["signed"] is True and meta["sso_url"] == SSO_URL and len(meta["certs"]) == 1
    # without a required certificate an unsigned aggregate still reads (the administrator's choice)
    assert idp_saml.parse_metadata(federation_metadata(), IDP_ENTITY)["signed"] is False
    cases = {
        "unsigned": federation_metadata(),
        "invalid": signed_metadata(key=OTHER_KEY, cert=OTHER_CERT),
    }
    cases["tampered"] = signed_metadata(tamper=True)
    cases["expired"] = signed_metadata(valid_days=-1)
    cases["wrapped"] = wrapped_metadata()
    want = {"unsigned": "unsigned", "invalid": "invalid", "tampered": "invalid", "expired": "expired"}
    want["wrapped"] = "unsigned"
    for name, doc in cases.items():
        with pytest.raises(idp_saml.MetadataError) as err:
            idp_saml.parse_metadata(doc, IDP_ENTITY, signing_cert=cert)
        assert err.value.code == want[name], name


async def test_required_signature_is_checked_and_refusals_say_why_in_turkish(fed) -> None:  # type: ignore[no-untyped-def]
    env, federation, p = fed
    # pasted as bare base64 with NBSPs and line breaks (as copied from the federation's web page)
    b64 = _b64_cert(FED_CERT)
    pasted = "\xa0" + "\r\n".join(b64[i : i + 64] for i in range(0, len(b64), 64)) + "\xa0"
    out = await _configure(env, p["id"], metadata_signing_cert=pasted)
    assert out["discovery"]["ok"] is True, out["discovery"]
    sig = _row(out["discovery"]["checks"], "metadata_signature")
    assert sig["ok"] is True and "imza" in sig["tr"].lower()
    assert out["saml"]["metadata_signed"] is True
    info = out["saml"]["metadata_signing_cert"]
    assert "YETKİM" in info["subject"] and len(info["sha256"]) == 95 and info["not_after"]
    r = await env.put(p["id"], enabled=True)
    assert r.status_code == 200, r.text

    # the federation (or someone in between) now serves an unsigned copy: refused, metadata dropped, reason shown
    federation.doc = federation_metadata()
    rep = (await env.client.post(f"{ADMIN}/{p['id']}/discover", headers=env.admin)).json()
    assert rep["ok"] is False
    row = _row(rep["checks"], "metadata_signature")
    assert row["ok"] is False and row["detail"] == "unsigned"
    assert "imzalı değil" in row["tr"] and "not signed" in row["en"]
    prov = (await env.client.get(f"{ADMIN}/{p['id']}", headers=env.admin)).json()
    assert prov["status"] == "error" and prov["configured"] is False and prov["saml"]["metadata_signed"] is False
    start = await env.client.get("/api/v1/auth/sso/yetkim/start")
    assert start.status_code == 302 and "/login?error=" in start.headers["location"]

    # a copy signed by another key: "could not be verified"; enabling then says why (TR first)
    federation.doc = signed_metadata(key=OTHER_KEY, cert=OTHER_CERT)
    r = await env.put(p["id"], enabled=False)
    assert r.status_code == 200, r.text
    rep = (await env.client.post(f"{ADMIN}/{p['id']}/discover", headers=env.admin)).json()
    row = _row(rep["checks"], "metadata_signature")
    assert row["detail"] == "invalid" and "doğrulanamadı" in row["tr"]
    r = await env.put(p["id"], enabled=True)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "metadata_signature" and "doğrulanamadı" in detail["tr"] and detail["en"]

    # an expired aggregate (validUntil in the past) is refused too
    federation.doc = signed_metadata(valid_days=-2)
    rep = (await env.client.post(f"{ADMIN}/{p['id']}/discover", headers=env.admin)).json()
    assert _row(rep["checks"], "metadata_signature")["detail"] == "expired"

    # clearing the certificate reads the metadata again without the check (administrator's decision, audited)
    federation.doc = federation_metadata()
    out = await _configure(env, p["id"], metadata_signing_cert="")
    assert out["discovery"]["ok"] is True and out["saml"]["metadata_signing_cert"] is None
    async with dbmod.get_session_factory()() as s:
        rows = (await s.execute(select(AuditEvent).where(AuditEvent.action == "sso.provider_update"))).scalars()
        afters = [e.after or {} for e in rows]
    assert any((a.get("options") or {}).get("metadata_signing_cert") for a in afters)
    assert all("BEGIN CERTIFICATE" not in json.dumps(a) for a in afters)


async def test_a_bad_signing_certificate_is_refused_in_both_languages(fed) -> None:  # type: ignore[no-untyped-def]
    env, _federation, p = fed
    r = await env.put(p["id"], metadata_signing_cert="MIIB bu bir sertifika değil")
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "invalid_certificate" and "Sertifika" in d["tr"] and "certificate" in d["en"]


# ------------------------------------------------------------------------------------------------ encrypted assertions


async def _sp_key(env: Any, pid: int) -> dict[str, Any]:
    r = await env.put(pid, sp_key_generate=True)
    assert r.status_code == 200, r.text
    return r.json()


async def _sp_cert(env: Any, slug: str) -> str:
    md = etree.fromstring((await env.client.get(f"/api/v1/auth/sso/{slug}/metadata")).content)
    kd = md.find(f".//{{{MD}}}KeyDescriptor[@use='encryption']")
    assert kd is not None, etree.tostring(md)
    b64 = kd.findtext(f".//{{{DS}}}X509Certificate").strip()
    return idp_saml.pem_certificate(b64)


async def test_encrypted_assertions_sign_in_with_the_sp_key(fed, caplog) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    env, _federation, p = fed
    await _configure(env, p["id"], metadata_signing_cert=FED_CERT.decode())
    out = await _sp_key(env, p["id"])
    assert out["saml"]["sp_private_key_set"] is True and out["saml"]["sp_certificate"]["sha256"]
    assert "sp_private_key" not in json.dumps(out).replace("sp_private_key_set", "")
    assert (await env.put(p["id"], enabled=True)).status_code == 200
    sp = SamlIdp(env, "yetkim")
    cert = await _sp_cert(env, "yetkim")
    md = (await env.client.get("/api/v1/auth/sso/yetkim/metadata")).text
    assert 'AuthnRequestsSigned="false"' in md and "aes256-gcm" in md

    # Shibboleth's default (AES-128-GCM, RSA-OAEP, EncryptedKey beside EncryptedData)
    rid, relay = await sp.start(next="/bookings")
    loc = await sp.post(relay, encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), cert))
    assert "ticket" in query_of(loc), loc
    # ADFS (AES-256-CBC, EncryptedKey inside KeyInfo; CBC only inside a signed Response, idp2-2026-10-18) and
    # xmlenc 1.1 RSA-OAEP with SHA-256
    for kwargs, signed_response in (
        ({"data_alg": XENC + "aes256-cbc", "key_in_keyinfo": True}, True),
        ({"key_alg": XENC11 + "rsa-oaep", "sha256": True}, False),
    ):
        rid, relay = await sp.start()
        resp = encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), cert, **kwargs)
        resp = sign_response(resp) if signed_response else resp
        assert "ticket" in query_of(await sp.post(relay, resp)), kwargs
    # a signed response around an encrypted, unsigned assertion (the response signature covers the ciphertext)
    rid, relay = await sp.start()
    inner = saml_response(rid, acs=sp.acs, audience=sp.entity, sign=False)
    assert "ticket" in query_of(await sp.post(relay, sign_response(encrypt_assertion(inner, cert))))

    # refusals: RSA PKCS#1 v1.5, a key for another SP, an unsigned encrypted assertion in an unsigned response
    other_key, other_cert = _keypair("sp.baska.edu.tr")
    for resp_of in (
        lambda r: encrypt_assertion(saml_response(r, acs=sp.acs, audience=sp.entity), cert, key_alg=XENC + "rsa-1_5"),
        lambda r: encrypt_assertion(saml_response(r, acs=sp.acs, audience=sp.entity), other_cert.decode()),
        lambda r: encrypt_assertion(saml_response(r, acs=sp.acs, audience=sp.entity, sign=False), cert),
    ):
        rid, relay = await sp.start()
        assert query_of(await sp.post(relay, resp_of(rid)))["error"] == "failed"
    async with dbmod.get_session_factory()() as s:
        refused = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_refused"))).scalars()
        details = [str((e.after or {}).get("detail")) for e in refused]
        prov = (await s.execute(select(SsoProvider).where(SsoProvider.name == "yetkim"))).scalar_one()
        audits = [e.after for e in (await s.execute(select(AuditEvent))).scalars()]
        idents = list((await s.execute(select(UserIdentity))).scalars())
    assert "rsa-1_5" in details[0] and "decrypt" in details[1] and "signed" in details[2]
    # the SP key is kept like the other secrets: Fernet-encrypted, never in the audit trail or the logs
    raw = json.dumps(prov.options)
    assert "PRIVATE KEY" not in raw and "PRIVATE KEY" in decrypt_secret(prov.options["sp_private_key_enc"])
    assert all("PRIVATE KEY" not in json.dumps(a, default=str) for a in audits)
    assert "PRIVATE KEY" not in caplog.text
    assert len(idents) == 1


async def _test_login(env: Any, sp: Any, pid: int, response_of: Any) -> dict[str, Any]:
    """Run the wizard's test login with the IdP answering ``response_of(request_id)``; the report."""
    r = (await env.client.post(f"{ADMIN}/{pid}/test", headers=env.admin)).json()
    q = {k: v[0] for k, v in parse_qs(urlsplit(r["authorize_url"]).query).items()}
    rid = etree.fromstring(zlib.decompress(base64.b64decode(q["SAMLRequest"]), -15)).get("ID")
    await sp.post(q["RelayState"], response_of(rid))
    return (await env.client.get(f"{ADMIN}/{pid}/test/{r['test_id']}", headers=env.admin)).json()


async def test_aes_cbc_needs_a_signed_response(fed) -> None:  # type: ignore[no-untyped-def]
    """idp2-2026-10-18 (orchestrator's decision): AES-CBC has no integrity of its own, so an unsigned Response around
    a CBC-encrypted assertion is refused before anything is decrypted (no padding oracle), even when the decrypted
    assertion would carry a valid signature. Inside a signed Response CBC passes; AES-GCM passes either way."""
    env, _federation, p = fed
    await _configure(env, p["id"])
    await _sp_key(env, p["id"])
    assert (await env.put(p["id"], enabled=True)).status_code == 200
    sp = SamlIdp(env, "yetkim")
    cert = await _sp_cert(env, "yetkim")
    cbc = {"data_alg": XENC + "aes256-cbc", "key_in_keyinfo": True}

    # unsigned Response, CBC-encrypted signed assertion: refused, with the reason in the provider's check rows
    rid, relay = await sp.start()
    loc = await sp.post(relay, encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), cert, **cbc))
    assert query_of(loc)["error"] == "failed"
    async with dbmod.get_session_factory()() as s:
        (ev,) = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_refused"))).scalars()
    assert "aes-cbc" in ev.after["detail"] and ev.after["reason"] == "invalid_token"
    out = (await env.client.get(f"{ADMIN}/{p['id']}", headers=env.admin)).json()
    print("DBG", out["discovery"]); row = _row(out["discovery"]["checks"], "assertion_encryption")
    assert row["ok"] is False and row["detail"] == "cbc_unsigned"
    assert row["tr"] == (
        "Şifreli onay AES-CBC kullanıyor; yanıt imzalı değilse kabul edilmez. IdP'de yanıt imzalamayı açın ya da "
        "AES-GCM seçin."
    )
    assert "AES-CBC" in row["en"] and "sign" in row["en"] and "AES-GCM" in row["en"]
    # the wizard's test login says the same, in both languages
    report = await _test_login(
        env, sp, p["id"], lambda r: encrypt_assertion(saml_response(r, acs=sp.acs, audience=sp.entity), cert, **cbc)
    )
    assert report["ok"] is False and report["hint"]["tr"] == row["tr"] and report["hint"]["en"] == row["en"]
    # re-reading the metadata keeps the row (it is about the IdP's responses, not its metadata)
    assert (await env.client.post(f"{ADMIN}/{p['id']}/discover", headers=env.admin)).status_code == 200
    out = (await env.client.get(f"{ADMIN}/{p['id']}", headers=env.admin)).json()
    assert _row(out["discovery"]["checks"], "assertion_encryption")["ok"] is False

    # the same CBC assertion inside a signed Response: accepted, and the refusal row goes away
    rid, relay = await sp.start()
    resp = sign_response(encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), cert, **cbc))
    assert "ticket" in query_of(await sp.post(relay, resp))
    out = (await env.client.get(f"{ADMIN}/{p['id']}", headers=env.admin)).json()
    assert all(c["key"] != "assertion_encryption" for c in out["discovery"]["checks"])

    # AES-GCM with an unsigned Response (the assertion signed) passes as before
    rid, relay = await sp.start()
    resp = encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), cert)
    assert "ticket" in query_of(await sp.post(relay, resp))
    report = await _test_login(
        env, sp, p["id"], lambda r: encrypt_assertion(saml_response(r, acs=sp.acs, audience=sp.entity), cert)
    )
    assert report["ok"] is True


def test_cbc_refusal_happens_before_any_decryption(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No padding oracle: an unsigned Response with CBC never reaches the decryptor."""
    from app.services.identity import saml_crypto

    called: list[int] = []
    monkeypatch.setattr(saml_crypto, "decrypt_element", lambda *a, **k: called.append(1) or b"")
    _key, sp_cert = _keypair("sp.uni.edu.tr")
    cfg = idp_saml.SamlConfig(
        slug="x",
        issuer=IDP_ENTITY,
        tenant_id="t",
        sso_url=SSO_URL,
        certs=(CERT.decode(),),
        sp_entity_id="e",
        acs_url="https://panel/acs",
        sp_key=_key.decode(),
    )
    resp = encrypt_assertion(
        saml_response("_r1", acs=cfg.acs_url, audience="e"), sp_cert.decode(), data_alg=XENC + "aes128-cbc"
    )
    with pytest.raises(idp_saml.SamlError) as exc:
        idp_saml.parse_response(cfg, resp, "_r1", datetime.now(UTC))
    assert "aes-cbc" in exc.value.detail and not called


async def test_without_an_sp_key_an_encrypted_assertion_is_refused(fed) -> None:  # type: ignore[no-untyped-def]
    env, _federation, p = fed
    await _configure(env, p["id"])
    assert (await env.put(p["id"], enabled=True)).status_code == 200
    sp = SamlIdp(env, "yetkim")
    other_key, other_cert = _keypair("sp")
    rid, relay = await sp.start()
    resp = encrypt_assertion(saml_response(rid, acs=sp.acs, audience=sp.entity), other_cert.decode())
    assert query_of(await sp.post(relay, resp))["error"] == "failed"
    async with dbmod.get_session_factory()() as s:
        (ev,) = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_refused"))).scalars()
    assert "no SP decryption key" in ev.after["detail"]


async def test_a_pasted_sp_key_must_match_its_certificate(fed) -> None:  # type: ignore[no-untyped-def]
    env, _federation, p = fed
    r = await env.put(p["id"], sp_private_key=KEY.decode(), sp_certificate=OTHER_CERT.decode())
    assert r.status_code == 422 and r.json()["detail"]["code"] == "sp_key_mismatch"
    assert "eşleşmiyor" in r.json()["detail"]["tr"]
    r = await env.put(p["id"], sp_private_key="-----BEGIN PRIVATE KEY-----\nbozuk\n-----END PRIVATE KEY-----")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_private_key"
    assert "bozuk" not in r.text
    r = await env.put(p["id"], sp_private_key=KEY.decode(), sp_certificate=CERT.decode())
    assert r.status_code == 200, r.text
    assert r.json()["saml"]["sp_certificate"]["subject"].endswith("idp.uni.edu.tr")


# ------------------------------------------------------------------------------------------------ AuthnRequest signing


async def test_authn_request_signing_is_optional_and_verifiable(fed) -> None:  # type: ignore[no-untyped-def]
    env, _federation, p = fed
    await _configure(env, p["id"])
    assert (await env.put(p["id"], enabled=True)).status_code == 200
    # off by default: no signature parameters
    loc = (await env.client.get("/api/v1/auth/sso/yetkim/start")).headers["location"]
    assert "Signature=" not in loc and "SigAlg=" not in loc
    # turning it on needs an SP key
    r = await env.put(p["id"], sign_requests=True)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "sp_key_required"
    assert "anahtar" in r.json()["detail"]["tr"]
    await _sp_key(env, p["id"])
    out = (await env.put(p["id"], sign_requests=True)).json()
    assert out["saml"]["sign_requests"] is True
    md = etree.fromstring((await env.client.get("/api/v1/auth/sso/yetkim/metadata")).content)
    spsso = md.find(f"{{{MD}}}SPSSODescriptor")
    assert spsso.get("AuthnRequestsSigned") == "true"
    assert spsso.find(f"{{{MD}}}KeyDescriptor[@use='signing']") is not None
    cert = await _sp_cert(env, "yetkim")

    loc = (await env.client.get("/api/v1/auth/sso/yetkim/start", params={"next": "/bookings"})).headers["location"]
    query = urlsplit(loc).query
    q = {k: v[0] for k, v in parse_qs(query).items()}
    assert q["SigAlg"] == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
    # SAML bindings §3.4.4.1: the signature covers the URL-encoded SAMLRequest, RelayState and SigAlg, in order
    signed_part, _, sig = query.rpartition("&Signature=")
    assert signed_part.startswith("SAMLRequest=") and "&RelayState=" in signed_part
    pub = x509.load_pem_x509_certificate(cert.encode()).public_key()
    pub.verify(  # type: ignore[union-attr]
        base64.b64decode(unquote_plus(sig)), signed_part.encode(), asym.PKCS1v15(), hashes.SHA256()
    )
    req = etree.fromstring(zlib.decompress(base64.b64decode(q["SAMLRequest"]), -15))
    assert req.get("AssertionConsumerServiceURL") == f"{PANEL}/api/v1/auth/sso/yetkim/acs"
    # removing the key while signing is on is refused with the reason
    r = await env.put(p["id"], sp_key_remove=True)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "sp_key_in_use"
    r = await env.put(p["id"], sign_requests=False, sp_key_remove=True)
    assert r.status_code == 200 and r.json()["saml"]["sp_private_key_set"] is False


def test_sp_key_material_never_reaches_repr() -> None:
    cfg = idp_saml.SamlConfig(
        slug="x",
        issuer=IDP_ENTITY,
        tenant_id="t",
        sso_url=SSO_URL,
        certs=(CERT.decode(),),
        sp_entity_id="e",
        acs_url="a",
        sp_key=KEY.decode(),
    )
    assert "PRIVATE" not in repr(cfg) and "PRIVATE" not in str(cfg)


def test_pem_helpers_normalise_turkish_paste() -> None:
    b64 = _b64_cert(CERT)
    assert idp_saml.pem_certificate(" " + b64[:30] + " \n" + b64[30:] + " ") == idp_saml.pem_certificate(b64)
    loaded = x509.load_pem_x509_certificate(idp_saml.pem_certificate(b64).encode())
    assert loaded.public_bytes(serialization.Encoding.PEM) == CERT
