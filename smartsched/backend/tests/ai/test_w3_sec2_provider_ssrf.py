"""Security follow-up (wave3-sec2, docs/SECURITY.md R12): SSRF guard on the AI provider base URLs.

A provider base URL is an outbound request target an administrator types in. It must be https and resolve only to
public addresses, so the backend cannot be pointed at the cloud metadata service, a link-local address or the
compose network (the database, Grafana, the backend's own /metrics). A local OpenAI-compatible server (Ollama, vLLM)
is allowed only with the explicit ``allow_local`` opt-in on that provider, shown as a warning; link-local and
metadata addresses stay refused even then. The check runs when the URL is saved (no DNS) and before every real
request (after DNS resolution).
"""

from __future__ import annotations

import pytest
from app.ai.providers import make_adapter, url_guard
from app.ai.providers.gemini import GeminiAdapter
from app.ai.providers.openai_compat import OpenAICompatAdapter
from app.ai.providers.url_guard import UnsafeBaseURL, check_base_url

from tests.api_fixtures import client, login  # noqa: F401


def _dns(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


PUBLIC = _dns(
    {
        "api.openai.com": ["162.159.140.245"],
        "rebind.example.com": ["93.184.215.14", "10.0.0.7"],  # one private answer is enough to refuse
        "metadata.google.internal": ["169.254.169.254"],
        "ollama.lan": ["192.168.1.20"],
        "v6meta.example.com": ["fd00:ec2::254"],
    }
)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://api.openai.com/v1", "https_required"),
        ("ftp://api.openai.com/v1", "https_required"),
        ("https://169.254.169.254/latest/meta-data", "blocked_address"),
        ("https://metadata.google.internal/computeMetadata/v1", "blocked_address"),
        ("https://[fe80::1]/v1", "blocked_address"),
        ("https://[::ffff:169.254.169.254]/v1", "blocked_address"),
        ("https://v6meta.example.com/v1", "blocked_address"),
        ("https://168.63.129.16/v1", "blocked_address"),  # Azure wire server: a public-range metadata address
        ("https://100.100.100.200/v1", "blocked_address"),  # Alibaba Cloud metadata
        ("https://0.0.0.0/v1", "blocked_address"),
        ("https://127.0.0.1:11434/v1", "local_address"),
        ("https://10.1.2.3/v1", "local_address"),
        ("https://172.18.0.3:8000/v1", "local_address"),  # the compose network (backend, db, grafana)
        ("https://[::1]/v1", "local_address"),
        ("https://100.64.0.9/v1", "local_address"),  # carrier-grade NAT, not public
        ("https://rebind.example.com/v1", "local_address"),
        ("https://ollama.lan/v1", "local_address"),
        ("https://unknown.invalid/v1", "unresolvable"),
        ("https://user:pw@api.openai.com/v1", "credentials_in_url"),
        ("https:///v1", "invalid_url"),
    ],
)
def test_unsafe_targets_are_refused(url: str, code: str) -> None:
    with pytest.raises(UnsafeBaseURL) as e:
        check_base_url(url, resolver=PUBLIC)
    assert e.value.code == code
    assert e.value.message_tr and e.value.message_en


def test_a_public_https_url_passes() -> None:
    assert check_base_url("https://api.openai.com/v1", resolver=PUBLIC).local is False


def test_the_local_opt_in_allows_a_local_server_but_never_metadata() -> None:
    for url in ("http://127.0.0.1:11434/v1", "http://ollama.lan:11434/v1", "https://10.1.2.3/v1"):
        assert check_base_url(url, allow_local=True, resolver=PUBLIC).local is True
    for url in ("http://169.254.169.254/latest", "http://metadata.google.internal/", "http://[fe80::1]/"):
        with pytest.raises(UnsafeBaseURL) as e:
            check_base_url(url, allow_local=True, resolver=PUBLIC)
        assert e.value.code == "blocked_address"
    # the opt-in is for local servers: a public host still needs https
    with pytest.raises(UnsafeBaseURL) as e:
        check_base_url("http://api.openai.com/v1", allow_local=True, resolver=PUBLIC)
    assert e.value.code == "https_required"


def test_saving_checks_without_dns() -> None:
    # unknown names pass the save-time check (the call-time check resolves them); literals and localhost do not
    assert check_base_url("https://vllm.example.edu.tr/v1", resolve=False).local is False
    for url in ("https://localhost:11434/v1", "https://gpu.localhost/v1", "https://10.0.0.5/v1"):
        with pytest.raises(UnsafeBaseURL):
            check_base_url(url, resolve=False)
    with pytest.raises(UnsafeBaseURL):
        check_base_url("https://169.254.169.254/", resolve=False, allow_local=True)


async def test_adapters_check_the_resolved_address_before_any_request(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(url_guard, "_resolve", PUBLIC)
    a = OpenAICompatAdapter("azure_openai", api_key="k", base_url="https://metadata.google.internal/openai/v1")
    with pytest.raises(UnsafeBaseURL):
        await a.list_models()
    g = GeminiAdapter(api_key="k", base_url="https://rebind.example.com/v1beta")
    with pytest.raises(UnsafeBaseURL):
        await g.list_models()
    # the default local Ollama URL needs the opt-in
    local = make_adapter("openai_compatible", model="llama3.1", secrets={}, config={})
    with pytest.raises(UnsafeBaseURL) as e:
        await local.list_models()
    assert e.value.code == "local_address"
    # with it, the guard lets the request go (the connection itself then fails: nothing listens there)
    opted = make_adapter(
        "openai_compatible", model="llama3.1", secrets={}, config={"base_url": "http://127.0.0.1:9/v1", "allow_local": True}
    )
    with pytest.raises(Exception) as e2:
        await opted.list_models()
    assert not isinstance(e2.value, UnsafeBaseURL)
    # the opt-in belongs to the OpenAI-compatible provider only
    other = make_adapter(
        "openai", model="gpt", secrets={"api_key": "k"}, config={"base_url": "http://127.0.0.1:9/v1", "allow_local": True}
    )
    with pytest.raises(UnsafeBaseURL):
        await other.list_models()


async def test_admin_api_refuses_unsafe_urls_and_warns_on_the_local_opt_in(client):  # type: ignore[no-untyped-def]  # noqa: F811
    h = await login(client)
    for url in ("https://169.254.169.254/latest", "http://api.openai.com/v1", "https://10.0.0.5/v1"):
        r = await client.put("/api/v1/ai/admin/providers/openai", json={"base_url": url}, headers=h)
        assert r.status_code == 422, (url, r.text)
        detail = r.json()["detail"]
        assert detail["code"] == "unsafe_url" and detail["field"] == "base_url"
        assert detail["message_tr"] and detail["message_en"]
    # a local server without the opt-in is refused, with it saved and flagged
    r = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible", json={"base_url": "http://127.0.0.1:11434/v1"}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "local_address"
    r = await client.put(
        "/api/v1/ai/admin/providers/openai_compatible",
        json={"base_url": "http://127.0.0.1:11434/v1", "allow_local": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["allow_local"] is True and out["local"] is True
    [w] = out["warnings"]
    assert w["code"] == "local_url_opt_in" and "yerel" in w["message_tr"].lower()
    # the opt-in exists only on the OpenAI-compatible provider
    r = await client.put("/api/v1/ai/admin/providers/openai", json={"allow_local": True}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unknown_field"
    # a public provider has no warning
    listing = (await client.get("/api/v1/ai/admin/providers", headers=h)).json()["providers"]
    assert next(p for p in listing if p["id"] == "openai")["warnings"] == []
