#!/usr/bin/env python3
"""Rewrite the generated blocks of the Markdown docs from the sources of truth (docs/STATUS.md explains the setup).

A generated block is everything between two marker lines, each on a line of its own:

    <!-- AUTO:<name> [key=value ...] -->
    ... generated, never edit by hand ...
    <!-- /AUTO:<name> -->

Only the text between the markers is rewritten; everything around it is left byte for byte. Markers inside fenced
code blocks are examples and are ignored. A file without markers is never touched (README.md included). The
output depends only on the files in the tree (and, for ``last-updated``, on git), so a second run changes nothing.

Blocks (sources in brackets):

    status        "What is built" from docs/features.yml (``only=done`` for a short Done-only table)
    roadmap       ticked / open checkboxes per section of docs/ROADMAP.md
    decisions     owner / user decision sets in docs/ROADMAP.md (title lines with dates)
    parity        CRBS superset gate result + tested commit (docs/testing/crbs-parity-report.md; ``gaps=yes`` lists
                  the GAP rows)
    migrations    the Alembic chain and its single head (smartsched/backend/alembic/versions)
    gates         pod CI gates (smartsched/deploy/pod-ci/podci/gates.py) + recorded results with commit and date
                  (docs/testing/gate-results.json, if it exists)
    agents        agent counts per status and the running ledgers (docs/agents/registry.json; no prompts)
    languages     offered interface languages and the TR catalogue state (bookings_i18n.py, lib/i18n, messages/)
    formats       intake formats of the Ingestion Council (app/council/formats*.py registry entries)
    last-updated  HEAD's commit and date (git). Volatile: ``--check`` does not compare it, and without git (pod CI
                  exports the tree with git archive) the block keeps its text.

Usage (standard library only; run it isolated):

    python3 -I scripts/docs/sync_docs.py            # rewrite every stale block
    python3 -I scripts/docs/sync_docs.py --check    # exit 1 and name the stale blocks (pod CI, validate gate)
    python3 -I scripts/docs/sync_docs.py --check --diff
    python3 -I scripts/docs/sync_docs.py --list     # blocks per file, with their state
    python3 -I scripts/docs/sync_docs.py --record-podci /var/lib/smartsched-ci/ci.sqlite3 [--branch B]
                                                    # copy the last finished pod CI run into gate-results.json

Exit status: 0 ok, 1 stale (``--check``), 2 a malformed marker, an unknown block or an unreadable source.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import difflib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

FEATURES = "docs/features.yml"
ROADMAP = "docs/ROADMAP.md"
PARITY_REPORT = "docs/testing/crbs-parity-report.md"
VERSIONS = "smartsched/backend/alembic/versions"
GATES_PY = "smartsched/deploy/pod-ci/podci/gates.py"
GATE_RESULTS = "docs/testing/gate-results.json"
REGISTRY = "docs/agents/registry.json"
COUNCIL = "smartsched/backend/app/council"
BOOKINGS_I18N = "smartsched/backend/app/services/bookings_i18n.py"
FRONTEND_I18N = "smartsched/frontend/src/lib/i18n/index.ts"
MESSAGES = "smartsched/frontend/messages"

SKIP_DIRS = frozenset({
    ".git", "node_modules", ".next", "__pycache__", ".venv", "venv", ".claude", ".swarm", ".hive-mind",
    "crbs-core", "uploads", "local", "assets", "test-results", "playwright-report", ".pytest_cache",
    ".mypy_cache", ".ruff_cache",
})

OPEN_RE = re.compile(r"^[ \t]*<!-- AUTO:([a-z][a-z0-9-]*)((?:[ \t]+[a-z][a-z0-9_-]*=[^\s=]+)*)[ \t]*-->[ \t]*$")
CLOSE_RE = re.compile(r"^[ \t]*<!-- /AUTO:([a-z][a-z0-9-]*)[ \t]*-->[ \t]*$")
ANY_MARK_RE = re.compile(r"^[ \t]*<!-- /?AUTO:")
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


class SyncError(Exception):
    """A malformed marker, an unknown block or a source that cannot be read: exit status 2."""


# --------------------------------------------------------------------------------------------------
# markers
# --------------------------------------------------------------------------------------------------


@dataclass
class Block:
    name: str
    args: dict[str, str]
    start: int  # index of the open-marker line
    end: int  # index of the close-marker line
    body: str  # the text between the marker lines

    @property
    def label(self) -> str:
        extra = " ".join(f"{k}={v}" for k, v in self.args.items())
        return f"{self.name} {extra}".strip()


def parse_blocks(text: str, where: str = "<text>") -> tuple[list[str], list[Block]]:
    """The file's lines (with their line ends) and its blocks; markers in fenced code are ignored."""
    lines = text.splitlines(keepends=True)
    blocks: list[Block] = []
    fence: str | None = None
    current: tuple[str, dict[str, str], int] | None = None
    for i, raw in enumerate(lines):
        line = raw.rstrip("\r\n")
        m = FENCE_RE.match(line)
        if m and current is None:
            mark = m.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):].strip():
                fence = None
            continue
        if fence is not None:
            continue
        opened, closed = OPEN_RE.match(line), CLOSE_RE.match(line)
        if opened:
            if current is not None:
                raise SyncError(f"{where}:{i + 1}: AUTO:{opened.group(1)} opens inside AUTO:{current[0]}")
            args = dict(kv.split("=", 1) for kv in opened.group(2).split())
            current = (opened.group(1), args, i)
        elif closed:
            if current is None or closed.group(1) != current[0]:
                raise SyncError(f"{where}:{i + 1}: /AUTO:{closed.group(1)} closes a block that is not open")
            name, args, start = current
            blocks.append(Block(name, args, start, i, "".join(lines[start + 1:i])))
            current = None
        elif ANY_MARK_RE.match(line):
            raise SyncError(f"{where}:{i + 1}: malformed AUTO marker: {line.strip()}")
    if current is not None:
        raise SyncError(f"{where}:{current[2] + 1}: AUTO:{current[0]} is never closed")
    return lines, blocks


