"""W3-MAIL: SPF / DKIM / DMARC of the from-domain with a fake resolver, the DNS packet parser and the API route."""

from __future__ import annotations

import struct

import pytest
from app.services import mail_dns

from tests.api_fixtures import client, login  # noqa: F401


class FakeResolver:
    def __init__(self, records: dict[str, list[str]], broken: set[str] | None = None) -> None:
        self.records, self.broken, self.asked = records, broken or set(), []

    async def txt(self, name: str) -> list[str]:
        self.asked.append(name)
        if name in self.broken:
            raise mail_dns.DnsError("timeout")
        return self.records.get(name, [])


GOOD = {
    "uni.edu.tr": ["google-site-verification=abc", "v=spf1 include:spf.protection.outlook.com -all"],
    "selector1._domainkey.uni.edu.tr": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqh"],
    "_dmarc.uni.edu.tr": ["v=DMARC1; p=quarantine; rua=mailto:dmarc@uni.edu.tr"],
}


async def test_a_well_configured_microsoft_domain_passes() -> None:
    res = await mail_dns.check_domain(
        "Bildirim@Uni.edu.tr", resolver=FakeResolver(GOOD), preset_id="microsoft365_oauth2"
    )
    assert res["domain"] == "uni.edu.tr" and res["status"] == "ok"
    assert [c["status"] for c in res["checks"]] == ["ok", "ok", "ok"]
    assert "seçici: selector1" in res["checks"][1]["message_tr"]


async def test_missing_records_give_plain_turkish_fixes() -> None:
    res = await mail_dns.check_domain("bildirim@uni.edu.tr", resolver=FakeResolver({}), preset_id="google_app_password")
    spf, dkim, dmarc = res["checks"]
    assert res["status"] == "error"
    assert spf["status"] == "error" and "SPF kaydı yok" in spf["message_tr"] and "v=spf1" in spf["fix_tr"]
    assert dkim["status"] == "error" and "google" in dkim["message_tr"]
    assert dmarc["status"] == "error" and "_dmarc.uni.edu.tr" in dmarc["fix_tr"]


@pytest.mark.parametrize(
    ("record", "status", "words"),
    [
        ("v=spf1 include:_spf.google.com ~all", "warn", "spf.protection.outlook.com"),  # wrong provider
        ("v=spf1 +all", "error", "+all"),
        ("v=spf1 include:spf.protection.outlook.com ?all", "warn", "?all"),
    ],
)
async def test_spf_verdicts(record: str, status: str, words: str) -> None:
    r = await mail_dns.check_spf(FakeResolver({"uni.edu.tr": [record]}), "uni.edu.tr", ["spf.protection.outlook.com"])
    assert r["status"] == status and words in (r["message_tr"] + (r["fix_tr"] or ""))


async def test_two_spf_records_fail() -> None:
    r = await mail_dns.check_spf(FakeResolver({"uni.edu.tr": ["v=spf1 -all", "v=spf1 mx -all"]}), "uni.edu.tr")
    assert r["status"] == "error" and "Birden fazla" in r["message_tr"]


async def test_dmarc_none_is_a_warning_and_revoked_dkim_an_error() -> None:
    dm = await mail_dns.check_dmarc(FakeResolver({"_dmarc.uni.edu.tr": ["v=DMARC1; p=none"]}), "uni.edu.tr")
    assert dm["status"] == "warn" and "p=quarantine" in dm["fix_tr"]
    dk = await mail_dns.check_dkim(FakeResolver({"s1._domainkey.uni.edu.tr": ["v=DKIM1; p="]}), "uni.edu.tr", ["s1"])
    assert dk["status"] == "error" and "iptal" in dk["message_tr"]
    none = await mail_dns.check_dkim(FakeResolver({}), "uni.edu.tr", [])
    assert none["status"] == "warn" and "seçici" in none["message_tr"]


async def test_lookup_failures_are_unknown_not_errors() -> None:
    res = await mail_dns.check_domain(
        "uni.edu.tr",
        resolver=FakeResolver({}, broken={"uni.edu.tr", "_dmarc.uni.edu.tr", "google._domainkey.uni.edu.tr"}),
        preset_id="google_app_password",
    )
    assert [c["status"] for c in res["checks"]] == ["unknown", "unknown", "unknown"]


async def test_turkish_domains_go_out_as_idna() -> None:
    assert mail_dns.domain_of("Bildirim@ÜNİVERSİTE.edu.tr") == "üniversite.edu.tr"
    assert mail_dns._qname("üniversite.edu.tr").startswith(b"\x11xn--niversite-")
    with pytest.raises(ValueError):
        await mail_dns.check_domain("not a domain", resolver=FakeResolver({}))


def _answer(qid: int, txts: list[bytes], rcode: int = 0) -> bytes:
    q = mail_dns._qname("uni.edu.tr") + struct.pack(">HH", 16, 1)
    head = struct.pack(">HHHHHH", qid, 0x8180 | rcode, 1, len(txts), 0, 0)
    body = b""
    for t in txts:
        rdata = b"".join(bytes([len(t[i : i + 255])]) + t[i : i + 255] for i in range(0, len(t), 255))
        body += b"\xc0\x0c" + struct.pack(">HHIH", 16, 1, 300, len(rdata)) + rdata
    return head + q + body


def test_txt_parser_joins_long_strings_and_reads_nxdomain() -> None:
    long = b"v=DKIM1; k=rsa; p=" + b"A" * 400
    rcode, tc, out = mail_dns.parse_txt_answer(_answer(7, [long, b"v=spf1 -all"]), 7)
    assert rcode == 0 and not tc and out == [long.decode(), "v=spf1 -all"]
    assert mail_dns.parse_txt_answer(_answer(9, [], rcode=3), 9)[0] == 3
    with pytest.raises(mail_dns.DnsError):
        mail_dns.parse_txt_answer(_answer(1, []), 2)


async def test_api_checks_the_saved_from_domain(client, monkeypatch) -> None:  # noqa: F811
    from app.api.v1 import mail_admin

    fake = FakeResolver(GOOD)
    monkeypatch.setattr(mail_admin, "resolver", lambda: fake)
    h = await login(client)
    assert (await client.post("/api/v1/mail/dns-check", json={}, headers=h)).status_code == 422
    await client.put(
        "/api/v1/mail/settings",
        json={"provider": "microsoft365_oauth2", "host": "smtp.office365.com", "from_address": "bildirim@uni.edu.tr"},
        headers=h,
    )
    r = await client.post("/api/v1/mail/dns-check", json={}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    assert "selector1._domainkey.uni.edu.tr" in fake.asked
    r = await client.post("/api/v1/mail/dns-check", json={"domain": "ornek.edu.tr", "selector": "s1"}, headers=h)
    assert r.json()["domain"] == "ornek.edu.tr" and "s1._domainkey.ornek.edu.tr" in fake.asked
    bad = await client.post("/api/v1/mail/dns-check", json={"selector": "bad selector!"}, headers=h)
    assert bad.status_code == 422
