"""SAML 2.0 provider (wave 3b W3-IDP; app/services/identity/saml.py): IdP metadata (a YETKİM-style federation
aggregate), SP metadata, the redirect AuthnRequest, a signed response through the ACS with a test key, and the
refusals: a tampered assertion, a foreign audience, a replayed RelayState, an unsigned assertion, and the
"kütüphane gerekli" state without the optional library."""

from __future__ import annotations

import base64
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

# the signature tests need the optional SAML extra (pip install '.[saml]'); the "kütüphane gerekli" state is tested in
# test_w3b_idp_saml_optional.py without it
pytest.importorskip("signxml")
from app.core import db as dbmod
from app.models import AuditEvent, User
from app.models.sso import UserIdentity
from app.services.identity import saml as idp_saml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner
from sqlalchemy import select

from tests.test_w3b_idp_fakes import PANEL, idp, query_of  # noqa: F401

ADMIN = "/api/v1/auth/sso/admin/providers"
IDP_ENTITY = "https://idp.uni.edu.tr/idp/shibboleth"
SSO_URL = "https://idp.uni.edu.tr/idp/profile/SAML2/Redirect/SSO"
METADATA_URL = "https://yetkim.org.tr/metadata/yetkim-metadata.xml"
MD = "urn:oasis:names:tc:SAML:2.0:metadata"


def _keypair(cn: str = "idp.uni.edu.tr") -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return pem_key, cert.public_bytes(serialization.Encoding.PEM)


KEY, CERT = _keypair()
OTHER_KEY, OTHER_CERT = _keypair("evil.example")


def _b64_cert(pem: bytes) -> str:
    return "".join(pem.decode().strip().splitlines()[1:-1])


def federation_metadata() -> bytes:
    """An aggregate with another SP and our IdP (as a federation publishes it)."""
    return f"""<?xml version="1.0"?>
<md:EntitiesDescriptor xmlns:md="{MD}" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Name="YETKİM">
  <md:EntityDescriptor entityID="https://sp.baska.edu.tr/shibboleth">
    <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"/>
  </md:EntityDescriptor>
  <md:EntityDescriptor entityID="{IDP_ENTITY}">
    <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
      <md:KeyDescriptor use="signing"><ds:KeyInfo><ds:X509Data><ds:X509Certificate>
        {_b64_cert(CERT)}
      </ds:X509Certificate></ds:X509Data></ds:KeyInfo></md:KeyDescriptor>
      <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="{SSO_URL}"/>
      <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{SSO_URL}"/>
    </md:IDPSSODescriptor>
  </md:EntityDescriptor>
</md:EntitiesDescriptor>""".encode()