def newline_of(lines: list[str]) -> str:
    return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"


# --------------------------------------------------------------------------------------------------
# context
# --------------------------------------------------------------------------------------------------


@dataclass
class Context:
    root: Path
    target: Path  # the Markdown file being rendered (links are relative to it)
    args: dict[str, str] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> str:
        p = self.path(rel)
        try:
            return p.read_text(encoding="utf-8")
        except OSError as exc:
            raise SyncError(f"cannot read {rel}: {exc.strerror or exc}") from exc

    def link(self, rel: str, text: str | None = None) -> str:
        """A Markdown link from the target file to a repo path."""
        href = PurePosixPath(os.path.relpath(self.root / rel, self.target.parent).replace(os.sep, "/"))
        return f"[{text or rel}]({href.as_posix()})"

    def memo(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]


def cell(value: object) -> str:
    """One Markdown table cell: no line breaks, pipes escaped."""
    return " ".join(str(value).split()).replace("|", "\\|")


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:(")
    # never end inside an open inline-code span
    if cut.count("`") % 2:
        cut = cut[: cut.rfind("`")].rstrip(" ,;:(")
    return cut + "…"


def table(head: list[str], rows: list[list[object]], align: list[str] | None = None) -> list[str]:
    sep = [("---:" if a == "r" else "---") for a in (align or ["l"] * len(head))]
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(sep) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return out


# --------------------------------------------------------------------------------------------------
# docs/features.yml: a tiny YAML subset (a list of flat mappings with scalar values)
# --------------------------------------------------------------------------------------------------

FEATURE_KEYS = ("feature", "area", "status", "phase", "evidence", "note")
STATUSES = {"done": "Done", "backend-only": "Backend only", "in-progress": "In progress", "planned": "Planned"}
AREAS = {
    "planning": "Planning",
    "intake": "Intake",
    "bookings": "Bookings (the classroombookings side)",
    "identity": "Identity and notifications",
    "languages": "Languages",
    "platform": "Platform, CI and docs",
}


def _scalar(raw: str, where: str) -> str:
    raw = raw.strip()
    if raw[:1] == '"':
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SyncError(f"{where}: bad double-quoted string") from exc
        if not isinstance(value, str):
            raise SyncError(f"{where}: bad double-quoted string")
        return value
    if raw[:1] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise SyncError(f"{where}: unterminated single-quoted string")
        return raw[1:-1].replace("''", "'")
    if " #" in raw:
        raw = raw.split(" #", 1)[0].rstrip()
    if raw[:1] in "[{&*!|>%@`" or ": " in raw:
        raise SyncError(f"{where}: quote this value (YAML would read it differently): {raw!r}")
    return raw


def parse_features_yaml(text: str, where: str = FEATURES) -> list[dict[str, str]]:
    """``- key: value`` items with ``  key: value`` continuation lines; ``#`` comments; nothing else."""
    items: list[dict[str, str]] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        at = f"{where}:{n}"
        if line.startswith("- "):
            items.append({})
            body = line[2:]
        elif line.startswith("  ") and not line.startswith("   ") and items:
            body = line[2:]
        else:
            raise SyncError(f"{at}: expected '- key: value' or '  key: value'")
        key, sep, value = body.partition(":")
        if not sep or not re.fullmatch(r"[a-z_]+", key):
            raise SyncError(f"{at}: expected 'key: value'")
        if key not in FEATURE_KEYS:
            raise SyncError(f"{at}: unknown key {key!r} (allowed: {', '.join(FEATURE_KEYS)})")
        if key in items[-1]:
            raise SyncError(f"{at}: duplicate key {key!r}")
        items[-1][key] = _scalar(value, at)
    for i, item in enumerate(items, 1):
        for key in ("feature", "area", "status"):
            if not item.get(key):
                raise SyncError(f"{where}: item {i} has no {key}")
        if item["status"] not in STATUSES:
            raise SyncError(f"{where}: item {i}: status {item['status']!r} is not one of {', '.join(STATUSES)}")
        if item["area"] not in AREAS:
            raise SyncError(f"{where}: item {i}: area {item['area']!r} is not one of {', '.join(AREAS)}")
    return items


def gen_status(ctx: Context) -> str:
    items = ctx.memo("features", lambda: parse_features_yaml(ctx.read(FEATURES)))
    counts = Counter(i["status"] for i in items)
    summary = " · ".join(f"{STATUSES[s]} {counts[s]}" for s in STATUSES)
    only = ctx.args.get("only")
    if only is not None and only not in STATUSES:
        raise SyncError(f"status: only={only!r} is not one of {', '.join(STATUSES)}")

    def evidence(i: dict[str, str]) -> str:
        ev = i.get("evidence", "")
        if not ev:
            return ""
        if not ctx.path(ev).exists():
            raise SyncError(f"{FEATURES}: evidence path {ev} does not exist ({i['feature'][:40]}…)")
        return ctx.link(ev, "`" + PurePosixPath(ev).name + "`")

    out = [f"{summary} (from {ctx.link(FEATURES, '`docs/features.yml`')}).", ""]
    if only:
        chosen = [i for i in items if i["status"] == only]
        out += table(["Feature", "Area", "Evidence"],
                     [[i["feature"], AREAS[i["area"]].split(" (")[0], evidence(i)] for i in chosen])
        return "\n".join(out)
    for area, label in AREAS.items():
        rows = [i for i in items if i["area"] == area]
        if not rows:
            continue
        out += [f"**{label}**", ""]
        out += table(["Feature", "Status", "Phase", "Evidence"], [
            [i["feature"], STATUSES[i["status"]] + (f": {i['note']}" if i.get("note") else ""),
             i.get("phase", ""), evidence(i)] for i in rows])
        out.append("")
    return "\n".join(out).rstrip()


# --------------------------------------------------------------------------------------------------
# docs/ROADMAP.md: checkbox counts and the decision sets
# --------------------------------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{2,4})\s+(.*\S)\s*$")
CHECK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b(?:\s+(~?\d{2}:\d{2}))?")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def gen_roadmap(ctx: Context) -> str:
    rows: list[list[object]] = []
    title, done, open_ = "(top)", 0, 0

    def flush() -> None:
        if done or open_:
            rows.append([shorten(title, 90), done, open_])

    for line in ctx.read(ROADMAP).splitlines():
        h = HEADING_RE.match(line)
        if h:
            flush()
            title, done, open_ = LINK_RE.sub(r"\1", h.group(2)), 0, 0
            continue
        c = CHECK_RE.match(line)
        if c:
            if c.group(1) == " ":
                open_ += 1
            else:
                done += 1
    flush()
    total_done = sum(int(r[1]) for r in rows)  # type: ignore[call-overload]
    total_open = sum(int(r[2]) for r in rows)  # type: ignore[call-overload]
    with_open = sum(1 for r in rows if r[2])
    out = [f"{ctx.link(ROADMAP, '`docs/ROADMAP.md`')}: **{total_done} ticked · {total_open} open** checkboxes in "
           f"{len(rows)} sections ({with_open} with open items).", "",
           "<details><summary>Per section</summary>", ""]
    out += table(["Section", "Ticked", "Open"], rows, ["l", "r", "r"])
    out += ["", "</details>"]
    return "\n".join(out)


#: "User decisions (...)", "Owner decisions ...", "Solver decisions (owner, ...)", "Phase 19 UX decisions (owner, ...)"
DECISION_LINE_RE = re.compile(
    r"^(?:#{2,4}\s+)?(?P<title>(?=[A-Z])[^\n]*?(?:\b(?:[Oo]wner|[Uu]ser) decisions\b|\bdecisions \((?:owner|user),)[^\n]*)$")


@dataclass
class DecisionSet:
    title: str
    date: str
    time: str
    order: int
    items: list[str]


def _lead(text: str) -> str:
    text = LINK_RE.sub(r"\1", text).strip()
    bold = re.match(r"^\*\*(.+?)\*\*", text)
    if bold:
        return shorten(bold.group(1).rstrip(":."), 100)
    first = re.split(r"(?<=[A-Za-z0-9)\]`])\.\s", text, maxsplit=1)[0]
    return shorten(first.rstrip(".:"), 110)


def _undated(title: str) -> str:
    """The title without its date / time (shown in its own column): "Solver decisions (owner, 2026-10-15)" ->
    "Solver decisions (owner)"."""
    title = re.sub(r"\s*\d{4}-\d{2}-\d{2}(?:\s+~?\d{2}:\d{2})?", "", title)
    for a, b in ((",)", ")"), (",;", ";"), ("()", ""), (" :", ":")):
        title = title.replace(a, b)
    return " ".join(title.split()).rstrip(":")


def roadmap_decisions(text: str) -> list[DecisionSet]:
    sets: list[DecisionSet] = []
    section_date, section_time = "", ""
    current: DecisionSet | None = None
    for line in text.splitlines():
        h = HEADING_RE.match(line)
        if h:
            current = None
            d = DATE_RE.search(h.group(2))
            section_date, section_time = (d.group(1), d.group(2) or "") if d else ("", "")
        stripped = line.strip()
        if not stripped:
            continue
        m = DECISION_LINE_RE.match(stripped)
        if m is not None and not stripped.startswith(("-", "*")):
            title = m.group("title").strip()
            inline = ""
            if not h and ": " in title and not title.endswith(":"):
                title, inline = title.split(": ", 1)
            title = LINK_RE.sub(r"\1", title).rstrip(":").strip()
            d = DATE_RE.search(title)
            date, time = (d.group(1), d.group(2) or "") if d else (section_date, section_time)
            title = _undated(title)
            current = DecisionSet(title, date, time, len(sets), [])
            sets.append(current)
            if inline:
                current.items += [_lead(p) for p in inline.rstrip(".").split("; ") if p.strip()]
                current = None
            continue
        if current is None:
            continue
        if h:
            current = None
        elif re.match(r"^[-*]\s+(?!\[[ xX]\])", line):
            current.items.append(_lead(line[2:]))
        elif not line.startswith((" ", "\t", "-", "*")):
            current = None  # a paragraph after the list ends the set
    return sets


def gen_decisions(ctx: Context) -> str:
    sets = ctx.memo("decisions", lambda: roadmap_decisions(ctx.read(ROADMAP)))
    if not sets:
        raise SyncError(f"{ROADMAP}: no owner / user decision sets found")
    out = [f"Owner and user decisions recorded in {ctx.link(ROADMAP, '`docs/ROADMAP.md`')}, newest first "
           f"(title lines only; the full text is in the roadmap).", ""]
    for s in sorted(sets, key=lambda s: (s.date, s.time.lstrip("~"), s.order), reverse=True):
        when = f"{s.date} {s.time}".strip() or "undated"
        out.append(f"- **{when}**: {shorten(s.title, 110)}")
        out += [f"  - {item}" for item in s.items]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# CRBS parity report
# --------------------------------------------------------------------------------------------------

@dataclass
class Parity:
    result: str
    when: str
    commit: str
    counts: Counter[str]
    rows: list[tuple[str, str, str, str, str]]  # row id, behaviour, api, ui, result


def parse_parity(text: str) -> Parity:
    head = re.search(r"on (\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC) \(commit `([0-9a-f]{7,40})`\)", text)
    verdict = re.search(r"\*\*Result: ([A-Z]+)\*\*", text)
    if not head or not verdict:
        raise SyncError(f"{PARITY_REPORT}: no 'Generated ... on <date> (commit `<sha>`)' / '**Result: X**' line")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith(("| Row ", "|---")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) < 6:
            continue
        rows.append((cells[0], cells[1], cells[3], cells[4], cells[5].strip("*")))
    counts = Counter(r[4] for r in rows)
    stated = re.search(r"PASS (\d+) · GAP (\d+).*?FAIL (\d+) · MISSING (\d+)", text)
    if stated:
        want = dict(zip(("PASS", "GAP", "FAIL", "MISSING"), map(int, stated.groups()), strict=True))
        got = {k: counts.get(k, 0) for k in want}
        if want != got:
            raise SyncError(f"{PARITY_REPORT}: the summary line says {want} but the table has {got}")
    return Parity(verdict.group(1), head.group(1), head.group(2), counts, rows)


def gen_parity(ctx: Context) -> str:
    p: Parity = ctx.memo("parity", lambda: parse_parity(ctx.read(PARITY_REPORT)))
    c = p.counts
    out = [f"**CRBS superset gate: {p.result}**: PASS {c['PASS']} · GAP {c['GAP']} · FAIL {c['FAIL']} · "
           f"MISSING {c['MISSING']} of {len(p.rows)} rows, measured on commit `{p.commit}` ({p.when}) by "
           f"`scripts/parity_check.py`. Full table: {ctx.link(PARITY_REPORT, '`crbs-parity-report.md`')}."]
    if ctx.args.get("gaps") == "yes":
        gaps = [r for r in p.rows if r[4] in ("GAP", "FAIL", "MISSING")]
        out += ["", f"Rows not passing ({len(gaps)}):", ""]
        out += table(["Row", "Behaviour / screen", "API", "UI", "Result"],
                     [[r[0], shorten(r[1], 110), r[2], r[3], r[4]] for r in gaps])
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# Alembic chain
# --------------------------------------------------------------------------------------------------

@dataclass
class Migration:
    file: str
    revision: str
    down: tuple[str, ...]
    summary: str


def _const_strings(node: ast.AST | None) -> tuple[str, ...]:
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
        return ()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.Tuple | ast.List):
        return tuple(s for e in node.elts for s in _const_strings(e))
    raise SyncError(f"unsupported revision expression: {ast.dump(node)[:80]}")


