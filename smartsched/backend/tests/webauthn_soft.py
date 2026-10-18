"""A software WebAuthn authenticator for the AU-B tests (no browser): builds the JSON a browser returns from
``navigator.credentials.create()`` (attestation ``none``) and ``navigator.credentials.get()``, with a real P-256 key,
so the server runs py_webauthn's full verification (challenge, origin, RP ID hash, flags, signature, counter).

    auth = SoftAuthenticator("plan.uni.edu.tr", "https://plan.uni.edu.tr")
    reg = auth.register(options_json)            # dict for /auth/passkeys/register/verify
    assertion = auth.assert_(options_json)       # dict for /auth/passkey(s)/verify
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP, FLAG_UV, FLAG_BE, FLAG_BS, FLAG_AT = 0x01, 0x04, 0x08, 0x10, 0x40


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class SoftAuthenticator:
    rp_id: str
    origin: str
    user_verification: bool = True
    synced: bool = False
    #: hardware keys count up; synced passkeys always send 0
    counter: int = 0
    credential_id: bytes = field(default_factory=lambda: os.urandom(32))
    key: ec.EllipticCurvePrivateKey = field(default_factory=lambda: ec.generate_private_key(ec.SECP256R1()))
    user_handle: bytes | None = None

    def _flags(self, extra: int = 0) -> int:
        f = FLAG_UP | extra
        if self.user_verification:
            f |= FLAG_UV
        if self.synced:
            f |= FLAG_BE | FLAG_BS
        return f

    def _cose(self) -> bytes:
        nums = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})

    def _client_data(self, kind: str, challenge: str, origin: str | None = None) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin or self.origin, "crossOrigin": False},
            separators=(",", ":"),
        ).encode()

    def register(
        self, options: dict[str, Any], *, origin: str | None = None, rp_id: str | None = None
    ) -> dict[str, Any]:
        public = options.get("publicKey", options)
        self.user_handle = unb64u(public["user"]["id"])
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode()).digest()
        attested = bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose()
        auth_data = rp_hash + bytes([self._flags(FLAG_AT)]) + struct.pack(">I", self.counter) + attested
        att_obj = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cdj = self._client_data("webauthn.create", public["challenge"], origin)
        return {
            "id": b64u(self.credential_id),
            "rawId": b64u(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64u(cdj),
                "attestationObject": b64u(att_obj),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def assert_(
        self, options: dict[str, Any], *, origin: str | None = None, counter: int | None = None
    ) -> dict[str, Any]:
        public = options.get("publicKey", options)
        if counter is not None:
            self.counter = counter
        elif self.counter:
            self.counter += 1
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = rp_hash + bytes([self._flags()]) + struct.pack(">I", self.counter)
        cdj = self._client_data("webauthn.get", public["challenge"], origin)
        sig = self.key.sign(auth_data + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64u(self.credential_id),
            "rawId": b64u(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64u(cdj),
                "authenticatorData": b64u(auth_data),
                "signature": b64u(sig),
                "userHandle": b64u(self.user_handle) if self.user_handle else None,
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }
