"""Deploy seed profile: what a one-click deploy loads on first boot (smartsched/deploy/profile.env).

    SEED_PROFILE=empty         nothing; the setup wizard + /onboarding (claude/smartsched-universal)
    SEED_PROFILE=institution   bookings.approval_mode=all (every request is approved first), the owner's files: Bahar /
                               Güz / Final workbooks + room master, the preference rules the planning / exam
                               importers derive from their free-text columns, then the learning extraction
                               (claude/gracious-cerf-w1598m)

Both branches carry the same code; only profile.env differs (.gitattributes: merge=ours). A missing file or key
means ``empty``.

Run by deploy.sh inside the backend image (same Python, same DATABASE_URL), after the stack is healthy:

    python /seed/tool/seed.py run      # files bind-mounted read-only at /seed/files
    python seed.py plan --profile institution --files-dir smartsched/backend/tests/fixtures   # validate.sh

Idempotent: every finished step is recorded in the settings row ``deploy.seed_profile`` (JSON). A later deploy runs
only the steps not recorded yet (e.g. the learning step once its CLI exists) and never re-imports a file. A
database that already holds terms but has no marker (someone imported by hand) is left alone unless
SEED_FORCE=1. Only existing CLI commands are used (``python -m app.cli ...``); a missing command is reported and
retried on the next deploy, it does not fail the deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

PROFILES = ("empty", "institution")
DEFAULT_PROFILE = "empty"
MARKER_KEY = "deploy.seed_profile"
MARKER_VERSION = 1


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]  # app.cli arguments; "{files}" is replaced by the files directory
    files: tuple[str, ...] = ()  # seed files the step reads (checked by `plan`)
    optional_cli: bool = False  # the CLI command may not exist yet: skip + retry later instead of failing


# The owner's policy for the institution (2026-10-15): every booking request goes to the administrators first.
# Written through the PUT /org/settings validation (app.cli set-setting); first, so the policy holds even if an
# import below fails. Recorded in the marker like every step: an administrator who later switches the mode back
# in Ayarlar is not overridden by the next deploy. The empty profile sets nothing (the default stays "rules").
APPROVAL_MODE = Step("approval-mode", ("set-setting", "bookings.approval_mode", "all"))

# Same files and order as scripts/record/stack.sh (the e2e / record stacks).
INSTITUTION: tuple[Step, ...] = (
    APPROVAL_MODE,
    Step("bahar-grid", ("import", "weekly-grid", "{files}/bahar_derslikler_takvimi_2026.xlsx", "--term", "2026-BAHAR",
                        "--year", "2026"), ("bahar_derslikler_takvimi_2026.xlsx",)),
    Step("bahar-planning", ("import", "planning-list", "{files}/bahar_derslik_planlama_listesi_v5.xlsx", "--term",
                            "2026-BAHAR"), ("bahar_derslik_planlama_listesi_v5.xlsx",)),
    Step("guz-grid", ("import", "weekly-grid", "{files}/guz_derslikler_takvimi_2026_2027.xlsx", "--term", "2026-GUZ",
                      "--year", "2026"), ("guz_derslikler_takvimi_2026_2027.xlsx",)),
    Step("guz-planning", ("import", "planning-list", "{files}/guz_derslik_planlama_2026_2027_v2.xlsx", "--term",
                          "2026-GUZ"), ("guz_derslik_planlama_2026_2027_v2.xlsx",)),
    Step("final-grid", ("import", "weekly-grid", "{files}/final_derslikler_takvimi_2026_v2.xlsx", "--term",
                        "2026-FINAL", "--year", "2026"), ("final_derslikler_takvimi_2026_v2.xlsx",)),
    Step("final-exams", ("import", "exam-list", "{files}/final_planlama_listesi_2026_v2.xlsx", "--term", "2026-FINAL"),
         ("final_planlama_listesi_2026_v2.xlsx",)),
    Step("room-master", ("import", "room-master", "{files}/room_master.csv"), ("room_master.csv",)),
    # app.services.learning.refresh over every term (app.cli learning-refresh)
    Step("learning", ("learning-refresh",), optional_cli=True),
)


def steps_for(profile: str) -> tuple[Step, ...]:
    return INSTITUTION if profile == "institution" else ()


def parse_profile(text: str | None) -> str:
    """SEED_PROFILE from profile.env text (KEY=VALUE lines, # comments, optional quotes). Missing -> empty."""
    value = None
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if line.startswith("SEED_PROFILE="):
            value = line.split("=", 1)[1].strip().strip("'\"")
    value = value or DEFAULT_PROFILE
    if value not in PROFILES:
        raise ValueError(f"SEED_PROFILE={value!r}: expected one of {', '.join(PROFILES)}")
    return value


def read_profile(path: Path) -> str:
    return parse_profile(path.read_text(encoding="utf-8") if path.is_file() else None)


# ---- marker store ----------------------------------------------------------------------------------------------
class Store(Protocol):
    def get(self) -> dict[str, Any] | None: ...
    def put(self, marker: dict[str, Any]) -> None: ...
    def has_terms(self) -> bool: ...


class DbStore:
    """The ``settings`` row ``deploy.seed_profile`` (key/value table, no migration needed)."""

    def __init__(self, url: str) -> None:
        from sqlalchemy import create_engine  # backend image only

        sync = url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")
        self.engine = create_engine(sync, pool_pre_ping=True)

    def get(self) -> dict[str, Any] | None:
        from sqlalchemy import text

        with self.engine.connect() as c:
            row = c.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": MARKER_KEY}).first()
        return json.loads(row[0]) if row and row[0] else None

    def put(self, marker: dict[str, Any]) -> None:
        from sqlalchemy import text

        value, now = json.dumps(marker, ensure_ascii=False, sort_keys=True), datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as c:
            done = c.execute(text("UPDATE settings SET value = :v, updated_at = :t WHERE key = :k"),
                             {"k": MARKER_KEY, "v": value, "t": now}).rowcount
            if not done:
                c.execute(text("INSERT INTO settings (key, value, is_secret, updated_at) VALUES (:k, :v, :s, :t)"),
                          {"k": MARKER_KEY, "v": value, "s": False, "t": now})

    def has_terms(self) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as c:
            return c.execute(text("SELECT 1 FROM terms LIMIT 1")).first() is not None


# ---- runner ----------------------------------------------------------------------------------------------------
Runner = Callable[[Sequence[str]], int]
MISSING_CLI = 2  # argparse: invalid choice


def cli_runner(argv: Sequence[str]) -> int:
    return subprocess.run([sys.executable, "-m", "app.cli", *argv], check=False).returncode


def cli_has(runner: Runner, command: str) -> bool:
    return runner([command, "--help"]) == 0


@dataclass
class Outcome:
    profile: str
    ran: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # optional CLI missing: retried on the next deploy
    already: list[str] = field(default_factory=list)
    note: str = ""


def run(profile: str, store: Store, runner: Runner, files_dir: str, *, force: bool = False,
        log: Callable[[str], None] = print) -> Outcome:
    out = Outcome(profile)
    steps = steps_for(profile)
    if not steps:
        out.note = "empty profile: nothing to load (setup wizard / onboarding)"
        log(f"[seed] {out.note}")
        return out
    marker = store.get()
    if marker is None and store.has_terms() and not force:
        out.note = "terms exist but no seed marker: data was loaded by hand; not importing (SEED_FORCE=1 overrides)"
        log(f"[seed] {out.note}")
        return out
    marker = marker or {"profile": profile, "version": MARKER_VERSION, "steps": {}}
    if marker.get("profile") != profile:
        out.note = f"database was seeded with profile {marker.get('profile')!r}; not changing it to {profile!r}"
        log(f"[seed] {out.note}")
        return out
    done: dict[str, str] = marker.setdefault("steps", {})
    for step in steps:
        if step.name in done:
            out.already.append(step.name)
            continue
        if step.optional_cli and not cli_has(runner, step.argv[0]):
            out.skipped.append(step.name)
            log(f"[seed] {step.name}: `app.cli {step.argv[0]}` does not exist yet; skipped (retried next deploy)")
            continue
        argv = [a.replace("{files}", files_dir) for a in step.argv]
        log(f"[seed] {step.name}: app.cli {' '.join(argv)}")
        code = runner(argv)
        if code != 0:
            raise RuntimeError(f"seed step {step.name} failed (exit {code}); finished steps are kept, rerun deploy")
        done[step.name] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.put(marker)  # after every step: a failed deploy resumes where it stopped
        out.ran.append(step.name)
    log(f"[seed] profile {profile}: ran {out.ran or '-'}, already {out.already or '-'}, skipped {out.skipped or '-'}")
    return out


def plan(profile: str, files_dir: Path) -> list[str]:
    """Problems with the profile's seed files (validate.sh); [] = ready."""
    return [f"missing seed file {files_dir / f}" for s in steps_for(profile) for f in s.files
            if not (files_dir / f).is_file()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("command", choices=["run", "plan", "profile"])
    ap.add_argument("--profile", default=None, help="default: SEED_PROFILE env, else profile.env, else empty")
    ap.add_argument("--profile-file", default=str(Path(__file__).resolve().parent.parent / "profile.env"))
    ap.add_argument("--files-dir", default=os.environ.get("SEED_FILES_DIR", "/seed/files"))
    a = ap.parse_args(argv)
    explicit = a.profile or os.environ.get("SEED_PROFILE")
    try:
        profile = parse_profile(f"SEED_PROFILE={explicit}") if explicit else read_profile(Path(a.profile_file))
    except ValueError as exc:
        print(f"[seed] {exc}", file=sys.stderr)
        return 2
    if a.command == "profile":
        print(profile)
        return 0
    if a.command == "plan":
        problems = plan(profile, Path(a.files_dir))
        for p in problems:
            print(f"[seed] {p}", file=sys.stderr)
        print(f"[seed] profile {profile}: {len(steps_for(profile))} step(s): "
              f"{', '.join(s.name for s in steps_for(profile)) or 'none'}")
        return 1 if problems else 0
    problems = plan(profile, Path(a.files_dir))
    if problems:
        print("\n".join(f"[seed] {p}" for p in problems), file=sys.stderr)
        return 1
    try:
        run(profile, DbStore(os.environ["DATABASE_URL"]) if steps_for(profile) else _NoStore(), cli_runner,
            a.files_dir, force=os.environ.get("SEED_FORCE") == "1")
    except RuntimeError as exc:
        print(f"[seed] {exc}", file=sys.stderr)
        return 1
    return 0


class _NoStore:
    def get(self) -> dict[str, Any] | None:
        return None

    def put(self, marker: dict[str, Any]) -> None:
        return None

    def has_terms(self) -> bool:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
