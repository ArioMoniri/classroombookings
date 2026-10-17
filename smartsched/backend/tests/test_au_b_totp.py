"""AU-01 TOTP core (RFC 6238, stdlib; docs/research/2026-10-18-auth-backend.md §2) and recovery-code format (§4)."""

from __future__ import annotations

import base64

import pytest
from app.core import totp

#: RFC 6238 Appendix B, SHA-1 rows (secret "12345678901234567890", 8 digits)
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()
VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize(("t", "code"), VECTORS)
def test_rfc6238_appendix_b_sha1_vectors(t: int, code: str) -> None:
    assert totp.code_at(RFC_SECRET, t, digits=8) == code


def test_six_digit_codes_are_the_last_six_of_the_truncation() -> None:
    assert totp.code_at(RFC_SECRET, 59) == "287082"


def test_new_secret_is_160_bits_base32_unpadded() -> None:
    s = totp.new_secret()
    assert len(s) == 32 and "=" not in s
    assert len(base64.b32decode(s)) == 20
    assert totp.new_secret() != s


def test_drift_of_one_step_either_way_is_accepted_two_is_not() -> None:
    secret = totp.new_secret()
    now = 1_760_000_000.0
    step = int(now // 30)
    for delta in (-1, 0, 1):
        code = totp.code_at(secret, (step + delta) * 30)
        assert totp.match(secret, code, now=now) == step + delta
    for delta in (-2, 2):
        assert totp.match(secret, totp.code_at(secret, (step + delta) * 30), now=now) is None


def test_replay_of_the_same_or_an_earlier_step_is_refused() -> None:
    secret = totp.new_secret()
    now = 1_760_000_000.0
    step = int(now // 30)
    code = totp.code_at(secret, step * 30)
    assert totp.match(secret, code, now=now, last_step=step - 1) == step
    assert totp.match(secret, code, now=now, last_step=step) is None
    earlier = totp.code_at(secret, (step - 1) * 30)
    assert totp.match(secret, earlier, now=now, last_step=step) is None


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 34 5x", None])
def test_malformed_codes_never_match(bad: str | None) -> None:
    assert totp.match(totp.new_secret(), bad, now=1_760_000_000.0) is None


def test_spaces_in_a_typed_code_are_ignored() -> None:
    secret = totp.new_secret()
    code = totp.code_at(secret, 1_760_000_000)
    assert totp.match(secret, f"{code[:3]} {code[3:]}", now=1_760_000_000.0) is not None


def test_otpauth_uri_names_issuer_and_account() -> None:
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", "ayse.yilmaz@uni.edu.tr", "Örnek Üniversitesi")
    assert uri.startswith("otpauth://totp/%C3%96rnek%20%C3%9Cniversitesi:ayse.yilmaz%40uni.edu.tr?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri and "issuer=%C3%96rnek%20%C3%9Cniversitesi" in uri
    assert "algorithm=SHA1" in uri and "digits=6" in uri and "period=30" in uri


def test_recovery_codes_are_80_bit_grouped_and_normalised() -> None:
    codes = totp.new_recovery_codes()
    assert len(codes) == 10 and len(set(codes)) == 10
    for c in codes:
        groups = c.split("-")
        assert len(groups) == 4 and all(len(g) == 4 for g in groups)
        assert set(c.replace("-", "")) <= set(totp.CROCKFORD)
    c = codes[0]
    assert totp.normalise_recovery(c.lower().replace("-", " ")) == c.replace("-", "")
    assert totp.normalise_recovery("oooo-iiii-llll-0000") == "0000111111110000"
    assert totp.normalise_recovery("short") is None
