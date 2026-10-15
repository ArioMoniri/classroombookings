"""Admin persona 2026-10-15 M-41: webhook URLs must not reach the server's own network.

Refused at save time (``POST`` / ``PUT /webhooks``, literal addresses, ``localhost`` names and every address the
host name resolves to) and again at send time (DNS is resolved again and every address is checked, so a name
that later rebinds to 127.0.0.1 is still refused); the delivery client itself refuses to open a connection to a
blocked address, so the window between the check and the connect is closed too.

One test per class: loopback, private RFC 1918, link-local, CGNAT, unique-local IPv6, ``localhost`` names and
non-http(s) schemes. Runs on the real Bahar 2026 import (``tests/crbs_env``); the loopback URL is the persona's
exact repro (``EV/curl/webhooks-calsync.txt`` WH-4).
"""

from __future__ import annotations

import asyncio

import httpcore
import httpx
import pytest
from app.services import webhooks
from app.workers import integrations as worker

from tests.crbs_env import env  # noqa: F401
from tests.integrations_support import Receiver, client_factory

HOOK = "https://otomasyon.uni.edu.tr/api/v1/webhooks/ap-flow-1"
PUBLIC = "203.0.113.10"  # TEST-NET-3: never a real lookup in tests

#: class -> (literal URLs refused at save time, an address a host name may resolve to)
CLASSES: dict[str, tuple[tuple[str, ...], str]] = {
    "loopback": (
        (
            "http://127.0.0.1:18951/",  # persona repro WH-4
            "http://127.8.9.10/x",
            "http://[::1]/x",
            "http://[::ffff:127.0.0.1]/x",  # IPv4-mapped
            "http://2130706433/x",  # 127.0.0.1 as one integer (inet_aton forms)
            "http://127.1/x",
            "http://0x7f.0.0.1/x",
            "http://0.0.0.0/x",
        ),
        "127.0.0.1",
    ),
    "private_rfc1918": (
        ("http://10.0.4.12/x", "http://172.16.5.4/x", "http://172.31.255.1/x", "https://192.168.1.10/x"),
        "192.168.10.20",
    ),
    "link_local": (("http://169.254.10.1/x", "http://169.254.169.254/latest/meta-data/", "http://[fe80::1]/x"), "169.254.1.1"),
    "cgnat": (("http://100.64.0.1/x", "http://100.127.255.254/x"), "100.100.100.200"),
    "unique_local_ipv6": (("http://[fd12:3456:789a::1]/x", "http://[fc00::5]/x", "http://[fd00:ec2::254]/x"), "fd00::1"),
    "localhost_names": (
        (
            "http://localhost:8000/x",
            "http://LOCALHOST./x",
            "http://api.localhost/x",
            "http://localhost.localdomain/x",
            "http://ip6-localhost/x",
            " http://localhost/x ",  # NBSP pasted around the URL
        ),
        "",
    ),
    "non_http_scheme": (
        ("ftp://hooks.uni.edu.tr/x", "file:///etc/passwd", "gopher://hooks.uni.edu.tr/x", "javascript:alert(1)"),
        "",
    ),
}


@pytest.fixture
def receiver(monkeypatch) -> Receiver:
    rec = Receiver()
    monkeypatch.setattr(webhooks, "http_client", client_factory(rec))

    async def public_dns(host: str) -> list[str]:
        return [PUBLIC]

    monkeypatch.setattr(webhooks, "resolve_host", public_dns)
    return rec


@pytest.fixture(autouse=True)
async def _stop_worker():
    yield
    await worker.wait_idle()
    await worker.shutdown()


def _dns(monkeypatch, *addresses: str) -> None:
    async def fake(host: str) -> list[str]:
        return list(addresses)

    monkeypatch.setattr(webhooks, "resolve_host", fake)


async def _post(env, url: str):  # noqa: F811
    return await env.client.post("/api/v1/webhooks", json={"url": url, "events": ["*"]}, headers=env.admin)


