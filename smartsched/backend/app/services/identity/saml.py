"""SAML 2.0 service provider for the ``saml`` kind (Shibboleth, eduGAIN, Turkey's YETKİM federation, ADFS; wave 3b
W3-IDP).

The XML signature is verified by **signxml** (Apache-2.0, maintained; pure Python on lxml + cryptography) behind an
optional import: without it :data:`AVAILABLE` is false, the gallery card says "kütüphane gerekli" and a SAML provider
can be configured but never enabled (``library_required``).

What the SP does (HTTP-Redirect AuthnRequest, HTTP-POST response to the ACS):

* **Metadata** (:func:`parse_metadata`): the IdP's entity id, its HTTP-Redirect ``SingleSignOnService``, its
  ``SingleLogoutService`` and its signing certificates; an ``EntitiesDescriptor`` (a federation aggregate such as
  YETKİM's) needs the IdP's entity id. DTDs and entities are refused.
* **Response** (:func:`parse_response`): the signature of the Response or of the Assertion is verified against
  the metadata certificates and only the *signed* element is read afterwards (XML signature wrapping); then the
  issuer, the status, ``Destination`` / ``Recipient`` (the ACS URL), ``InResponseTo`` (the request id kept in the
  state row), ``NotBefore`` / ``NotOnOrAfter`` (2 minutes of skew), the audience (the SP entity id) and the bearer
  subject confirmation. Encrypted assertions are refused (switch encryption off at the IdP).
* **Identity** is the persistent NameID (or a configured attribute such as eduPersonPrincipalName) under the IdP's
  entity id; the e-mail comes from the ``mail`` attribute, groups from eduPersonEntitlement / affiliation.
"""

from __future__ import annotations

import base64
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.services.identity import kinds
from app.services.identity.oidc import namespace, plain, secure_url

try:  # optional: python -m pip install signxml
    from lxml import etree
    from signxml import XMLVerifier
    from signxml.exceptions import InvalidInput, InvalidSignature

    AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by monkeypatching AVAILABLE in the tests
    etree = None  # type: ignore[assignment]
    XMLVerifier = None  # type: ignore[assignment,misc]
    AVAILABLE = False

NS = {
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
}
REDIRECT_BINDING = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
POST_BINDING = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"
BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"
SKEW = timedelta(minutes=2)
MAX_XML = 512 * 1024
#: friendly attribute names accepted next to the OID names of the presets
FRIENDLY = {
    kinds.ATTR_MAIL: ("mail", "email", "emailaddress"),
    kinds.ATTR_DISPLAY_NAME: ("displayName", "cn", "name"),
    kinds.ATTR_ENTITLEMENT: ("eduPersonEntitlement",),
    kinds.ATTR_AFFILIATION: ("eduPersonScopedAffiliation", "eduPersonAffiliation"),
    kinds.ATTR_EPPN: ("eduPersonPrincipalName",),
}


