"""Key material of a SAML service provider (RF-12 / W3-IDP, idp-2026-10-18), on ``cryptography`` only:

* **Certificates and keys pasted by an administrator** (:func:`pem_certificate`, :func:`pem_private_key`): PEM or
  bare base64, NBSP / narrow NBSP / CRLF tolerated (copied from a federation's web page or a Word document).
* **The SP key pair** (:func:`generate_keypair`): RSA-3072 and a self-signed certificate for ten years, as
  Shibboleth SPs use; the IdP imports it from the SP metadata. The private key is Fernet-encrypted by the caller
  (``encrypt_secret``, like ``client_secret``) and never logged, audited or returned.
* **EncryptedAssertion** (:func:`decrypt_element`, XML Encryption 1.0 / 1.1): key transport RSA-OAEP
  (``rsa-oaep-mgf1p``; xmlenc 1.1 ``rsa-oaep`` with SHA-1/224/256/384/512 digests and MGF1); data AES-128/192/256 in
  GCM or CBC (CBC only inside a signed Response: saml.py checks :func:`data_mode` first, idp2-2026-10-18). RSA
  PKCS#1 v1.5 key transport is refused (Bleichenbacher). Every failure after the algorithm checks
  answers the same text, so an attacker learns nothing about the padding (Jager & Somorovsky 2011).
* **HTTP-Redirect signatures** (:func:`sign_redirect`): RSA-SHA256 over ``SAMLRequest=…&RelayState=…&SigAlg=…``
  (SAML bindings §3.4.4.1).
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID

XENC = "http://www.w3.org/2001/04/xmlenc#"
XENC11 = "http://www.w3.org/2009/xmlenc11#"
DSIG = "http://www.w3.org/2000/09/xmldsig#"
DSIG_MORE = "http://www.w3.org/2001/04/xmldsig-more#"
NS = {"xenc": XENC, "xenc11": XENC11, "ds": DSIG}
SIG_ALG = DSIG_MORE + "rsa-sha256"
#: data encryption: algorithm -> (mode, key bytes)
DATA_ALGS = {
    XENC11 + "aes128-gcm": ("gcm", 16),
    XENC11 + "aes192-gcm": ("gcm", 24),
    XENC11 + "aes256-gcm": ("gcm", 32),
    XENC + "aes128-cbc": ("cbc", 16),
    XENC + "aes192-cbc": ("cbc", 24),
    XENC + "aes256-cbc": ("cbc", 32),
}
KEY_ALGS = (XENC + "rsa-oaep-mgf1p", XENC11 + "rsa-oaep")
#: published in the SP metadata, preferred first (an IdP that reads them avoids CBC)
PREFERRED = (
    XENC11 + "aes256-gcm",
    XENC11 + "aes128-gcm",
    XENC + "aes256-cbc",
    XENC + "aes128-cbc",
    XENC11 + "rsa-oaep",
    XENC + "rsa-oaep-mgf1p",
)
_DIGESTS: dict[str, type[hashes.HashAlgorithm]] = {
    DSIG + "sha1": hashes.SHA1,
    XENC + "sha256": hashes.SHA256,
    DSIG_MORE + "sha224": hashes.SHA224,
    DSIG_MORE + "sha384": hashes.SHA384,
    XENC + "sha512": hashes.SHA512,
}
_MGFS: dict[str, type[hashes.HashAlgorithm]] = {
    XENC11 + "mgf1sha1": hashes.SHA1,
    XENC11 + "mgf1sha224": hashes.SHA224,
    XENC11 + "mgf1sha256": hashes.SHA256,
    XENC11 + "mgf1sha384": hashes.SHA384,
    XENC11 + "mgf1sha512": hashes.SHA512,
}
_SPACE = re.compile(r"[\s   ﻿]+")
_PEM = re.compile(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", re.S)
MIN_RSA_BITS = 2048
#: the one answer for every decryption failure (no padding oracle)
DECRYPT_FAILED = "the encrypted assertion could not be decrypted with the SP key"


class DecryptError(Exception):
    """``str(exc)`` is safe for the audit log (no key material, no plaintext)."""


# --------------------------------------------------------------------------------------------------- pasted values


def _body(text: str, label: str) -> bytes:
    """The DER of a pasted PEM block (or bare base64); ``ValueError`` otherwise."""
    text = (text or "").replace("\\n", "\n")
    m = _PEM.search(text)
    if m:
        if label not in m.group(1):
            raise ValueError(f"expected a {label} block, got {m.group(1)}")
        text = m.group(2)
    b64 = _SPACE.sub("", text)
    if not b64 or not re.fullmatch(r"[A-Za-z0-9+/]+=*", b64):
        raise ValueError("not base64")
    return base64.b64decode(b64 + "=" * (-len(b64) % 4))


def pem_certificate(text: str) -> str:
    """A pasted X.509 certificate as PEM; ``ValueError`` when it is not one."""
    try:
        cert = x509.load_der_x509_certificate(_body(text, "CERTIFICATE"))
    except Exception as exc:  # noqa: BLE001 - binascii / ASN.1 errors
        raise ValueError("not an X.509 certificate") from exc
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def pem_private_key(text: str) -> str:
    """A pasted RSA private key (PKCS#1 or PKCS#8, unencrypted, at least 2048 bits) as PKCS#8 PEM; ``ValueError``
    with a text that never repeats the input."""
    try:
        raw = text.strip().replace("\\n", "\n").encode("ascii", "ignore")
        key = (
            serialization.load_pem_private_key(raw, password=None)
            if b"-----BEGIN" in raw
            else serialization.load_der_private_key(_body(text, "PRIVATE KEY"), password=None)
        )
    except Exception as exc:  # noqa: BLE001 - every parse error looks the same
        raise ValueError("not an unencrypted private key") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < MIN_RSA_BITS:
        raise ValueError("an RSA key of at least 2048 bits is needed")
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")


def _load_key(pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):  # pragma: no cover - pem_private_key refuses other keys
        raise ValueError("an RSA key is needed")
    return key


def key_matches(key_pem: str, cert_pem: str) -> bool:
    pub = x509.load_pem_x509_certificate(cert_pem.encode("ascii")).public_key()
    fmt = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return bool(_load_key(key_pem).public_key().public_bytes(*fmt) == pub.public_bytes(*fmt))


def cert_info(pem: str | None) -> dict[str, Any] | None:
    """What the screen shows of a certificate: subject, validity end and the SHA-256 fingerprint."""
    if not pem:
        return None
    try:
        cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    except ValueError:
        return None
    fp = cert.fingerprint(hashes.SHA256()).hex().upper()
    return {
        "subject": cert.subject.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.replace(tzinfo=None).isoformat(timespec="seconds"),
        "sha256": ":".join(fp[i : i + 2] for i in range(0, len(fp), 2)),
    }


def b64_of(pem: str) -> str:
    """The base64 body of a PEM certificate (for ``ds:X509Certificate``)."""
    return "".join(line for line in pem.strip().splitlines() if not line.startswith("-----"))


def self_signed(key_pem: str, common_name: str, *, years: int = 10) -> str:
    key = _load_key(key_pem)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name[:64] or "SmartSched SP")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * years))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def generate_keypair(common_name: str) -> tuple[str, str]:
    """(private key PEM, self-signed certificate PEM): RSA-3072, SHA-256, ten years."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    return key_pem, self_signed(key_pem, common_name)


# --------------------------------------------------------------------------------------------------- redirect binding


def sign_redirect(signed_part: str, key_pem: str) -> str:
    """base64 RSA-SHA256 signature of the URL-encoded ``SAMLRequest=…&RelayState=…&SigAlg=…`` octets."""
    sig = _load_key(key_pem).sign(signed_part.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


# --------------------------------------------------------------------------------------------------- XML Encryption


def _cipher_value(el: Any) -> bytes:
    text = el.findtext("xenc:CipherData/xenc:CipherValue", namespaces=NS)
    if not text:
        raise DecryptError("no CipherValue (CipherReference is not supported)")
    try:
        return base64.b64decode(_SPACE.sub("", text), validate=True)
    except ValueError as exc:
        raise DecryptError("CipherValue is not base64") from exc


def _algorithm(el: Any) -> str:
    method = el.find("xenc:EncryptionMethod", NS)
    return (method.get("Algorithm") or "") if method is not None else ""


def _oaep(ek: Any) -> padding.OAEP:
    method = ek.find("xenc:EncryptionMethod", NS)
    alg = _algorithm(ek)
    digest_el = method.find("ds:DigestMethod", NS) if method is not None else None
    digest_uri = digest_el.get("Algorithm") if digest_el is not None else DSIG + "sha1"
    if digest_uri not in _DIGESTS:
        raise DecryptError(f"unsupported OAEP digest {str(digest_uri)[:80]}")
    mgf_hash: type[hashes.HashAlgorithm] = hashes.SHA1
    if alg == XENC11 + "rsa-oaep":
        mgf_el = method.find("xenc11:MGF", NS) if method is not None else None
        mgf_uri = mgf_el.get("Algorithm") if mgf_el is not None else XENC11 + "mgf1sha1"
        if mgf_uri not in _MGFS:
            raise DecryptError(f"unsupported MGF {str(mgf_uri)[:80]}")
        mgf_hash = _MGFS[mgf_uri]
    params = method.findtext("xenc:OAEPparams", namespaces=NS) if method is not None else None
    label = base64.b64decode(params) if params else None
    return padding.OAEP(mgf=padding.MGF1(mgf_hash()), algorithm=_DIGESTS[digest_uri](), label=label)


def _encrypted_keys(container: Any, data: Any) -> list[Any]:
    """EncryptedKey inside the EncryptedData's KeyInfo (ADFS) or beside it in the EncryptedAssertion (Shibboleth,
    referenced by a RetrievalMethod)."""
    inside: list[Any] = data.findall("ds:KeyInfo/xenc:EncryptedKey", NS)
    beside: list[Any] = container.findall("xenc:EncryptedKey", NS)
    return inside or beside


def data_mode(container: Any) -> str | None:
    """``"gcm"`` or ``"cbc"`` for the data encryption of an ``EncryptedAssertion``, read before any decryption;
    ``None`` when the algorithm is missing or unsupported (the decryptor refuses it then)."""
    data = container.find("xenc:EncryptedData", NS)
    alg = _algorithm(data) if data is not None else ""
    return DATA_ALGS[alg][0] if alg in DATA_ALGS else None


def decrypt_element(container: Any, key_pem: str) -> bytes:
    """The plaintext XML of an ``EncryptedAssertion`` (``EncryptedData`` of ``Type=#Element``). Raises
    :class:`DecryptError`."""
    data = container.find("xenc:EncryptedData", NS)
    if data is None:
        raise DecryptError("no EncryptedData")
    data_alg = _algorithm(data)
    if data_alg not in DATA_ALGS:
        raise DecryptError(f"unsupported data encryption {data_alg[:80] or 'missing'}")
    mode, size = DATA_ALGS[data_alg]
    eks = _encrypted_keys(container, data)
    if not eks:
        raise DecryptError("no EncryptedKey")
    for ek in eks:
        alg = _algorithm(ek)
        if alg == XENC + "rsa-1_5":
            raise DecryptError("rsa-1_5 key transport is refused: use RSA-OAEP at the IdP")
        if alg not in KEY_ALGS:
            raise DecryptError(f"unsupported key transport {alg[:80] or 'missing'}")
    key = _load_key(key_pem)
    cipher = _cipher_value(data)
    sym: bytes | None = None
    for ek in eks:  # several recipients: the one for this SP's key opens
        try:
            candidate = key.decrypt(_cipher_value(ek), _oaep(ek))
        except DecryptError:
            raise
        except Exception:  # noqa: BLE001, S112 - a key for another recipient
            continue
        if len(candidate) == size:
            sym = candidate
            break
    try:
        if sym is None:
            raise ValueError("no key")
        if mode == "gcm":
            if len(cipher) < 12 + 16:
                raise ValueError("short")
            return AESGCM(sym).decrypt(cipher[:12], cipher[12:], None)
        if len(cipher) < 32 or len(cipher) % 16:
            raise ValueError("short")
        dec = Cipher(algorithms.AES(sym), modes.CBC(cipher[:16])).decryptor()
        plain = dec.update(cipher[16:]) + dec.finalize()
        pad = plain[-1]
        if not 1 <= pad <= 16:  # XML Encryption padding: only the last octet is defined
            raise ValueError("padding")
        return plain[:-pad]
    except Exception as exc:  # noqa: BLE001 - one answer for every failure
        raise DecryptError(DECRYPT_FAILED) from exc