def _instant(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def saml_response(
    request_id: str,
    *,
    acs: str,
    audience: str,
    name_id: str = "AAdzZWNyZXQxyGt0dqM1kz8r",
    mail: str = "ayse.yilmaz@uni.edu.tr",
    entitlement: str = "urn:mace:uni.edu.tr:planlama",
    key: bytes = KEY,
    cert: bytes = CERT,
    issuer: str = IDP_ENTITY,
    sign: bool = True,
    tamper: bool = False,
) -> str:
    now = datetime.now(UTC)
    aid = "_" + uuid.uuid4().hex
    xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
 xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_{uuid.uuid4().hex}" Version="2.0"
 IssueInstant="{_instant(now)}" Destination="{acs}" InResponseTo="{request_id}">
 <saml:Issuer>{issuer}</saml:Issuer>
 <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
 <saml:Assertion ID="{aid}" Version="2.0" IssueInstant="{_instant(now)}">
  <saml:Issuer>{issuer}</saml:Issuer>
  <saml:Subject>
   <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">{name_id}</saml:NameID>
   <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData InResponseTo="{request_id}" Recipient="{acs}"
     NotOnOrAfter="{_instant(now + timedelta(minutes=5))}"/>
   </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{_instant(now - timedelta(seconds=30))}" NotOnOrAfter="{_instant(now + timedelta(minutes=5))}">
   <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{_instant(now)}"><saml:AuthnContext>
   <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
  </saml:AuthnContext></saml:AuthnStatement>
  <saml:AttributeStatement>
   <saml:Attribute Name="urn:oid:0.9.2342.19200300.100.1.3" FriendlyName="mail"><saml:AttributeValue>{mail}</saml:AttributeValue></saml:Attribute>
   <saml:Attribute Name="urn:oid:2.16.840.1.113730.3.1.241" FriendlyName="displayName"><saml:AttributeValue>Ayşe Yılmaz</saml:AttributeValue></saml:Attribute>
   <saml:Attribute Name="urn:oid:1.3.6.1.4.1.5923.1.1.1.7" FriendlyName="eduPersonEntitlement"><saml:AttributeValue>{entitlement}</saml:AttributeValue></saml:Attribute>
  </saml:AttributeStatement>
 </saml:Assertion>
</samlp:Response>"""
    root = etree.fromstring(xml.encode())
    ns = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
    assertion = root.find("saml:Assertion", ns)
    if sign:
        signed = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
            assertion, key=key, cert=cert.decode()
        )
        root.replace(assertion, signed)
    if tamper:
        value = root.find(".//saml:Attribute[@FriendlyName='mail']/saml:AttributeValue", ns)
        value.text = "rektor@uni.edu.tr"
    return base64.b64encode(etree.tostring(root)).decode()


class SamlIdp:
    def __init__(self, env: Any, slug: str) -> None:
        self.env, self.slug = env, slug
        self.acs = f"{PANEL}/api/v1/auth/sso/{slug}/acs"
        self.entity = f"{PANEL}/api/v1/auth/sso/{slug}/metadata"

    async def start(self, **params: str) -> tuple[str, str]:
        """(request id, RelayState) of the AuthnRequest the browser carries to the IdP."""
        r = await self.env.client.get(f"/api/v1/auth/sso/{self.slug}/start", params=params)
        assert r.status_code == 302, r.text
        loc = r.headers["location"]
        assert loc.startswith(SSO_URL + "?"), loc
        q = {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}
        xml = zlib.decompress(base64.b64decode(q["SAMLRequest"]), -15)
        req = etree.fromstring(xml)
        assert req.get("AssertionConsumerServiceURL") == self.acs
        return req.get("ID"), q["RelayState"]

    async def post(self, relay: str, response: str) -> str:
        r = await self.env.client.post(
            f"/api/v1/auth/sso/{self.slug}/acs", data={"SAMLResponse": response, "RelayState": relay}
        )
        assert r.status_code == 302, r.text
        return r.headers["location"]


@pytest.fixture
async def saml(idp, monkeypatch):  # type: ignore[no-untyped-def]  # noqa: F811
    from app.services import sso as sso_service

    previous = sso_service.transport

    async def route(req: Any) -> Any:
        if str(req.url) == METADATA_URL:
            return sso_service.http.Response(200, content=federation_metadata())
        return await previous.handle_async_request(req)

    monkeypatch.setattr(sso_service, "transport", sso_service.http.MockTransport(route))
    p = await idp.create("saml", preset="yetkim")
    assert p["name"] == "yetkim" and p["invite_only"] is True
    # the YETKİM preset reads eduPersonScopedAffiliation; this IdP releases eduPersonEntitlement (pasted OID)
    r = await idp.put(
        p["id"],
        metadata_url=METADATA_URL,
        idp_entity_id=IDP_ENTITY,
        invite_only=False,
        groups_attribute="\xa0urn:oid:1.3.6.1.4.1.5923.1.1.1.7 ",
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["discovery"]["ok"] is True, out["discovery"]
    assert out["saml"]["idp_entity_id"] == IDP_ENTITY and out["saml"]["certificates"] == 1
    r = await idp.put(p["id"], enabled=True)
    assert r.status_code == 200, r.text
    return idp, SamlIdp(idp, "yetkim"), r.json()


async def test_setup_values_and_sp_metadata(saml) -> None:  # type: ignore[no-untyped-def]
    env, sp, p = saml
    setup = (await env.client.get(f"{ADMIN}/{p['id']}/setup", headers=env.admin)).json()
    values = {v["key"]: v["value"] for v in setup["console"]}
    assert values["acs_url"] == sp.acs and values["entity_id"] == sp.entity
    assert values["name_id_format"].endswith(":persistent")
    md = await env.client.get("/api/v1/auth/sso/yetkim/metadata")
    assert md.status_code == 200 and md.headers["content-type"].startswith("application/samlmetadata+xml")
    root = etree.fromstring(md.content)
    assert root.get("entityID") == sp.entity
    acs = root.find(f".//{{{MD}}}AssertionConsumerService")
    assert acs.get("Location") == sp.acs and "HTTP-POST" in acs.get("Binding")


async def test_signed_assertion_signs_in_and_maps_the_entitlement(saml) -> None:  # type: ignore[no-untyped-def]
    env, sp, p = saml
    rid, relay = await sp.start(next="/bookings")
    loc = await sp.post(relay, saml_response(rid, acs=sp.acs, audience=sp.entity))
    q = query_of(loc)
    assert urlsplit(loc).path == "/login/sso" and q["welcome"] == "self" and q["next"] == "/bookings"
    tok = (await env.client.post("/api/v1/auth/sso/exchange", json={"ticket": q["ticket"]})).json()["access_token"]
    me = (await env.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})).json()
    assert me["email"] == "ayse.yilmaz@uni.edu.tr" and me["full_name"] == "Ayşe Yılmaz"
    async with dbmod.get_session_factory()() as s:
        (ident,) = (await s.execute(select(UserIdentity))).scalars()
    assert ident.provider == "yetkim" and ident.subject == "AAdzZWNyZXQxyGt0dqM1kz8r" and ident.issuer == IDP_ENTITY
    # the RelayState is single use
    again = await sp.post(relay, saml_response(rid, acs=sp.acs, audience=sp.entity))
    assert query_of(again)["error"] == "failed"


async def test_tampered_unsigned_foreign_and_wrong_audience_are_refused(saml) -> None:  # type: ignore[no-untyped-def]
    env, sp, _p = saml
    for kwargs in (
        {"tamper": True},
        {"sign": False},
        {"key": OTHER_KEY, "cert": OTHER_CERT},
        {"audience": "https://sp.baska.edu.tr/shibboleth"},
    ):
        rid, relay = await sp.start()
        body = {"acs": sp.acs, "audience": sp.entity, **kwargs}
        loc = await sp.post(relay, saml_response(rid, **body))
        assert query_of(loc)["error"] == "failed", kwargs
    # an assertion for another request id (replayed from an older login) is refused too
    rid, relay = await sp.start()
    loc = await sp.post(relay, saml_response("_old-request", acs=sp.acs, audience=sp.entity))
    assert query_of(loc)["error"] in ("failed",)
    async with dbmod.get_session_factory()() as s:
        assert not list((await s.execute(select(User).where(User.email == "rektor@uni.edu.tr"))).scalars())
        refused = (await s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_refused"))).scalars()
        details = [str((e.after or {}).get("detail")) for e in refused]
    assert ["signature" in d for d in details[:3]] == [True, False, True]
    assert "neither the response nor the assertion is signed" in details[1]
    assert "audience" in details[3] and "InResponseTo" in details[4]


async def test_test_login_reports_saml_attributes(saml) -> None:  # type: ignore[no-untyped-def]
    env, sp, p = saml
    r = (await env.client.post(f"{ADMIN}/{p['id']}/test", headers=env.admin)).json()
    q = {k: v[0] for k, v in parse_qs(urlsplit(r["authorize_url"]).query).items()}
    rid = etree.fromstring(zlib.decompress(base64.b64decode(q["SAMLRequest"]), -15)).get("ID")
    loc = await sp.post(q["RelayState"], saml_response(rid, acs=sp.acs, audience=sp.entity))
    assert loc.endswith("ok=1")
    res = (await env.client.get(f"{ADMIN}/{p['id']}/test/{r['test_id']}", headers=env.admin)).json()
    assert res["ok"] is True and res["verified_email"] == "ayse.yilmaz@uni.edu.tr"
    assert res["groups"] == ["urn:mace:uni.edu.tr:planlama"] and "mail" in res["attributes"]


def test_metadata_parser_refuses_entities_and_needs_the_entity_id_in_an_aggregate() -> None:
    with pytest.raises(ValueError, match="DTD"):
        idp_saml.parse_metadata(b'<!DOCTYPE x [<!ENTITY a "b">]><md:EntityDescriptor xmlns:md="' + MD.encode() + b'"/>')
    meta = idp_saml.parse_metadata(federation_metadata(), IDP_ENTITY)
    assert meta["sso_url"] == SSO_URL and len(meta["certs"]) == 1
    # one IdP in the aggregate: found without the entity id
    assert idp_saml.parse_metadata(federation_metadata())["entity_id"] == IDP_ENTITY
    with pytest.raises(ValueError, match="not in this metadata"):
        idp_saml.parse_metadata(federation_metadata(), "https://idp.baska.edu.tr/idp")