class SamlError(Exception):
    """``code`` is a key of sso.PUBLIC_CODES (``invalid_token``, ``tenant``, ``state``, ``unavailable``)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = code, detail[:200]


@dataclass(frozen=True)
class SamlConfig:
    slug: str
    issuer: str  # the IdP entity id
    tenant_id: str  # identity namespace (digest of the entity id)
    sso_url: str
    certs: tuple[str, ...]
    sp_entity_id: str
    acs_url: str
    slo_url: str | None = None
    email_attribute: str = kinds.ATTR_MAIL
    name_attribute: str = kinds.ATTR_DISPLAY_NAME
    groups_attribute: str = kinds.ATTR_ENTITLEMENT
    #: ``None``: the NameID; else an attribute (e.g. eduPersonPrincipalName)
    subject_attribute: str | None = None
    kind: str = kinds.SAML
    groups_claim: str = "groups"
    roles_claim: str = "roles"


def sp_entity_id(base: str, slug: str) -> str:
    return f"{base}/api/v1/auth/sso/{slug}/metadata"


def acs_url(base: str, slug: str) -> str:
    return f"{base}/api/v1/auth/sso/{slug}/acs"


def config_from(row: Any, base: str, opts: dict[str, Any]) -> SamlConfig | None:
    meta = opts.get("metadata") or {}
    if not (meta.get("entity_id") and meta.get("sso_url") and meta.get("certs")):
        return None
    return SamlConfig(
        slug=row.name,
        issuer=meta["entity_id"],
        tenant_id=namespace(meta["entity_id"]),
        sso_url=meta["sso_url"],
        slo_url=meta.get("slo_url"),
        certs=tuple(meta["certs"]),
        sp_entity_id=sp_entity_id(base, row.name),
        acs_url=acs_url(base, row.name),
        email_attribute=opts.get("email_attribute") or kinds.ATTR_MAIL,
        name_attribute=opts.get("name_attribute") or kinds.ATTR_DISPLAY_NAME,
        groups_attribute=opts.get("groups_attribute") or kinds.ATTR_ENTITLEMENT,
        subject_attribute=opts.get("subject_attribute") or None,
    )


# --------------------------------------------------------------------------------------------------- XML


def _parser() -> Any:
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)


def _parse(data: bytes) -> Any:
    if len(data) > MAX_XML:
        raise ValueError("the XML document is too large")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("DTDs and entities are not allowed")
    return etree.fromstring(data, parser=_parser())


def _pem(b64: str) -> str:
    body = "".join(b64.split())
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def parse_metadata(xml: bytes, entity_id: str | None = None) -> dict[str, Any]:
    """``{entity_id, sso_url, slo_url, certs}`` of the IdP; raises ``ValueError`` (English; the caller words it)."""
    if not AVAILABLE:
        raise ValueError("library_required")
    root = _parse(xml)
    want = plain(entity_id) if entity_id else None
    if root.tag == f"{{{NS['md']}}}EntitiesDescriptor":
        candidates = root.findall(".//md:EntityDescriptor", NS)
        if not want:
            idps = [e for e in candidates if e.find("md:IDPSSODescriptor", NS) is not None]
            if len(idps) != 1:
                raise ValueError("federation metadata: give the IdP entity id")
            ent = idps[0]
        else:
            matches = [e for e in candidates if e.get("entityID") == want]
            if not matches:
                raise ValueError("the IdP entity id is not in this metadata")
            ent = matches[0]
    elif root.tag == f"{{{NS['md']}}}EntityDescriptor":
        ent = root
        if want and ent.get("entityID") != want:
            raise ValueError("the metadata is for another entity id")
    else:
        raise ValueError("not SAML metadata (EntityDescriptor)")
    idp = ent.find("md:IDPSSODescriptor", NS)
    if idp is None:
        raise ValueError("the entity is not an identity provider (no IDPSSODescriptor)")
    sso = next(
        (s.get("Location") for s in idp.findall("md:SingleSignOnService", NS) if s.get("Binding") == REDIRECT_BINDING),
        None,
    )
    if not sso or not secure_url(sso):
        raise ValueError("no HTTPS SingleSignOnService with the HTTP-Redirect binding")
    slo = next(
        (s.get("Location") for s in idp.findall("md:SingleLogoutService", NS) if s.get("Binding") == REDIRECT_BINDING),
        None,
    )
    certs: list[str] = []
    for kd in idp.findall("md:KeyDescriptor", NS):
        if kd.get("use") not in (None, "signing"):
            continue
        for c in kd.findall(".//ds:X509Certificate", NS):
            if c.text and c.text.strip():
                certs.append(_pem(c.text))
    if not certs:
        raise ValueError("no signing certificate in the metadata")
    return {"entity_id": ent.get("entityID"), "sso_url": sso, "slo_url": slo, "certs": certs}


def sp_metadata(cfg_entity_id: str, acs: str) -> str:
    """The SP metadata the IdP administrator imports (no SP certificate: requests are not signed, assertions must
    be)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<md:EntityDescriptor xmlns:md="{NS["md"]}" entityID="{_attr(cfg_entity_id)}">\n'
        '  <md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
        f"    <md:NameIDFormat>{PERSISTENT}</md:NameIDFormat>\n"
        f'    <md:AssertionConsumerService Binding="{POST_BINDING}" Location="{_attr(acs)}" index="0" '
        'isDefault="true"/>\n'
        "  </md:SPSSODescriptor>\n"
        "</md:EntityDescriptor>\n"
    )


def _attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _instant(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def authn_request_url(cfg: SamlConfig, request_id: str, relay_state: str, now: datetime) -> str:
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" ID="{_attr(request_id)}" '
        f'Version="2.0" IssueInstant="{_instant(now)}" Destination="{_attr(cfg.sso_url)}" '
        f'ProtocolBinding="{POST_BINDING}" AssertionConsumerServiceURL="{_attr(cfg.acs_url)}">'
        f"<saml:Issuer>{_attr(cfg.sp_entity_id)}</saml:Issuer>"
        f'<samlp:NameIDPolicy Format="{PERSISTENT}" AllowCreate="true"/>'
        "</samlp:AuthnRequest>"
    )
    deflated = zlib.compress(xml.encode("utf-8"))[2:-4]  # raw DEFLATE (RFC 1951), as the binding requires
    query = urlencode({"SAMLRequest": base64.b64encode(deflated).decode("ascii"), "RelayState": relay_state})
    sep = "&" if "?" in cfg.sso_url else "?"
    return f"{cfg.sso_url}{sep}{query}"


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    if "." in text:  # fractional seconds of any length
        head, _, tail = text.partition(".")
        digits = "".join(ch for ch in tail if ch.isdigit())
        zone = tail[len(digits) :]
        text = f"{head}.{digits[:6].ljust(6, '0')}{zone}"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)


def _verify(data: bytes, certs: tuple[str, ...]) -> Any:
    last: Exception | None = None
    for cert in certs:
        try:
            return XMLVerifier().verify(data, x509_cert=cert, expect_references=1).signed_xml
        except (InvalidSignature, InvalidInput) as exc:
            last = exc
    raise SamlError("invalid_token", f"signature: {type(last).__name__ if last else 'no certificate'}")


