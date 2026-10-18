"""W3-OPS: ``/grafana/`` on the deployed proxy. The locations in ``observability/nginx/grafana.locations`` are pasted
into ``nginx/default.conf`` before ``location / {``: admin-only through ``auth_request`` to the backend's
``/api/v1/ops/grafana-auth`` (204 admin, 401 → /login, 403 others), the client's X-WEBAUTH-USER always overwritten.
This keeps the pasted copy identical to its source, so a change in one cannot silently miss the other."""

from __future__ import annotations

import re

from podfakes import REPO

DEPLOY = REPO / "smartsched/deploy"


def _block() -> str:
    return (DEPLOY / "observability/nginx/grafana.locations").read_text(encoding="utf-8").strip()


def test_default_conf_carries_the_grafana_locations_verbatim_before_the_catch_all() -> None:
    conf = (DEPLOY / "nginx/default.conf").read_text(encoding="utf-8")
    block = _block()
    assert conf.count(block) == 1, "nginx/default.conf must carry observability/nginx/grafana.locations once, verbatim"
    assert conf.index(block) < conf.index("    location / {")


def test_grafana_is_admin_only_and_never_trusts_the_client_identity_header() -> None:
    block = _block()
    loc = re.search(r"location /grafana/ \{(.*?)\n    \}", block, re.S)
    assert loc, "location /grafana/ missing"
    body = loc.group(1)
    assert "auth_request /_ops/grafana-auth;" in body
    assert "error_page 401 = @grafana_login;" in body
    assert "proxy_set_header X-WEBAUTH-USER    smartsched-admin;" in body
    assert 'proxy_set_header Authorization     "";' in body
    auth = re.search(r"location = /_ops/grafana-auth \{(.*?)\n    \}", block, re.S)
    assert auth and "internal;" in auth.group(1)
    assert "proxy_pass http://smartsched_frontend/api/v1/ops/grafana-auth;" in auth.group(1)
    assert "return 302 /login?next=$request_uri;" in block


def test_compose_grafana_serves_the_sub_path_with_auth_proxy() -> None:
    compose = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    for line in (
        'GF_SERVER_ROOT_URL: "%(protocol)s://%(domain)s/grafana/"',
        'GF_SERVER_SERVE_FROM_SUB_PATH: "true"',
        'GF_AUTH_PROXY_ENABLED: "true"',
        "GF_AUTH_PROXY_HEADER_NAME: X-WEBAUTH-USER",
    ):
        assert line in compose, line
