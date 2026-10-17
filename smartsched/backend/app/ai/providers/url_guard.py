"""SSRF guard for AI provider base URLs (security follow-up wave3-sec2, docs/SECURITY.md R12).

An administrator types a provider's base URL; the backend then sends requests (with the provider key) there. Without
a guard that URL could name the cloud metadata service, a link-local address or a service on the compose network
(the database, Grafana, the backend's own ``/metrics``). Rules:

* ``https`` only, no user name or password in the URL;
* every address the host name resolves to must be public (``is_global``);
* link-local (169.254.0.0/16, fe80::/10), unspecified, multicast and reserved addresses and the known cloud metadata
  addresses are always refused;
* a **local** OpenAI-compatible server (Ollama, vLLM, LM Studio on loopback or a private network) is allowed only
  with the explicit ``allow_local`` opt-in of that provider; then ``http`` is accepted for a local address. The
  admin page shows the opt-in as a warning.

:func:`check_base_url` runs when the URL is saved (``resolve=False``: literals and ``localhost`` only) and before
every real request (after DNS resolution, in the adapters). Residual risk: the HTTP client resolves the name again
(DNS rebinding between the check and the connection); the window is short and the provider key is the only thing
sent.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.ai.providers.base import ProviderError

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], list[str]]

#: cloud metadata services outside the link-local range (AWS IPv6 IMDS, Azure wire server, Alibaba Cloud)
METADATA = frozenset(
    ipaddress.ip_address(a) for a in ("fd00:ec2::254", "168.63.129.16", "100.100.100.200", "169.254.169.254")
)
_LOCAL_NAMES = ("localhost", ".localhost", ".local", ".internal", ".lan", ".home.arpa")

_TEXTS: dict[str, tuple[str, str]] = {
    "invalid_url": ("Adres geçerli bir URL değil.", "The address is not a valid URL."),
    "https_required": (
        "Sağlayıcı adresi https:// ile başlamalı.",
        "The provider address must start with https://.",
    ),
    "credentials_in_url": (
        "Adres kullanıcı adı ya da parola içeremez; anahtarı anahtar alanına girin.",
        "The address cannot carry a user name or password; put the key in the key field.",
    ),
    "blocked_address": (
        "Bu adres bulut meta veri servisine ya da yerel bağlantı adresine gidiyor; izin verilmez.",
        "This address points at a cloud metadata service or a link-local address and is not allowed.",
    ),
    "local_address": (
        "Bu adres kurum içi ya da yerel bir sunucuya gidiyor. Yerel bir OpenAI uyumlu sunucu (Ollama, vLLM) "
        "kullanıyorsanız 'Yerel sunucuya izin ver' seçeneğini açın.",
        "This address points at a private or local server. For a local OpenAI-compatible server (Ollama, vLLM), "
        "turn on 'Allow a local server'.",
    ),
    "unresolvable": (
        "Sağlayıcı adresi çözümlenemedi.",
        "The provider address could not be resolved.",
    ),
}


class UnsafeBaseURL(ProviderError):
    """A refused base URL; ``code`` is one of :data:`_TEXTS` and the message is shown to the administrator."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.message_tr, self.message_en = _TEXTS[code]
        super().__init__(f"unsafe provider URL ({code}): {self.message_en}")


@dataclass(frozen=True)
class Verdict:
    #: the URL points at a local / private server (allowed only with the opt-in)
    local: bool


def _resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def _parse_ip(value: str) -> IPAddress | None:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _classify(ip: IPAddress) -> str:
    """``blocked`` | ``local`` | ``public``."""
    if ip in METADATA or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        return "blocked"
    if ip.is_loopback or ip.is_private:
        return "local"
    if ip.is_reserved or (
        isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour is not None and not ip.sixtofour.is_global
    ):
        return "blocked"
    if ip.is_global:
        return "public"
    return "local"  # loopback, private, carrier-grade NAT, unique local


def check_base_url(
    url: str | None, *, allow_local: bool = False, resolve: bool = True, resolver: Resolver | None = None
) -> Verdict:
    """Raise :class:`UnsafeBaseURL` unless ``url`` is a safe provider target; returns whether it is local."""
    try:
        parts = urlsplit((url or "").strip())
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeBaseURL("invalid_url") from exc
    if parts.scheme not in {"http", "https"}:
        raise UnsafeBaseURL("https_required")
    if not host:
        raise UnsafeBaseURL("invalid_url")
    if parts.username is not None or parts.password is not None:
        raise UnsafeBaseURL("credentials_in_url")

    literal = _parse_ip(host)
    addresses: list[IPAddress] | None
    if literal is not None:
        addresses = [literal]
    elif host == "localhost" or host.endswith(_LOCAL_NAMES):
        addresses = None if resolve else [ipaddress.ip_address("127.0.0.1")]
    else:
        addresses = None
    if addresses is None and resolve:
        try:
            found = (resolver or _resolve)(host, port)
        except (OSError, UnicodeError) as exc:
            raise UnsafeBaseURL("unresolvable") from exc
        addresses = [ip for ip in (_parse_ip(a) for a in found) if ip is not None]
        if not addresses:
            raise UnsafeBaseURL("unresolvable")

    kinds = {_classify(ip) for ip in addresses or []}
    if "blocked" in kinds:
        raise UnsafeBaseURL("blocked_address")
    local = "local" in kinds
    if local and not allow_local:
        raise UnsafeBaseURL("local_address")
    if parts.scheme != "https":
        # plain http only for a local server the administrator opted in to (unknown at save time: the call decides)
        if not allow_local or (addresses is not None and not local):
            raise UnsafeBaseURL("https_required")
    return Verdict(local=local)


async def ensure_safe(url: str, *, allow_local: bool) -> None:
    """The call-time check (DNS resolution off the event loop)."""
    import asyncio

    await asyncio.to_thread(check_base_url, url, allow_local=allow_local)


__all__ = ["METADATA", "UnsafeBaseURL", "Verdict", "check_base_url", "ensure_safe"]
