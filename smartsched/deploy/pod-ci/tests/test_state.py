"""Job state machine (SQLite): transitions, supersede, restart recovery, persistence."""

from __future__ import annotations

import pytest
from podfakes import SHA_A, SHA_B, SHA_C, Clock

from podci.config import Config
from podci.state import (
    ERROR,
    FAILURE,
    QUEUED,
    RUNNING,
    SUCCESS,
    SUPERSEDED,
    InvalidTransition,
    Store,
)


def test_happy_path_and_timestamps(store: Store, clock: Clock) -> None:
    run = store.enqueue("main", SHA_A, deploy=True)
    assert run and run.state == QUEUED and run.deploy
    clock.advance(5)
    run = store.transition(run.id, RUNNING)
    assert run.attempts == 1 and run.started_at == clock.t
    clock.advance(65)
    run = store.transition(run.id, SUCCESS, summary="ok")
    assert run.duration == 65 and run.summary == "ok"


@pytest.mark.parametrize(("start", "bad"), [(QUEUED, SUCCESS), (QUEUED, FAILURE), (SUCCESS, RUNNING),
                                            (SUPERSEDED, RUNNING)])
def test_invalid_transitions(store: Store, start: str, bad: str) -> None:
    run = store.enqueue("main", SHA_A, deploy=False)
    assert run
    if start == SUCCESS:
        store.transition(run.id, RUNNING)
        store.transition(run.id, SUCCESS)
    elif start == SUPERSEDED:
        store.transition(run.id, SUPERSEDED)
    with pytest.raises(InvalidTransition):
        store.transition(run.id, bad)


def test_duplicate_commit_is_not_queued_twice(store: Store) -> None:
    assert store.enqueue("main", SHA_A, deploy=False)
    assert store.enqueue("main", SHA_A, deploy=False) is None
    assert store.enqueue("other", SHA_A, deploy=False)  # same sha on another branch is its own run


def test_supersede_only_queued_runs_of_that_branch(store: Store) -> None:
    a = store.enqueue("main", SHA_A, deploy=True)
    b = store.enqueue("main", SHA_B, deploy=True)
    other = store.enqueue("feature", SHA_A, deploy=False)
    assert a and b and other
    store.transition(a.id, RUNNING)  # running runs finish; only queued ones are superseded
    c = store.enqueue("main", SHA_C, deploy=True)
    assert c
    gone = store.supersede_older("main", c.id)
    assert [r.id for r in gone] == [b.id]
    assert store.get(b.id).state == SUPERSEDED  # type: ignore[union-attr]
    assert store.get(a.id).state == RUNNING  # type: ignore[union-attr]
    assert store.get(other.id).state == QUEUED  # type: ignore[union-attr]


def test_next_queued_prefers_deploy_branch_then_fifo(store: Store) -> None:
    f = store.enqueue("feature", SHA_A, deploy=False)
    d = store.enqueue("main", SHA_B, deploy=True)
    assert f and d
    assert store.next_queued().id == d.id  # type: ignore[union-attr]
    store.transition(d.id, RUNNING)
    assert store.next_queued().id == f.id  # type: ignore[union-attr]


def test_restart_recovery_requeues_then_errors(cfg: Config, clock: Clock) -> None:
    s1 = Store(cfg.db_path, clock=clock)
    run = s1.enqueue("main", SHA_A, deploy=True)
    assert run
    s1.transition(run.id, RUNNING)
    s1.add_steps(run.id, [("backend", True)])
    s1.step_transition(run.id, "backend", "running", log_path="/x")
    del s1  # worker killed mid-run
    s2 = Store(cfg.db_path, clock=clock)  # state survives in SQLite
    requeued, failed = s2.recover_interrupted(max_attempts=2)
    assert [r.id for r in requeued] == [run.id] and not failed
    assert s2.get(run.id).state == QUEUED and s2.steps(run.id) == []  # type: ignore[union-attr]
    s2.transition(run.id, RUNNING)  # attempt 2, killed again
    requeued, failed = Store(cfg.db_path, clock=clock).recover_interrupted(max_attempts=2)
    assert not requeued and [r.id for r in failed] == [run.id]
    assert s2.get(run.id).state == ERROR  # type: ignore[union-attr]


def test_rerun_resets_a_finished_run(store: Store) -> None:
    run = store.enqueue("main", SHA_A, deploy=False)
    assert run
    with pytest.raises(InvalidTransition):
        store.rerun(run.id)
    store.transition(run.id, RUNNING)
    store.add_steps(run.id, [("backend", True)])
    store.transition(run.id, FAILURE)
    again = store.rerun(run.id)
    assert again.state == QUEUED and again.attempts == 0 and store.steps(run.id) == []


def test_step_state_machine(store: Store) -> None:
    run = store.enqueue("main", SHA_A, deploy=False)
    assert run
    store.add_steps(run.id, [("a", True), ("b", False)])
    with pytest.raises(InvalidTransition):
        store.step_transition(run.id, "a", SUCCESS)  # must run first
    store.step_transition(run.id, "a", "running", log_path="/tmp/a.log")
    st = store.step_transition(run.id, "a", SUCCESS, exit_code=0)
    assert st.exit_code == 0 and st.log_path == "/tmp/a.log"
    assert store.step_transition(run.id, "b", "skipped").state == "skipped"
    assert [s.name for s in store.steps(run.id)] == ["a", "b"]


def test_old_runs_pruned_keep_newest(store: Store) -> None:
    ids = []
    for i in range(5):
        r = store.enqueue("main", f"{i:040x}", deploy=False)
        assert r
        store.transition(r.id, RUNNING)
        store.transition(r.id, SUCCESS)
        ids.append(r.id)
    assert store.old_run_ids(keep=2) == ids[:3][::-1]


def test_cpu_window(store: Store) -> None:
    store.add_cpu_sample(100, 10, 1000, keep_seconds=10_000)
    store.add_cpu_sample(200, 20, 2000, keep_seconds=10_000)
    assert store.cpu_window(150) == ((100, 10, 1000), (200, 20, 2000))
    assert store.cpu_window(50) is None  # history shorter than the window