@pytest.mark.parametrize("cls", sorted(CLASSES))
async def test_literal_targets_are_refused_at_save_time(env, receiver, cls):  # noqa: F811
    for url in CLASSES[cls][0]:
        r = await _post(env, url)
        assert r.status_code == 422, (cls, url, r.text)
    assert (await env.client.get("/api/v1/webhooks", headers=env.admin)).json() == []


@pytest.mark.parametrize("cls", sorted(c for c, (_, ip) in CLASSES.items() if ip))
async def test_host_names_resolving_to_a_blocked_address_are_refused_at_save_time(env, receiver, monkeypatch, cls):  # noqa: F811
    ok = await _post(env, HOOK)
    assert ok.status_code == 201, ok.text
    _dns(monkeypatch, PUBLIC, CLASSES[cls][1])  # every address counts, not only the first
    r = await _post(env, "https://hooks.uni.edu.tr/x")
    assert r.status_code == 422, r.text
    assert "address" in r.text
    r = await env.client.put(f"/api/v1/webhooks/{ok.json()['id']}", json={"url": HOOK}, headers=env.admin)
    assert r.status_code == 422, r.text
    stored = (await env.client.get(f"/api/v1/webhooks/{ok.json()['id']}", headers=env.admin)).json()
    assert stored["url"] == HOOK


@pytest.mark.parametrize("cls", sorted(c for c, (_, ip) in CLASSES.items() if ip))
async def test_dns_rebinding_is_refused_at_send_time(env, receiver, monkeypatch, cls):  # noqa: F811
    hook = (await _post(env, HOOK)).json()
    _dns(monkeypatch, PUBLIC, CLASSES[cls][1])  # the name rebinds after it was saved
    await env.client.post(f"/api/v1/webhooks/{hook['id']}/test", headers=env.admin)
    await worker.wait_idle()
    [d] = (await env.client.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert d["status"] == "FAILED" and "blocked address" in d["last_error"], d
    assert receiver.received == []


async def test_a_public_host_is_still_delivered(env, receiver):  # noqa: F811
    hook = (await _post(env, HOOK)).json()
    await env.client.post(f"/api/v1/webhooks/{hook['id']}/test", headers=env.admin)
    await worker.wait_idle()
    [d] = (await env.client.get(f"/api/v1/webhooks/{hook['id']}/deliveries", headers=env.admin)).json()
    assert d["status"] == "SENT" and len(receiver.received) == 1


async def test_the_delivery_client_never_connects_to_a_blocked_address(monkeypatch):
    """The window between the send-time check and the connect: the real client resolves and checks again
    inside ``connect_tcp``, so a listener on 127.0.0.1 is never reached, whatever the URL says."""
    hits: list[bytes] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hits.append(await reader.read(100))
        writer.write(b"HTTP/1.1 200 OK\r\ncontent-length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 18980)
    try:
        async with webhooks.http_client() as client:
            with pytest.raises(httpx.ConnectError):
                await client.post("http://127.0.0.1:18980/", content=b"{}")
            _dns(monkeypatch, "127.0.0.1")  # a public-looking name that resolves to loopback
            with pytest.raises(httpx.ConnectError):
                await client.post("http://rebind.uni.edu.tr:18980/", content=b"{}")
        backend = webhooks.GuardedBackend()
        with pytest.raises(httpcore.ConnectError):
            await backend.connect_tcp("rebind.uni.edu.tr", 18980)
        _dns(monkeypatch)  # does not resolve
        with pytest.raises(httpcore.ConnectError):
            await backend.connect_tcp("yok.uni.edu.tr", 18980)
    finally:
        server.close()
        await server.wait_closed()
    assert hits == []


def test_blocked_address_classes():
    for cls, (_, ip) in CLASSES.items():
        if ip:
            assert webhooks.blocked_address(ip), cls
    for ok in (PUBLIC, "8.8.8.8", "2001:4860:4860::8888", "100.128.0.1", "172.32.0.1", "11.0.0.1"):
        assert not webhooks.blocked_address(ok), ok