def _attributes(assertion: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for attr in assertion.findall(".//saml:AttributeStatement/saml:Attribute", NS):
        values = [plain(v.text or "") for v in attr.findall("saml:AttributeValue", NS) if (v.text or "").strip()]
        for key in (attr.get("Name"), attr.get("FriendlyName")):
            if key:
                out.setdefault(key, []).extend(values)
    return out


def _first(attrs: dict[str, list[str]], name: str) -> list[str]:
    for key in (name, *FRIENDLY.get(name, ())):
        if attrs.get(key):
            return attrs[key]
    return []


def parse_response(cfg: SamlConfig, saml_response: str, request_id: str | None, now: datetime) -> dict[str, Any]:
    """The verified claims of a ``SAMLResponse`` (base64 of the POST form). Raises :class:`SamlError`.

    The result looks like an OIDC claim set so the shared sign-in code can use it: ``_sub``, ``_ns``, ``email``,
    ``email_verified`` (the IdP vouches for its directory), ``name``, ``groups``, plus ``_attributes``."""
    if not AVAILABLE:
        raise SamlError("unavailable", "library_required")
    try:
        raw = base64.b64decode(saml_response.encode("ascii"), validate=False)
        root = _parse(raw)
    except Exception as exc:  # noqa: BLE001 - bad base64 / XML
        raise SamlError("invalid_token", f"malformed response: {type(exc).__name__}") from exc
    if root.tag != f"{{{NS['samlp']}}}Response":
        raise SamlError("invalid_token", "not a samlp:Response")
    status = root.find("samlp:Status/samlp:StatusCode", NS)
    if status is None or status.get("Value") != SUCCESS:
        raise SamlError("denied", f"status {status.get('Value') if status is not None else 'missing'}")
    if root.find("saml:EncryptedAssertion", NS) is not None:
        raise SamlError("invalid_token", "encrypted assertions are not supported")
    dest = root.get("Destination")
    if dest and dest != cfg.acs_url:
        raise SamlError("invalid_token", "Destination is not the ACS URL")
    if request_id and root.get("InResponseTo") not in (None, request_id):
        raise SamlError("state", "InResponseTo mismatch")
    if root.find("ds:Signature", NS) is not None:
        signed = _verify(raw, cfg.certs)
        assertions = signed.findall("saml:Assertion", NS)
    else:
        found = root.findall("saml:Assertion", NS)
        if len(found) != 1 or found[0].find("ds:Signature", NS) is None:
            raise SamlError("invalid_token", "neither the response nor the assertion is signed")
        signed = _verify(etree.tostring(found[0]), cfg.certs)
        assertions = [signed] if signed.tag == f"{{{NS['saml']}}}Assertion" else []
    if len(assertions) != 1:
        raise SamlError("invalid_token", "exactly one signed assertion expected")
    a = assertions[0]
    issuer = (a.findtext("saml:Issuer", namespaces=NS) or "").strip()
    if issuer != cfg.issuer:
        raise SamlError("tenant", f"issuer {issuer[:100]}")
    t = now.replace(tzinfo=None)
    cond = a.find("saml:Conditions", NS)
    if cond is not None:
        nb, na = _time(cond.get("NotBefore")), _time(cond.get("NotOnOrAfter"))
        if (nb and t + SKEW < nb) or (na and t - SKEW >= na):
            raise SamlError("invalid_token", "assertion outside its validity window")
        audiences = [x.text.strip() for x in cond.findall(".//saml:Audience", NS) if x.text]
        if audiences and cfg.sp_entity_id not in audiences:
            raise SamlError("invalid_token", "audience is not this SP")
    else:
        raise SamlError("invalid_token", "no Conditions")
    confirmed = False
    for sc in a.findall("saml:Subject/saml:SubjectConfirmation", NS):
        if sc.get("Method") != BEARER:
            continue
        data = sc.find("saml:SubjectConfirmationData", NS)
        if data is None:
            continue
        na = _time(data.get("NotOnOrAfter"))
        if data.get("Recipient") != cfg.acs_url or (na and t - SKEW >= na):
            continue
        if request_id and data.get("InResponseTo") != request_id:
            continue
        confirmed = True
    if not confirmed:
        raise SamlError("invalid_token", "no valid bearer subject confirmation")
    attrs = _attributes(a)
    if cfg.subject_attribute:
        values = _first(attrs, cfg.subject_attribute)
        subject = values[0] if values else ""
    else:
        subject = plain(a.findtext("saml:Subject/saml:NameID", namespaces=NS) or "")
    if not subject or len(subject) > 255:
        raise SamlError("invalid_token", "no usable subject")
    emails = _first(attrs, cfg.email_attribute)
    names = _first(attrs, cfg.name_attribute)
    return {
        "iss": issuer,
        "_sub": subject,
        "_ns": cfg.tenant_id,
        "email": emails[0] if emails else None,
        "email_verified": bool(emails),
        "name": names[0] if names else None,
        "groups": _first(attrs, cfg.groups_attribute),
        "_attributes": {k: v[:20] for k, v in attrs.items()},
    }
