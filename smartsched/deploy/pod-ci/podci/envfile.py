"""deploy/.env handling on the pod: create from .env.example, set pod values, generate every
__GENERATE__ secret ON THE POD (same semantics as deploy.sh), and list the secrets synced to SSM."""

from __future__ import annotations

import re
import secrets
import string
from pathlib import Path

PLACEHOLDER = "__GENERATE__"
PASSWORD_KEYS = re.compile(r"^(ADMIN_PASSWORD|.*_DB_PASSWORD|POSTGRES_PASSWORD|CRBS_DB_ROOT_PASSWORD)$")
# .env key -> SSM name under /smartsched (all SecureString except admin_email). AUTH_SECRET was dropped
# (dead config, no-placeholder audit m3): pods bootstrapped earlier keep /smartsched/app/AUTH_SECRET and
# the line in .env, both unused and harmless; it is no longer synced.
SSM_MAP = {
    "ADMIN_EMAIL": "admin_email",
    "ADMIN_PASSWORD": "admin_password",
    "APP_SECRET": "app/APP_SECRET",
    "JWT_SECRET": "app/JWT_SECRET",
    "POSTGRES_PASSWORD": "app/POSTGRES_PASSWORD",
}
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def random_password(n: int = 20) -> str:
    """ADMIN_PASSWORD / DB passwords: 20 alphanumerics (the backend needs >= 12 in prod)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def set_keys(text: str, values: dict[str, str]) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if m and m.group(1) in values:
            lines[i] = f"{m.group(1)}={values[m.group(1)]}"
            seen.add(m.group(1))
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def generate(text: str) -> tuple[str, list[str]]:
    generated = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if m and m.group(2).strip() == PLACEHOLDER:
            key = m.group(1)
            value = random_password() if PASSWORD_KEYS.match(key) else secrets.token_hex(32)
            lines[i] = f"{key}={value}"
            generated.append(key)
    return "\n".join(lines) + "\n", generated


def prepare(env_file: Path, example: Path, values: dict[str, str]) -> list[str]:
    """Create env_file from example when missing; always apply values; generate placeholders.

    Values only overwrite non-secret keys: an existing .env keeps its secrets across re-runs."""
    text = env_file.read_text(encoding="utf-8") if env_file.exists() else example.read_text(encoding="utf-8")
    text = set_keys(text, values)
    text, generated = generate(text)
    env_file.write_text(text, encoding="utf-8")
    env_file.chmod(0o600)
    return generated


def ssm_values(env_file: Path) -> dict[str, tuple[str, bool]]:
    env = parse(env_file.read_text(encoding="utf-8"))
    return {ssm: (env[key], key != "ADMIN_EMAIL") for key, ssm in SSM_MAP.items() if env.get(key)}
