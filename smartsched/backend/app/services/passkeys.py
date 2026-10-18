"""WebAuthn ceremonies (passkeys) on py_webauthn 3.0.1 (Duo Labs, BSD-3; docs/research/2026-10-18-auth-backend.md §3).

Thin wrappers that fix SmartSched's choices: the relying party is the panel's public host (the full host on sslip.io,
never a public suffix), attestation ``none``, ES256 + RS256, resident key ``preferred``, user verification
``preferred`` for a second factor and ``required`` for passkey-only sign-in, 256-bit challenges, 5-minute timeout.
The accounts, challenges and rows live in :mod:`app.services.mfa`.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

TIMEOUT_MS = 300_000
CHALLENGE_BYTES = 32
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class RelyingParty:
    rp_id: str
    origin: str
    name: str = "SmartSched"


def relying_party_from(base: str | None, name: str = "SmartSched") -> RelyingParty | None:
    """The RP of a public base URL: ``https://host[:port]`` (``http`` only for localhost: WebAuthn needs a secure
    context). The RP ID is the host itself."""
    try:
        parts = urlsplit((base or "").strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host or parts.scheme not in ("https", "http"):
        return None
    if parts.scheme == "http" and host not in LOCAL_HOSTS:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    default = 443 if parts.scheme == "https" else 80
    netloc = host if port in (None, default) else f"{host}:{port}"
    return RelyingParty(rp_id=host, origin=f"{parts.scheme}://{netloc}", name=name or "SmartSched")


async def relying_party(session: AsyncSession, request_origin: str | None = None) -> RelyingParty | None:
    """The installation's RP from ``integrations.public_url`` / ``PUBLIC_URL``. Outside production, without a public
    URL, a ``localhost`` request origin is accepted (development)."""
    from app.core.config import get_settings
    from app.services.bookings_settings import get_value
    from app.services.calendar_feeds import public_base

    name = str(await get_value(session, "org", "name") or "") or "SmartSched"
    base, _source = await public_base(session)
    if base:
        return relying_party_from(base, name)
    if get_settings().environment != "prod" and request_origin:
        rp = relying_party_from(request_origin, name)
        if rp is not None and rp.rp_id in LOCAL_HOSTS:
            return rp
    return None


def new_challenge() -> bytes:
    return secrets.token_bytes(CHALLENGE_BYTES)


def b64(data: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url

    return str(bytes_to_base64url(data))


def unb64(text: str) -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return bytes(base64url_to_bytes(text))


def _descriptors(creds: list[tuple[str, list[str]]]) -> list[Any]:
    from webauthn.helpers.structs import AuthenticatorTransport, PublicKeyCredentialDescriptor

    out = []
    known = {t.value for t in AuthenticatorTransport}
    for cid, transports in creds:
        tr = [AuthenticatorTransport(t) for t in transports if t in known]
        out.append(PublicKeyCredentialDescriptor(id=unb64(cid), transports=tr or None))
    return out


def _to_dict(options: Any) -> dict[str, Any]:
    from webauthn import options_to_json

    return {"publicKey": json.loads(options_to_json(options))}


def registration_options(
    rp: RelyingParty,
    *,
    user_handle: bytes,
    user_name: str,
    display_name: str,
    challenge: bytes,
    exclude: list[tuple[str, list[str]]],
) -> dict[str, Any]:
    from webauthn import generate_registration_options
    from webauthn.helpers.cose import COSEAlgorithmIdentifier
    from webauthn.helpers.structs import (
        AttestationConveyancePreference,
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=rp.name,
        user_id=user_handle,
        user_name=user_name,
        user_display_name=display_name or user_name,
        challenge=challenge,
        timeout=TIMEOUT_MS,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=_descriptors(exclude),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.EDDSA,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    return _to_dict(options)


@dataclass(frozen=True)
class Registered:
    credential_id: str
    public_key: str
    sign_count: int
    aaguid: str
    backup_eligible: bool
    backed_up: bool
    transports: list[str]


class CeremonyError(Exception):
    """The browser's answer did not verify (origin, RP ID, challenge, signature, flags, counter)."""

    def __init__(self, message: str, *, counter: bool = False) -> None:
        super().__init__(message)
        self.counter = counter


def verify_registration(rp: RelyingParty, credential: dict[str, Any], challenge: bytes) -> Registered:
    from webauthn import verify_registration_response
    from webauthn.helpers.structs import CredentialDeviceType

    try:
        v = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            require_user_verification=False,
        )
    except Exception as exc:  # InvalidRegistrationResponse, malformed JSON / CBOR
        raise CeremonyError(str(exc)) from exc
    response = credential.get("response") if isinstance(credential, dict) else None
    transports = response.get("transports") if isinstance(response, dict) else None
    clean = [str(t)[:16] for t in transports if isinstance(t, str)][:8] if isinstance(transports, list) else []
    return Registered(
        credential_id=b64(v.credential_id),
        public_key=b64(v.credential_public_key),
        sign_count=int(v.sign_count),
        aaguid=str(v.aaguid)[:36],
        backup_eligible=v.credential_device_type == CredentialDeviceType.MULTI_DEVICE,
        backed_up=bool(v.credential_backed_up),
        transports=clean,
    )


def authentication_options(
    rp: RelyingParty, *, challenge: bytes, allow: list[tuple[str, list[str]]], require_uv: bool
) -> dict[str, Any]:
    from webauthn import generate_authentication_options
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=rp.rp_id,
        challenge=challenge,
        timeout=TIMEOUT_MS,
        allow_credentials=_descriptors(allow),
        user_verification=UserVerificationRequirement.REQUIRED if require_uv else UserVerificationRequirement.PREFERRED,
    )
    return _to_dict(options)


def credential_id_of(credential: Any) -> str | None:
    """The base64url credential id the browser answered with (``rawId`` / ``id``), or ``None``."""
    if not isinstance(credential, dict):
        return None
    raw = credential.get("rawId") or credential.get("id")
    if not isinstance(raw, str) or not 8 <= len(raw) <= 1400:
        return None
    try:
        return b64(unb64(raw))
    except Exception:
        return None


def verify_assertion(
    rp: RelyingParty,
    credential: dict[str, Any],
    challenge: bytes,
    *,
    public_key: str,
    sign_count: int,
    require_uv: bool,
) -> int:
    """The authenticator's new signature counter after a verified assertion (:class:`CeremonyError` otherwise; a
    counter that did not grow while either value is non-zero marks ``counter=True``: a possibly cloned key)."""
    from webauthn import verify_authentication_response

    try:
        v = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            credential_public_key=unb64(public_key),
            credential_current_sign_count=int(sign_count or 0),
            require_user_verification=require_uv,
        )
    except Exception as exc:
        msg = str(exc)
        raise CeremonyError(msg, counter="sign count" in msg.lower()) from exc
    return int(v.new_sign_count)


__all__ = [
    "CeremonyError",
    "Registered",
    "RelyingParty",
    "authentication_options",
    "credential_id_of",
    "new_challenge",
    "registration_options",
    "relying_party",
    "relying_party_from",
    "verify_assertion",
    "verify_registration",
]
