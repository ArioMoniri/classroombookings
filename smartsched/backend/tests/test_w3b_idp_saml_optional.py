"""SAML without the optional signxml library (wave 3b W3-IDP): the gallery says "kütüphane gerekli", metadata is not
read and the provider cannot be enabled. Runs with and without the ``saml`` extra installed."""

from __future__ import annotations

from app.services.identity import saml as idp_saml

from tests.test_w3b_idp_fakes import idp  # noqa: F401

METADATA = """<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.uni.edu.tr/idp/shibboleth"/>"""
IDP_ENTITY = "https://idp.uni.edu.tr/idp/shibboleth"


def federation_metadata() -> bytes:
    return METADATA.encode()


async def test_without_the_library_saml_cannot_be_enabled(idp, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(idp_saml, "AVAILABLE", False)
    kinds = {k["kind"]: k for k in (await idp.client.get("/api/v1/auth/sso/admin/kinds", headers=idp.admin)).json()}
    assert kinds["saml"]["library_required"] is True
    p = await idp.create("saml", preset="shibboleth")
    assert p["library_required"] is True
    r = await idp.put(p["id"], metadata_xml=federation_metadata().decode(), idp_entity_id=IDP_ENTITY)
    lib = next(c for c in r.json()["discovery"]["checks"] if c["key"] == "library")
    assert lib["ok"] is False and "Kütüphane gerekli" in lib["tr"]
    r = await idp.put(p["id"], enabled=True)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "library_required"
