"""Run state in SQLite (WAL) under /var/lib/smartsched-ci: runs, steps, branch heads, CPU samples.

Run state machine (anything else raises InvalidTransition):

    queued  -> running | superseded | cancelled
    running -> success | failure | error | queued (requeued after an interrupted worker, max_attempts)
    success/failure/error/superseded/cancelled -> queued   (explicit `rerun` only)

Step states: pending -> running -> success | failure | error;  pending -> skipped.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

QUEUED, RUNNING, SUCCESS, FAILURE, ERROR, SUPERSEDED, CANCELLED = (
    "queued", "running", "success", "failure", "error", "superseded", "cancelled")
TERMINAL = frozenset({SUCCESS, FAILURE, ERROR, SUPERSEDED, CANCELLED})
TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({RUNNING, SUPERSEDED, CANCELLED}),
    RUNNING: frozenset({SUCCESS, FAILURE, ERROR, QUEUED}),
    **{t: frozenset() for t in TERMINAL},
}
STEP_PENDING, STEP_RUNNING, STEP_SKIPPED = "pending", "running", "skipped"
STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    STEP_PENDING: frozenset({STEP_RUNNING, STEP_SKIPPED}),
    STEP_RUNNING: frozenset({SUCCESS, FAILURE, ERROR}),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT NOT NULL,
    sha TEXT NOT NULL,
    state TEXT NOT NULL,
    deploy INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    summary TEXT NOT NULL DEFAULT '',
    UNIQUE (branch, sha)
);
CREATE INDEX IF NOT EXISTS runs_state ON runs (state, id);
CREATE TABLE IF NOT EXISTS steps (
    run_id INTEGER NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    blocking INTEGER NOT NULL DEFAULT 1,
    started_at REAL,
    finished_at REAL,
    exit_code INTEGER,
    log_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, name)
);
CREATE TABLE IF NOT EXISTS heads (branch TEXT PRIMARY KEY, sha TEXT NOT NULL, seen_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS cpu_samples (ts REAL PRIMARY KEY, busy REAL NOT NULL, total REAL NOT NULL);
"""


class InvalidTransition(RuntimeError):
    pass


def _must[T](value: T | None, what: str) -> T:
    if value is None:
        raise InvalidTransition(f"{what} vanished")
    return value


@dataclass(frozen=True)
class Run:
    id: int
    branch: str
    sha: str
    state: str
    deploy: bool
    attempts: int
    created_at: float
    started_at: float | None
    finished_at: float | None
    summary: str

    @property
    def short(self) -> str:
        return self.sha[:7]

    @property
    def duration(self) -> float | None:
        if self.started_at is None:
            return None
        return (self.finished_at or time.time()) - self.started_at


@dataclass(frozen=True)
class Step:
    run_id: int
    seq: int
    name: str
    state: str
    blocking: bool
    started_at: float | None
    finished_at: float | None
    exit_code: int | None
    log_path: str

    @property
    def duration(self) -> float | None:
        if self.started_at is None:
            return None
        return (self.finished_at or time.time()) - self.started_at


