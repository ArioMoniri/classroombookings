"""A tiny OpenID Connect issuer for the W3-IDP e2e run (port 19712; Keycloak-shaped ``/realms/uni``).

    ../backend/.venv/bin/python -I e2e/w3-idp-mock-issuer.py 19712

Discovery, JWKS, an authorize endpoint that signs the person in at once (the ``login_hint`` or
``ayse.yilmaz@uni.edu.tr``) and redirects back with a code, and a token endpoint that checks the code, PKCE S256, the
redirect URI and the client secret (``client_secret_basic`` or ``_post``). Made-up client values; test use only."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from joserfc import jwt
from joserfc.jwk import RSAKey

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 19712
ISSUER = f"http://localhost:{PORT}/realms/uni"
CLIENT_ID, CLIENT_SECRET = "smartsched-e2e", "e2e-fake-secret"
#: a new key id per process: the backend caches the JWKS per key id (a restarted mock is a key rotation)
KID = "e2e-" + secrets.token_hex(4)
KEY = RSAKey.generate_key(2048, parameters={"kid": KID, "use": "sig", "alg": "RS256"}, private=True)
CODES: dict[str, dict[str, str]] = {}


def s256(v: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # quiet
        return

    def _json(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/realms/uni/.well-known/openid-configuration":
            return self._json(
                200,
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
                    "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
                    "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
                    "response_types_supported": ["code"],
                    "code_challenge_methods_supported": ["S256"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                },
            )
        if url.path == "/realms/uni/protocol/openid-connect/certs":
            return self._json(200, {"keys": [KEY.as_dict(private=False)]})
        if url.path == "/realms/uni/protocol/openid-connect/auth":
            code = secrets.token_urlsafe(16)
            CODES[code] = {
                "challenge": q.get("code_challenge", ""),
                "nonce": q.get("nonce", ""),
                "redirect_uri": q.get("redirect_uri", ""),
                "email": q.get("login_hint") or "ayse.yilmaz@uni.edu.tr",
            }
            self.send_response(302)
            self.send_header("Location", f"{q.get('redirect_uri')}?{urlencode({'code': code, 'state': q.get('state', '')})}")
            self.end_headers()
            return None
        return self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            cid, _, sec = base64.b64decode(auth[6:]).decode().partition(":")
        else:
            cid, sec = form.get("client_id", ""), form.get("client_secret", "")
        grant = CODES.pop(form.get("code", ""), None)
        if (
            grant is None
            or cid != CLIENT_ID
            or sec != CLIENT_SECRET
            or form.get("redirect_uri") != grant["redirect_uri"]
            or s256(form.get("code_verifier", "")) != grant["challenge"]
        ):
            return self._json(400, {"error": "invalid_grant"})
        now = int(time.time())
        email = grant["email"]
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "kc-" + hashlib.sha256(email.encode()).hexdigest()[:16],
            "nonce": grant["nonce"],
            "iat": now,
            "exp": now + 300,
            "email": email,
            "email_verified": True,
            "name": "Ayşe Yılmaz",
            "groups": ["/personel/planlama"],
        }
        token = jwt.encode({"alg": "RS256", "kid": KID, "typ": "JWT"}, claims, KEY)
        return self._json(200, {"access_token": "e2e-access", "id_token": token, "token_type": "Bearer"})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
