"""SPF / DKIM / DMARC check of the from-domain, with plain Turkish guidance (wave 3b W3-MAIL).

The resolver is pluggable (:class:`Resolver`: ``async txt(name) -> list[str]``); the default
:class:`UdpResolver` speaks DNS over UDP (TCP on truncation) to the host's resolver from ``/etc/resolv.conf`` with the
standard library only, so no new dependency. Internationalised domains (``üniversite.edu.tr``) go out as IDNA.

Each check answers ``{check, status, record, message_tr, message_en, fix_tr, fix_en}`` with ``status`` one of
``ok`` / ``warn`` / ``error`` / ``unknown`` (the lookup itself failed: no verdict).
"""

from __future__ import annotations

import asyncio
import random
import re
import socket
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services import mail_presets


class DnsError(Exception):
    """The lookup failed (timeout, SERVFAIL, no resolver): no verdict on the record."""


class Resolver(Protocol):
    async def txt(self, name: str) -> list[str]:  # [] = no such record (NXDOMAIN / NODATA)
        ...


def _servers() -> list[str]:
    try:
        text = Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [ln.split()[1] for ln in text.splitlines() if ln.strip().startswith("nameserver") and len(ln.split()) > 1]


def _qname(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("idna") if not label.isascii() else label.encode("ascii")
        if not 0 < len(raw) < 64:
            raise DnsError(f"bad DNS label in {name!r}")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _skip_name(buf: bytes, off: int) -> int:
    while True:
        if off >= len(buf):
            raise DnsError("truncated DNS answer")
        n = buf[off]
        if n == 0:
            return off + 1
        if n & 0xC0 == 0xC0:
            return off + 2
        off += 1 + n


def parse_txt_answer(buf: bytes, qid: int) -> tuple[int, bool, list[str]]:
    """(rcode, truncated, TXT strings) of a DNS response."""
    if len(buf) < 12:
        raise DnsError("short DNS answer")
    rid, flags, qd, an, _ns, _ar = struct.unpack(">HHHHHH", buf[:12])
    if rid != qid:
        raise DnsError("DNS answer id mismatch")
    rcode, tc = flags & 0x000F, bool(flags & 0x0200)
    off = 12
    for _ in range(qd):
        off = _skip_name(buf, off) + 4
    out: list[str] = []
    for _ in range(an):
        off = _skip_name(buf, off)
        rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", buf[off : off + 10])
        off += 10
        rdata = buf[off : off + rdlen]
        off += rdlen
        if rtype != 16:
            continue  # a CNAME on the way; the resolver follows it and returns the TXT too
        parts, i = [], 0
        while i < len(rdata):
            ln = rdata[i]
            parts.append(rdata[i + 1 : i + 1 + ln].decode("utf-8", errors="replace"))
            i += 1 + ln
        out.append("".join(parts))
    return rcode, tc, out


@dataclass
class UdpResolver:
    servers: list[str] | None = None
    timeout: float = 3.0

    async def txt(self, name: str) -> list[str]:
        return await asyncio.to_thread(self._query, name)

    def _query(self, name: str) -> list[str]:
        servers = self.servers or _servers() or ["1.1.1.1"]
        qid = random.randint(0, 0xFFFF)
        packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + _qname(name) + struct.pack(">HH", 16, 1)
        last: Exception | None = None
        for server in servers[:3]:
            try:
                family = socket.AF_INET6 if ":" in server else socket.AF_INET
                with socket.socket(family, socket.SOCK_DGRAM) as s:
                    s.settimeout(self.timeout)
                    s.sendto(packet, (server, 53))
                    buf, _ = s.recvfrom(4096)
                rcode, tc, out = parse_txt_answer(buf, qid)
                if tc:
                    with socket.create_connection((server, 53), timeout=self.timeout) as t:
                        t.sendall(struct.pack(">H", len(packet)) + packet)
                        size = struct.unpack(">H", _recv(t, 2))[0]
                        rcode, _tc, out = parse_txt_answer(_recv(t, size), qid)
                if rcode == 3:  # NXDOMAIN
                    return []
                if rcode != 0:
                    raise DnsError(f"DNS rcode {rcode}")
                return out
            except (OSError, DnsError, struct.error) as exc:
                last = exc
        raise DnsError(str(last) if last else "no DNS server")


def _recv(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise DnsError("DNS TCP connection closed")
        buf += chunk
    return buf


# --------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------

_DOMAIN = re.compile(r"^(?=.{1,253}$)([^\s.@/:]{1,63}\.)+[^\s.@/:]{2,63}$")


def domain_of(address: str) -> str:
    """``bildirim@Uni.edu.tr`` -> ``uni.edu.tr`` (NBSP and spaces cleaned, lower-cased, Turkish İ kept as i)."""
    text = (address or "").replace("\xa0", " ").strip()
    dom = text.rsplit("@", 1)[-1].strip().rstrip(".")
    # DNS names are case-insensitive ASCII; str.lower() would turn a Turkish İ into "i" + a combining dot
    return dom.replace("İ", "i").lower()


def _r(
    check: str, status: str, record: str | None, tr: str, en: str, fix_tr: str = "", fix_en: str = ""
) -> dict[str, Any]:
    return {
        "check": check,
        "status": status,
        "record": record,
        "message_tr": tr,
        "message_en": en,
        "fix_tr": fix_tr or None,
        "fix_en": fix_en or None,
    }


async def check_spf(resolver: Resolver, domain: str, includes: Iterable[str] = ()) -> dict[str, Any]:
    try:
        txt = await resolver.txt(domain)
    except DnsError as exc:
        return _r("spf", "unknown", None, f"SPF kaydı okunamadı ({exc}).", f"Could not read the SPF record ({exc}).")
    spf = [t for t in txt if t.lower().startswith("v=spf1")]
    if not spf:
        return _r(
            "spf",
            "error",
            None,
            f"{domain} alan adında SPF kaydı yok: alıcı sunucular iletilerinizi sahte sanabilir.",
            f"{domain} has no SPF record: receiving servers may treat your mail as forged.",
            "DNS'e bir TXT kaydı ekleyin, ör. v=spf1 include:<sağlayıcı> -all (bilgi işlem ekler).",
            "Add a TXT record such as v=spf1 include:<provider> -all (your IT department adds it).",
        )
    if len(spf) > 1:
        return _r(
            "spf",
            "error",
            " | ".join(spf),
            "Birden fazla SPF kaydı var; SPF bu durumda geçersiz sayılır.",
            "There is more than one SPF record; SPF then fails.",
            "Kayıtları tek bir v=spf1 kaydında birleştirin.",
            "Merge them into one v=spf1 record.",
        )
    rec = spf[0]
    terms = rec.lower().split()
    if "+all" in terms or "all" in terms:
        return _r(
            "spf",
            "error",
            rec,
            "SPF kaydı herkese izin veriyor (+all): kimlik doğrulaması işe yaramaz.",
            "The SPF record allows everyone (+all): it authenticates nothing.",
            "Sonu -all ya da ~all olacak şekilde düzeltin.",
            "End it with -all or ~all.",
        )
    wanted = [i.lower() for i in includes]
    if wanted and not any(f"include:{w}" in terms or f"redirect={w}" in terms for w in wanted):
        need = " ya da ".join(f"include:{w}" for w in wanted)
        need_en = " or ".join(f"include:{w}" for w in wanted)
        return _r(
            "spf",
            "warn",
            rec,
            f"SPF kaydı var ama seçtiğiniz sağlayıcıyı içermiyor ({need} bekleniyordu).",
            f"There is an SPF record but it does not include the chosen provider ({need_en} expected).",
            f"SPF kaydına {need} ekleyin.",
            f"Add {need_en} to the SPF record.",
        )
    if "?all" in terms:
        return _r(
            "spf",
            "warn",
            rec,
            "SPF kaydı var ama tarafsız (?all): sahte iletiler engellenmez.",
            "There is an SPF record but it is neutral (?all): forged mail is not stopped.",
            "Sonu ~all ya da -all olarak değiştirin.",
            "Change the end to ~all or -all.",
        )
    return _r("spf", "ok", rec, "SPF kaydı doğru görünüyor.", "The SPF record looks right.")


async def check_dkim(resolver: Resolver, domain: str, selectors: Iterable[str]) -> dict[str, Any]:
    sels = [s.strip() for s in selectors if s and s.strip()]
    if not sels:
        return _r(
            "dkim",
            "warn",
            None,
            "DKIM seçicisi bilinmiyor: sağlayıcı panelinde gösterilen seçiciyi 'DKIM seçici' alanına yazın.",
            "The DKIM selector is unknown: type the selector your provider shows into 'DKIM selector'.",
        )
    failures = 0
    for sel in sels:
        name = f"{sel}._domainkey.{domain}"
        try:
            txt = await resolver.txt(name)
        except DnsError:
            failures += 1
            continue
        rec = next((t for t in txt if "p=" in t.replace(" ", "")), None)
        if rec is not None:
            if re.search(r"(^|;)\s*p=\s*(;|$)", rec):
                return _r(
                    "dkim",
                    "error",
                    rec[:300],
                    f"DKIM anahtarı ({sel}) iptal edilmiş (boş p=).",
                    f"The DKIM key ({sel}) is revoked (empty p=).",
                    "Sağlayıcı panelinden yeni anahtarı DNS'e girin.",
                    "Enter the new key from your provider's console in DNS.",
                )
            return _r(
                "dkim", "ok", rec[:300], f"DKIM anahtarı bulundu (seçici: {sel}).", f"DKIM key found (selector: {sel})."
            )
    if failures == len(sels):
        return _r("dkim", "unknown", None, "DKIM kaydı okunamadı.", "Could not read the DKIM record.")
    return _r(
        "dkim",
        "error",
        None,
        f"DKIM kaydı bulunamadı ({', '.join(sels)} seçicileri denendi): iletiler imzasız görünür.",
        f"No DKIM record found (tried selectors {', '.join(sels)}): mail looks unsigned.",
        "Sağlayıcı panelinde DKIM'i açın ve verilen TXT/CNAME kaydını DNS'e ekleyin.",
        "Turn on DKIM in the provider console and add the TXT/CNAME record it gives to DNS.",
    )


async def check_dmarc(resolver: Resolver, domain: str) -> dict[str, Any]:
    try:
        txt = await resolver.txt(f"_dmarc.{domain}")
    except DnsError as exc:
        return _r(
            "dmarc", "unknown", None, f"DMARC kaydı okunamadı ({exc}).", f"Could not read the DMARC record ({exc})."
        )
    rec = next((t for t in txt if t.replace(" ", "").lower().startswith("v=dmarc1")), None)
    if rec is None:
        return _r(
            "dmarc",
            "error",
            None,
            "DMARC kaydı yok: Gmail ve Outlook toplu göndericilerden DMARC istiyor; iletiler spama düşebilir.",
            "No DMARC record: Gmail and Outlook require DMARC from bulk senders; mail may land in spam.",
            f"_dmarc.{domain} adına bir TXT kaydı ekleyin, ör. v=DMARC1; p=none; rua=mailto:dmarc@{domain}",
            f"Add a TXT record at _dmarc.{domain}, e.g. v=DMARC1; p=none; rua=mailto:dmarc@{domain}",
        )
    m = re.search(r"(?:^|;)\s*p\s*=\s*([a-z]+)", rec.lower())
    policy = m.group(1) if m else ""
    if policy == "none":
        return _r(
            "dmarc",
            "warn",
            rec,
            "DMARC kaydı var, politika yalnızca izleme (p=none).",
            "There is a DMARC record; the policy only monitors (p=none).",
            "Raporlar temiz görünüyorsa politikayı p=quarantine ya da p=reject yapın.",
            "Once the reports look clean, move the policy to p=quarantine or p=reject.",
        )
    if policy in ("quarantine", "reject"):
        return _r("dmarc", "ok", rec, f"DMARC kaydı doğru (p={policy}).", f"The DMARC record is right (p={policy}).")
    return _r(
        "dmarc",
        "error",
        rec,
        "DMARC kaydında geçerli bir politika (p=) yok.",
        "The DMARC record has no valid policy (p=).",
        "Kayda p=none, p=quarantine ya da p=reject ekleyin.",
        "Add p=none, p=quarantine or p=reject to the record.",
    )


_RANK = {"ok": 0, "unknown": 1, "warn": 2, "error": 3}


async def check_domain(
    domain: str, *, resolver: Resolver | None = None, preset_id: str | None = None, selector: str | None = None
) -> dict[str, Any]:
    dom = domain_of(domain)
    if not _DOMAIN.match(dom):
        raise ValueError("not a domain")
    resolver = resolver or UdpResolver()
    preset = mail_presets.get(preset_id)
    selectors = [selector] if selector else []
    selectors += list(preset.dkim_selectors if preset else ())
    checks = [
        await check_spf(resolver, dom, preset.spf_include if preset else ()),
        await check_dkim(resolver, dom, dict.fromkeys(selectors)),
        await check_dmarc(resolver, dom),
    ]
    worst = max(checks, key=lambda c: _RANK[c["status"]])["status"]
    return {"domain": dom, "status": worst, "checks": checks}