def first_sentence(doc: str) -> str:
    para = " ".join(doc.strip().split("\n\n", 1)[0].split())
    sentence = re.split(r"(?<=[a-z0-9)\]`])\.\s|:\s(?=[A-Z])", para, maxsplit=1)[0]
    return shorten(sentence.rstrip(".:"), 120)


def read_migrations(root: Path) -> list[Migration]:
    out = []
    directory = root / VERSIONS
    if not directory.is_dir():
        raise SyncError(f"{VERSIONS} is missing")
    for f in sorted(directory.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        values: dict[str, ast.AST | None] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                values[node.targets[0].id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                values[node.target.id] = node.value
        if "revision" not in values:
            continue
        rev = _const_strings(values["revision"])
        if len(rev) != 1:
            raise SyncError(f"{f.name}: revision must be one string")
        doc = ast.get_docstring(tree) or ""
        out.append(Migration(f.name, rev[0], _const_strings(values.get("down_revision")), first_sentence(doc)))
    return out


def chain_order(migs: list[Migration]) -> tuple[list[Migration], list[str]]:
    by_rev = {m.revision: m for m in migs}
    referenced = {d for m in migs for d in m.down}
    heads = sorted(r for r in by_rev if r not in referenced)
    order: list[Migration] = []
    seen: set[str] = set()

    def visit(rev: str) -> None:
        if rev in seen or rev not in by_rev:
            return
        seen.add(rev)
        for d in by_rev[rev].down:
            visit(d)
        order.append(by_rev[rev])

    for h in heads:
        visit(h)
    for m in migs:  # cycles / orphans still show up
        visit(m.revision)
    return order, heads


def gen_migrations(ctx: Context) -> str:
    migs = ctx.memo("migrations", lambda: read_migrations(ctx.root))
    order, heads = chain_order(migs)
    rows = [[i, f"`{m.revision}`", ", ".join(f"`{d}`" for d in m.down) or "(base)", m.summary]
            for i, m in enumerate(order, 1)]
    if len(heads) == 1:
        lead = (f"{len(order)} migrations in {ctx.link(VERSIONS, '`alembic/versions`')}; single head "
                f"**`{heads[0]}`**. A new migration goes on top of it (`alembic heads` must print one line).")
    else:
        lead = (f"**{len(heads)} heads** ({', '.join(f'`{h}`' for h in heads)}) in "
                f"{ctx.link(VERSIONS, '`alembic/versions`')}: `alembic upgrade head` fails until they are merged or "
                f"renumbered onto one head.")
    missing = sorted({d for m in migs for d in m.down} - {m.revision for m in migs})
    if missing:
        lead += f" Unknown parents: {', '.join(f'`{d}`' for d in missing)}."
    return "\n".join([lead, "", *table(["#", "Revision", "Revises", "Summary (first line of the docstring)"], rows,
                                       ["r", "l", "l", "l"])])


# --------------------------------------------------------------------------------------------------
# pod CI gates and recorded results
# --------------------------------------------------------------------------------------------------

@dataclass
class GateRow:
    name: str
    script: str
    description: str
    blocking: bool
    needs: tuple[str, ...]
    timeout: int


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except ValueError as exc:
        raise SyncError(f"{GATES_PY}: a Gate(...) argument is not a literal: {ast.dump(node)[:80]}") from exc


def read_gates(root: Path) -> tuple[list[GateRow], GateRow | None]:
    path = root / GATES_PY
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SyncError(f"cannot read {GATES_PY}") from exc

    def gate(call: ast.Call) -> GateRow:
        pos = [_literal(a) for a in call.args]
        kw = {k.arg: _literal(k.value) for k in call.keywords if k.arg}
        fields = dict(zip(("name", "script", "description", "blocking", "needs", "timeout"), pos, strict=False))
        fields.update(kw)
        return GateRow(fields["name"], fields["script"], fields["description"], bool(fields.get("blocking", True)),
                       tuple(fields.get("needs", ())), int(fields.get("timeout", 1800)))

    gates: list[GateRow] = []
    deploy = None
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        if target == "GATES" and isinstance(value, ast.Tuple):
            gates = [gate(e) for e in value.elts if isinstance(e, ast.Call)]
        elif target == "DEPLOY" and isinstance(value, ast.Call):
            deploy = gate(value)
    if not gates:
        raise SyncError(f"{GATES_PY}: no GATES tuple of Gate(...) calls")
    return gates, deploy


def read_gate_results(root: Path) -> list[dict[str, Any]]:
    path = root / GATE_RESULTS
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"{GATE_RESULTS}: {exc}") from exc
    runs = data.get("runs", []) if isinstance(data, dict) else []
    good = []
    for r in runs:
        if not isinstance(r, dict) or not r.get("commit") or not r.get("date") or not isinstance(r.get("gates"), dict):
            raise SyncError(f"{GATE_RESULTS}: every run needs commit, date and gates (got {str(r)[:80]})")
        good.append(r)
    return good


def gen_gates(ctx: Context) -> str:
    gates, deploy = ctx.memo("gates", lambda: read_gates(ctx.root))
    results = ctx.memo("gate-results", lambda: read_gate_results(ctx.root))
    latest: dict[str, dict[str, Any]] = {}
    for r in results:  # the newest run per place (pod / local)
        where = str(r.get("where", "pod"))
        if where not in latest or (r["date"], r["commit"]) > (latest[where]["date"], latest[where]["commit"]):
            latest[where] = r
    shown = [latest[w] for w in sorted(latest)]
    head = ["Gate", "Runs", "Blocking", "Needs"]
    head += [f"{r.get('where', 'pod').capitalize()} `{str(r['commit'])[:7]}` ({r['date']})" for r in shown]
    rows = []
    for g in [*gates, *([deploy] if deploy else [])]:
        row: list[object] = [f"`{g.name}`", g.description, "yes" if g.blocking else "no (report only)",
                             ", ".join(g.needs) or "-"]
        for r in shown:
            res = r["gates"].get(g.name)
            if isinstance(res, dict):
                res = res.get("result", "") + (f" ({res['note']})" if res.get("note") else "")
            row.append(shorten(str(res), 140) if res else "not recorded")
        rows.append(row)
    out = [f"{len(gates)} gates in {ctx.link(GATES_PY, '`podci/gates.py`')}, run in this order for every new commit; "
           f"`deploy` runs only on the deploy branch after every blocking gate is green."]
    if shown:
        sources = "; ".join(f"{r.get('where', 'pod')}: {r.get('source', 'recorded')}" for r in shown)
        out.append(f"Results with their commit and date from {ctx.link(GATE_RESULTS, '`gate-results.json`')} "
                   f"({sources}).")
    else:
        out.append(f"No recorded results ({GATE_RESULTS} does not exist): pod CI keeps its runs in SQLite on the pod "
                   f"(`/ci/` page); `sync_docs.py --record-podci` copies the last one here.")
    return "\n".join([*out, "", *table(head, rows)])


def record_podci(root: Path, db: Path, branch: str | None) -> dict[str, Any]:
    """The newest finished run (success / failure / error) of the pod CI SQLite store, into gate-results.json."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        q = "SELECT * FROM runs WHERE state IN ('success','failure','error') AND finished_at IS NOT NULL"
        args: tuple[str, ...] = ()
        if branch:
            q += " AND branch=?"
            args = (branch,)
        run = con.execute(q + " ORDER BY finished_at DESC, id DESC LIMIT 1", args).fetchone()
        if run is None:
            raise SyncError(f"{db}: no finished run" + (f" on {branch}" if branch else ""))
        steps = con.execute("SELECT * FROM steps WHERE run_id=? ORDER BY seq", (run["id"],)).fetchall()
    finally:
        con.close()
    finished = dt.datetime.fromtimestamp(float(run["finished_at"]), tz=dt.timezone.utc)
    entry = {
        "where": "pod",
        "branch": run["branch"],
        "commit": run["sha"],
        "date": finished.strftime("%Y-%m-%d %H:%M UTC"),
        "source": f"pod CI run #{run['id']} ({run['state']})",
        "gates": {s["name"]: s["state"] for s in steps},
    }
    path = root / GATE_RESULTS
    data: dict[str, Any] = {"runs": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    runs = [r for r in data.get("runs", []) if not (r.get("where") == "pod" and r.get("branch") == entry["branch"])]
    data["runs"] = [*runs, entry]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


# --------------------------------------------------------------------------------------------------
# agent registry
# --------------------------------------------------------------------------------------------------

def ledger_name(raw: str) -> str:
    name = re.split(r"\s+SCOPE\b|:\s", raw or "", maxsplit=1)[0].strip()
    return shorten(name, 60) or "(no ledger)"


def gen_agents(ctx: Context) -> str:
    try:
        agents = json.loads(ctx.read(REGISTRY)).get("agents", [])
    except json.JSONDecodeError as exc:
        raise SyncError(f"{REGISTRY}: {exc}") from exc
    counts = Counter(str(a.get("status", "unknown")) for a in agents)
    order = ["running", "finished", "stopped", "superseded"]
    states = [*order, *sorted(s for s in counts if s not in order)]
    summary = " · ".join(f"{s} {counts[s]}" for s in states if counts[s])
    running = sorted((a for a in agents if a.get("status") == "running"),
                     key=lambda a: (str(a.get("started_at") or ""), ledger_name(str(a.get("ledger", "")))))
    out = [f"{len(agents)} agents in {ctx.link(REGISTRY, '`docs/agents/registry.json`')}: {summary}."]
    if running:
        out += ["", *table(["Running ledger", "Agent type", "Started (UTC)"],
                           [[f"`{ledger_name(str(a.get('ledger', '')))}`", a.get("subagent_type", ""),
                             a.get("started_at", "")] for a in running])]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# languages
# --------------------------------------------------------------------------------------------------

def _flatten(d: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    else:
        out[prefix[:-1]] = d
    return out


def _module_tuple(root: Path, rel: str, name: str) -> tuple[str, ...]:
    tree = ast.parse((root / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        if target == name and value is not None:
            return tuple(str(v) for v in _literal(value))
    raise SyncError(f"{rel}: no literal {name}")


def gen_languages(ctx: Context) -> str:
    backend = _module_tuple(ctx.root, BOOKINGS_I18N, "SHIPPED_LANGUAGES")
    m = re.search(r"export const LOCALES = \[([^\]]*)\]", ctx.read(FRONTEND_I18N))
    if not m:
        raise SyncError(f"{FRONTEND_I18N}: no `export const LOCALES = [...]`")
    frontend = tuple(re.findall(r"[\"']([a-z-]+)[\"']", m.group(1)))
    catalogues = sorted(p.stem for p in ctx.path(MESSAGES).glob("*.json"))
    try:
        en = _flatten(json.loads(ctx.read(f"{MESSAGES}/en.json")))
    except json.JSONDecodeError as exc:
        raise SyncError(f"{MESSAGES}/en.json: {exc}") from exc
    names = {"tr": "Turkish", "en": "English"}
    rows = []
    for code in dict.fromkeys([*backend, *frontend]):
        if code == "en":
            state = "source catalogue"
        elif code in catalogues:
            other = _flatten(json.loads(ctx.read(f"{MESSAGES}/{code}.json")))
            missing = [k for k in en if not isinstance(other.get(k), str) or not other.get(k, "").strip()]
            state = "complete (a value for every English key)" if not missing else f"{len(missing)} keys missing"
        else:
            state = "no catalogue"
        rows.append([f"{names.get(code, code)} (`{code}`)", "yes" if code in backend else "no",
                     "yes" if code in frontend else "no", state])
    legacy = [c for c in catalogues if c not in backend and c not in frontend]
    out = [*table(["Language", "Backend offers", "Frontend offers", "Message catalogue"], rows)]
    if legacy:
        out += ["", f"Not offered (owner decision 2026-10-15: Turkish and English only): {' '.join(legacy)}. Their "
                f"catalogues stay in {ctx.link(MESSAGES, '`messages/`')}; a stored code is kept and shown in English."]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# intake formats (council registry)
# --------------------------------------------------------------------------------------------------

def _num(node: ast.AST, names: dict[str, int]) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult | ast.Add | ast.Sub | ast.FloorDiv):
        a, b = _num(node.left, names), _num(node.right, names)
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        return a // b
    raise SyncError(f"formats: not a number expression: {ast.dump(node)[:80]}")


def _size(n: int) -> str:
    mib = 1024 * 1024
    return f"{n // mib} MiB" if n % mib == 0 else f"{n:,} bytes"


def read_formats(root: Path) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    base = root / COUNCIL
    core = ast.parse((base / "formats.py").read_text(encoding="utf-8"))
    names: dict[str, int] = {}
    defaults: dict[str, int] = {}
    for node in core.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                names[node.targets[0].id] = _num(node.value, names)
            except SyncError:
                pass
        if isinstance(node, ast.ClassDef) and node.name == "FormatLimits":
            for f in node.body:
                if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name) and f.value is not None:
                    defaults[f.target.id] = _num(f.value, names)
    if "max_bytes" not in defaults:
        raise SyncError(f"{COUNCIL}/formats.py: no FormatLimits.max_bytes default")
    specs: list[dict[str, Any]] = []
    unsupported: list[tuple[str, str]] = []
    for path in sorted(base.glob("formats_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        local = dict(names)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args):
                continue
            inner = node.args[0]
            if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)):
                continue
            if node.func.id == "register" and inner.func.id == "FormatSpec":
                fields = dict(zip(("name", "label", "family", "extensions", "route", "sniff", "render", "limits",
                                   "precheck"), inner.args, strict=False))
                fields.update({k.arg: k.value for k in inner.keywords if k.arg})
                limits = dict(defaults)
                lim = fields.get("limits")
                if isinstance(lim, ast.Call):
                    limits.update({k.arg: _num(k.value, local) for k in lim.keywords if k.arg})
                specs.append({
                    "name": _literal(fields["name"]), "label": _literal(fields["label"]),
                    "extensions": tuple(_literal(fields["extensions"])), "route": _literal(fields["route"]),
                    "limits": limits, "changed": {k: v for k, v in limits.items() if defaults.get(k) != v},
                    "file": path.name,
                })
            elif node.func.id == "register_unsupported" and inner.func.id == "Unsupported":
                hint = inner.args[2] if len(inner.args) > 2 else next(
                    (k.value for k in inner.keywords if k.arg == "hint"), None)
                unsupported.append((_literal(inner.args[0]), _literal(hint) if hint is not None else ""))
    if not specs:
        raise SyncError(f"{COUNCIL}: no register(FormatSpec(...)) entries")
    return specs, unsupported


def gen_formats(ctx: Context) -> str:
    specs, unsupported = ctx.memo("formats", lambda: read_formats(ctx.root))
    routes = {"structured": "structured: read on the server, no AI",
              "ai": "AI-assisted: off by default; every row reviewed"}
    ordered = sorted(specs, key=lambda s: (s["route"] != "structured",))
    rows = []
    for s in ordered:
        sheet = [f"{k.removeprefix('max_')} {v:,}" for k, v in sorted(s["changed"].items()) if k != "max_bytes"]
        rows.append([f"`{s['name']}`", s["label"], " ".join(s["extensions"]), routes.get(s["route"], s["route"]),
                     _size(s["limits"]["max_bytes"]) + (f"; {', '.join(sheet)}" if sheet else ""),
                     f"`{s['file']}`"])
    out = [f"{len(specs)} formats registered in {ctx.link(COUNCIL, '`app/council/formats*.py`')}, detected by magic "
           f"bytes first (the extension only breaks ties). Limits not listed are the `FormatLimits` defaults.", ""]
    out += table(["Format", "Label", "Extensions", "Route", "Limit", "Registered in"], rows)
    if unsupported:
        out += ["", "Recognised but refused, with a hint: " + "; ".join(f"`{n}` ({h})" for n, h in unsupported) + "."]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------
# last-updated (git)
# --------------------------------------------------------------------------------------------------

def git_head(root: Path) -> tuple[str, str] | None:
    try:
        res = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%H%x09%ct"], capture_output=True,
                             text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0 or "\t" not in res.stdout:
        return None
    sha, ts = res.stdout.strip().split("\t", 1)
    when = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return sha[:7], when


def gen_last_updated(ctx: Context) -> str | None:
    head = ctx.memo("git-head", lambda: git_head(ctx.root))
    if head is None:
        return None  # no git (exported tree): keep the block as it is
    sha, when = head
    return (f"Generated blocks last synced on top of commit `{sha}` (committed {when}) by "
            f"`python3 -I scripts/docs/sync_docs.py`.")


# --------------------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------------------

GENERATORS: dict[str, Callable[[Context], str | None]] = {
    "status": gen_status,
    "roadmap": gen_roadmap,
    "decisions": gen_decisions,
    "parity": gen_parity,
    "migrations": gen_migrations,
    "gates": gen_gates,
    "agents": gen_agents,
    "languages": gen_languages,
    "formats": gen_formats,
    "last-updated": gen_last_updated,
}
VOLATILE = frozenset({"last-updated"})


@dataclass
class FileResult:
    path: Path
    old: str
    new: str
    blocks: list[Block]
    stale: list[str]


def render_text(text: str, ctx: Context, where: str = "<text>") -> tuple[str, list[Block], list[str]]:
    """The text with every block regenerated, its blocks, and the labels of the non-volatile stale ones."""
    lines, blocks = parse_blocks(text, where)
    if not blocks:
        return text, blocks, []
    nl = newline_of(lines)
    out: list[str] = []
    stale: list[str] = []
    pos = 0
    for b in blocks:
        gen = GENERATORS.get(b.name)
        if gen is None:
            raise SyncError(f"{where}:{b.start + 1}: unknown block AUTO:{b.name} (known: {', '.join(GENERATORS)})")
        out += lines[pos:b.start + 1]
        ctx.args = dict(b.args)
        content = gen(ctx)
        if content is None:
            body = b.body
        else:
            body = (nl.join(content.strip("\n").split("\n")) + nl) if content.strip() else ""
        if body != b.body and b.name not in VOLATILE:
            stale.append(b.label)
        out.append(body)
        pos = b.end
    out += lines[pos:]
    return "".join(out), blocks, stale


def markdown_files(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".") or d == ".github")
        for fn in filenames:
            if fn.endswith(".md"):
                found.append(Path(dirpath) / fn)
    return sorted(found)


def process(root: Path, files: list[Path] | None = None) -> list[FileResult]:
    cache: dict[str, Any] = {}
    results = []
    for path in files if files is not None else markdown_files(root):
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        if "AUTO:" not in text:
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        ctx = Context(root=root, target=path, cache=cache)
        new, blocks, stale = render_text(text, ctx, rel)
        if blocks:
            results.append(FileResult(path, text, new, blocks, stale))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sync_docs.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 when a block is stale; write nothing")
    mode.add_argument("--list", action="store_true", help="list the blocks per file and their state")
    mode.add_argument("--record-podci", metavar="DB", type=Path,
                      help="copy the newest finished run of the pod CI SQLite store into " + GATE_RESULTS)
    ap.add_argument("--diff", action="store_true", help="with --check: print a unified diff of the stale files")
    ap.add_argument("--branch", help="with --record-podci: the branch (default: the newest run of any branch)")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this script's repository)")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    try:
        if a.record_podci:
            entry = record_podci(root, a.record_podci, a.branch)
            print(f"recorded {entry['source']} {entry['branch']}@{entry['commit'][:7]} into {GATE_RESULTS}")
            return 0
        results = process(root)
    except SyncError as exc:
        print(f"sync_docs: {exc}", file=sys.stderr)
        return 2
    if a.list:
        for r in results:
            print(r.path.relative_to(root).as_posix())
            stale = set(r.stale)
            for b in r.blocks:
                state = "volatile" if b.name in VOLATILE else ("STALE" if b.label in stale else "ok")
                print(f"  {b.label:<28} lines {b.start + 1}-{b.end + 1}  {state}")
        if not results:
            print("no AUTO blocks found")
        return 0
    if a.check:
        stale_files = [r for r in results if r.stale]
        for r in stale_files:
            print(f"STALE {r.path.relative_to(root).as_posix()}: {', '.join(r.stale)}")
            if a.diff:
                rel = r.path.relative_to(root).as_posix()
                sys.stdout.writelines(difflib.unified_diff(r.old.splitlines(True), r.new.splitlines(True),
                                                           f"a/{rel}", f"b/{rel}"))
        if stale_files:
            print("docs are stale: run `python3 -I scripts/docs/sync_docs.py` and commit the result")
            return 1
        blocks = sum(len(r.blocks) for r in results)
        print(f"docs up to date ({blocks} blocks in {len(results)} files)")
        return 0
    changed = 0
    for r in results:
        if r.new != r.old:
            with r.path.open("w", encoding="utf-8", newline="") as fh:
                fh.write(r.new)
            changed += 1
            what = ", ".join(r.stale) or "last-updated"
            print(f"updated {r.path.relative_to(root).as_posix()}: {what}")
    print(f"{changed} of {len(results)} files with AUTO blocks updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