class Store:
    def __init__(self, path: Path | str, clock: object = time.time):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.executescript(SCHEMA)

    def now(self) -> float:
        return float(self.clock())  # type: ignore[operator]

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # ---- runs ---------------------------------------------------------------------------------
    @staticmethod
    def _run(row: sqlite3.Row | None) -> Run | None:
        if row is None:
            return None
        return Run(id=row["id"], branch=row["branch"], sha=row["sha"], state=row["state"], deploy=bool(row["deploy"]),
                   attempts=row["attempts"], created_at=row["created_at"], started_at=row["started_at"],
                   finished_at=row["finished_at"], summary=row["summary"])

    def get(self, run_id: int) -> Run | None:
        return self._run(self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def find(self, branch: str, sha: str) -> Run | None:
        return self._run(self.db.execute("SELECT * FROM runs WHERE branch=? AND sha=?", (branch, sha)).fetchone())

    def enqueue(self, branch: str, sha: str, deploy: bool) -> Run | None:
        """New queued run, or None when this (branch, sha) is already known."""
        with self.tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO runs (branch, sha, state, deploy, created_at) VALUES (?,?,?,?,?)",
                             (branch, sha, QUEUED, int(deploy), self.now()))
            if cur.rowcount == 0:
                return None
            run_id = cur.lastrowid
        return self.get(int(run_id or 0))

    def supersede_older(self, branch: str, newer_id: int) -> list[Run]:
        """Queued (not yet running) runs of the branch older than newer_id -> superseded."""
        rows = self.db.execute("SELECT * FROM runs WHERE branch=? AND state=? AND id<?", (branch, QUEUED, newer_id))
        out = []
        for row in rows.fetchall():
            run = _must(self._run(row), "run")
            self.transition(run.id, SUPERSEDED, summary=f"superseded by a newer commit (run #{newer_id})")
            out.append(run)
        return out

    def transition(self, run_id: int, new: str, summary: str | None = None) -> Run:
        with self.tx() as db:
            row = db.execute("SELECT state, attempts FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise InvalidTransition(f"run {run_id} does not exist")
            cur = row["state"]
            if new not in TRANSITIONS[cur]:
                raise InvalidTransition(f"run {run_id}: {cur} -> {new} is not allowed")
            now = self.now()
            sets = ["state=?"]
            args: list[object] = [new]
            if new == RUNNING:
                sets += ["started_at=?", "finished_at=NULL", "attempts=attempts+1"]
                args.append(now)
            elif new in TERMINAL:
                sets.append("finished_at=?")
                args.append(now)
            if summary is not None:
                sets.append("summary=?")
                args.append(summary)
            db.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", (*args, run_id))  # noqa: S608
        return _must(self.get(run_id), f"run {run_id}")

    def rerun(self, run_id: int) -> Run:
        """Explicit operator re-run of a finished run (fresh steps, attempts reset)."""
        run = self.get(run_id)
        if run is None or run.state not in TERMINAL:
            raise InvalidTransition(f"run {run_id} is not finished")
        with self.tx() as db:
            db.execute("DELETE FROM steps WHERE run_id=?", (run_id,))
            db.execute("UPDATE runs SET state=?, attempts=0, started_at=NULL, finished_at=NULL, summary='' "
                       "WHERE id=?", (QUEUED, run_id))
        return _must(self.get(run_id), f"run {run_id}")

    def next_queued(self, deploy_first: bool = True) -> Run | None:
        order = "deploy DESC, id ASC" if deploy_first else "id ASC"
        return self._run(self.db.execute(f"SELECT * FROM runs WHERE state=? ORDER BY {order} LIMIT 1",  # noqa: S608
                                         (QUEUED,)).fetchone())

    def recover_interrupted(self, max_attempts: int) -> tuple[list[Run], list[Run]]:
        """Runs left 'running' by a dead worker: requeue (attempts left) or fail. Returns (requeued, failed)."""
        requeued, failed = [], []
        for row in self.db.execute("SELECT * FROM runs WHERE state=?", (RUNNING,)).fetchall():
            run = _must(self._run(row), "run")
            self.db.execute("UPDATE steps SET state=?, finished_at=? WHERE run_id=? AND state=?",
                            (ERROR, self.now(), run.id, STEP_RUNNING))
            if run.attempts < max_attempts:
                self.db.execute("DELETE FROM steps WHERE run_id=?", (run.id,))
                requeued.append(self.transition(run.id, QUEUED, summary="requeued after an interrupted worker"))
            else:
                failed.append(self.transition(run.id, ERROR, summary=f"interrupted {run.attempts} times"))
        return requeued, failed

    def recent(self, limit: int = 50) -> list[Run]:
        rows = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [r for r in (self._run(x) for x in rows) if r is not None]

    def active(self) -> bool:
        row = self.db.execute("SELECT COUNT(*) FROM runs WHERE state IN (?,?)", (QUEUED, RUNNING)).fetchone()
        return bool(row[0])

    def running(self) -> bool:
        return bool(self.db.execute("SELECT COUNT(*) FROM runs WHERE state=?", (RUNNING,)).fetchone()[0])

    def last_finished_at(self) -> float | None:
        row = self.db.execute("SELECT MAX(finished_at) FROM runs").fetchone()
        return None if row[0] is None else float(row[0])

    def old_run_ids(self, keep: int) -> list[int]:
        rows = self.db.execute("SELECT id FROM runs WHERE state IN (?,?,?,?,?) ORDER BY id DESC LIMIT -1 OFFSET ?",
                               (*sorted(TERMINAL), keep)).fetchall()
        return [int(r[0]) for r in rows]

    def delete_runs(self, ids: list[int]) -> None:
        with self.tx() as db:
            db.executemany("DELETE FROM runs WHERE id=?", [(i,) for i in ids])

    # ---- steps --------------------------------------------------------------------------------
    @staticmethod
    def _step(row: sqlite3.Row) -> Step:
        return Step(run_id=row["run_id"], seq=row["seq"], name=row["name"], state=row["state"],
                    blocking=bool(row["blocking"]), started_at=row["started_at"], finished_at=row["finished_at"],
                    exit_code=row["exit_code"], log_path=row["log_path"])

    def add_steps(self, run_id: int, steps: list[tuple[str, bool]]) -> None:
        with self.tx() as db:
            for seq, (name, blocking) in enumerate(steps):
                db.execute("INSERT OR REPLACE INTO steps (run_id, seq, name, state, blocking) VALUES (?,?,?,?,?)",
                           (run_id, seq, name, STEP_PENDING, int(blocking)))

    def steps(self, run_id: int) -> list[Step]:
        rows = self.db.execute("SELECT * FROM steps WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [self._step(r) for r in rows]

    def step(self, run_id: int, name: str) -> Step | None:
        row = self.db.execute("SELECT * FROM steps WHERE run_id=? AND name=?", (run_id, name)).fetchone()
        return None if row is None else self._step(row)

    def step_transition(self, run_id: int, name: str, new: str, exit_code: int | None = None,
                        log_path: str | None = None) -> Step:
        cur = self.step(run_id, name)
        if cur is None:
            raise InvalidTransition(f"step {name} of run {run_id} does not exist")
        if new not in STEP_TRANSITIONS.get(cur.state, frozenset()):
            raise InvalidTransition(f"step {name}: {cur.state} -> {new} is not allowed")
        now = self.now()
        if new == STEP_RUNNING:
            self.db.execute("UPDATE steps SET state=?, started_at=?, log_path=COALESCE(?, log_path) "
                            "WHERE run_id=? AND name=?", (new, now, log_path, run_id, name))
        else:
            self.db.execute("UPDATE steps SET state=?, finished_at=?, exit_code=? WHERE run_id=? AND name=?",
                            (new, now if new != STEP_SKIPPED else None, exit_code, run_id, name))
        return _must(self.step(run_id, name), f"step {name}")

    # ---- heads --------------------------------------------------------------------------------
    def head(self, branch: str) -> str | None:
        row = self.db.execute("SELECT sha FROM heads WHERE branch=?", (branch,)).fetchone()
        return None if row is None else str(row[0])

    def set_head(self, branch: str, sha: str) -> None:
        self.db.execute("INSERT INTO heads (branch, sha, seen_at) VALUES (?,?,?) "
                        "ON CONFLICT(branch) DO UPDATE SET sha=excluded.sha, seen_at=excluded.seen_at",
                        (branch, sha, self.now()))

    # ---- CPU samples (idle detection) -----------------------------------------------------------
    def add_cpu_sample(self, ts: float, busy: float, total: float, keep_seconds: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO cpu_samples (ts, busy, total) VALUES (?,?,?)", (ts, busy, total))
        self.db.execute("DELETE FROM cpu_samples WHERE ts < ?", (ts - keep_seconds,))

    def cpu_window(self, since: float) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        """(oldest sample at or before `since`, newest sample) or None when history is shorter."""
        first = self.db.execute("SELECT ts, busy, total FROM cpu_samples WHERE ts<=? ORDER BY ts DESC LIMIT 1",
                                (since,)).fetchone()
        last = self.db.execute("SELECT ts, busy, total FROM cpu_samples ORDER BY ts DESC LIMIT 1").fetchone()
        if first is None or last is None or last[0] <= first[0]:
            return None
        return (tuple(first), tuple(last))  # type: ignore[return-value]
