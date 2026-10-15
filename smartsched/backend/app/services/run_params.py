"""Server-side policy for ``ScheduleRun.params`` (review B3 / M13).

* :func:`clean_client_params` whitelists and bounds what a client may put into ``POST /runs``
  ``params`` (time limit, workers, seed, weights, solver choice, real-data mode switches). Reserved
  keys (``studio`` and its seal, ``draft_id``) and unknown keys answer 422: a PLANNER must not be able to
  smuggle a draft snapshot that switches ADMIN-only built-in hard rules off.
* :func:`seal_studio` / :func:`trusted_studio_snapshot`: ``params["studio"]`` is honoured only when it
  carries an HMAC seal written by :func:`app.services.studio.generate` (the seal survives the
  server-side copies made for child runs: diagnosis fixes, chat edits).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

#: keys only the server may write
RESERVED_KEYS = frozenset({"studio", "studio_sig", "draft_id"})
#: keys a moderation re-solve writes (``app/services/moderation.py``): the re-solve's scope and the coordinator's
#: unlocks on a draft child run (``solver_bridge.UNLOCK_PARAM``); a client cannot set them through ``POST /runs``
MODERATION_KEYS = frozenset({"moderation", "unlock_request_ids"})
#: owner decision 2026-10-15: a run meant for publishing is solved with one CP-SAT worker, so re-running it gives
#: the identical schedule (``solver_bridge.solver_workers``); moderation re-solves always are
PUBLISH_CANDIDATE = "publish_candidate"
BOOL_KEYS = frozenset(
    {
        "trust_locked_rooms",
        "fixed_conflicts_as_warnings",
        "best_effort",
        "merge_joint_lectures",
        "split_blocked_weeks",
        "split_large_classes",
        "strict_horizon",
        "stability",
        PUBLISH_CANDIDATE,
        # "AI backlog finished" decision: a child run inherits its ancestors' run-scoped rules unless this is false
        "inherit_run_rules",
    }
)
#: run solvers a client may choose (the greedy stub is a test helper, not a run option: audit M1)
SOLVERS = ("auto", "cpsat")
DEFINITIVE = ("lock", "prefer", "ignore")
MAX_WEIGHT = 10_000
MAX_WEIGHT_KEYS = 50
MAX_BLOCK_RUNS = 20
#: relaxation policies (``app/solver/policy.py``; user decision 2026-10-15, ``lock_first`` is the default)
RELAXATION_POLICIES = ("lock_first", "most_classes_first")
DEFAULT_RELAXATION_POLICY = "lock_first"
#: coordinator priorities of one run: ``{"<request id>": int}`` (higher wins; ``app.solver.policy`` bounds)
MAX_PRIORITY_KEYS = 20_000
PRIORITY_RANGE = (-100, 100)


class ParamError(ValueError):
    """422 for ``POST /runs``."""


def _num(value: Any, key: str, lo: float, hi: float, *, integer: bool) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ParamError(f"params.{key} must be a number")
    if not lo <= value <= hi:
        raise ParamError(f"params.{key} must be within {lo:g}..{hi:g}")
    return int(value) if integer else float(value)


def bounds() -> dict[str, tuple[float, float]]:
    s = get_settings()
    return {
        "time_limit_s": (1.0, float(s.solver_max_time_limit)),
        "workers": (1, int(s.solver_max_workers)),
        "seed": (0, 2**31 - 1),
    }


def clean_client_params(params: dict[str, Any]) -> dict[str, Any]:
    """Validated copy of client-supplied run params; raises :class:`ParamError` (422)."""
    reserved = sorted(set(params) & RESERVED_KEYS)
    if reserved:
        raise ParamError(
            f"params {reserved} are reserved (studio runs are created by POST /terms/{{id}}/studio/generate)"
        )
    moderation = sorted(set(params) & MODERATION_KEYS)
    if moderation:
        raise ParamError(
            f"params {moderation} are reserved "
            "(moderation re-solves are created by POST /terms/{id}/moderation/resolve)"
        )
    b = bounds()
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key == "time_limit_s":
            out[key] = _num(value, key, *b[key], integer=False)
        elif key in ("workers", "seed"):
            out[key] = _num(value, key, *b[key], integer=True)
        elif key == "split_max_rooms":  # R4: rooms one large class may be split over (solver_bridge)
            out[key] = _num(value, key, 1, 8, integer=True)
        elif key == "solver":
            if value not in SOLVERS:
                raise ParamError(f"params.solver must be one of {SOLVERS}")
            out[key] = value
        elif key == "definitive_rooms":
            if value not in DEFINITIVE:
                raise ParamError(f"params.definitive_rooms must be one of {DEFINITIVE}")
            out[key] = value
        elif key in BOOL_KEYS:
            if not isinstance(value, bool):
                raise ParamError(f"params.{key} must be true or false")
            out[key] = value
        elif key == "weights":
            if not isinstance(value, dict) or len(value) > MAX_WEIGHT_KEYS:
                raise ParamError(f"params.weights must be an object with at most {MAX_WEIGHT_KEYS} entries")
            w: dict[str, int] = {}
            for wk, wv in value.items():
                if not isinstance(wk, str) or not 0 < len(wk) <= 64:
                    raise ParamError("params.weights keys must be names of at most 64 characters")
                w[wk] = int(_num(wv, f"weights.{wk}", 0, MAX_WEIGHT, integer=True))
            out[key] = w
        elif key == "relaxation_policy":
            if value not in RELAXATION_POLICIES:
                raise ParamError(f"params.relaxation_policy must be one of {RELAXATION_POLICIES}")
            out[key] = value
        elif key == "priorities":
            out[key] = clean_priorities(value)
        elif key == "block_run_ids":
            if not isinstance(value, list) or len(value) > MAX_BLOCK_RUNS:
                raise ParamError(f"params.block_run_ids must be a list of at most {MAX_BLOCK_RUNS} run ids")
            out[key] = [int(_num(v, key, 1, 2**31 - 1, integer=True)) for v in value]
        else:
            raise ParamError(f"unknown run param {key!r}")
    if out.get(PUBLISH_CANDIDATE):
        out["workers"] = 1
    return out


def deterministic_run(params: dict[str, Any] | None) -> bool:
    """True for a publish candidate or a moderation re-solve: solved with ``workers=1`` (owner decision)."""
    p = params or {}
    return bool(p.get(PUBLISH_CANDIDATE)) or isinstance(p.get("moderation"), dict)


def clean_priorities(value: Any) -> dict[str, int]:
    """``{"<request id>": priority}`` (meeting / exam request ids of the run's term, higher wins).

    P19-M2: the coordinator's priority is stored on ``sections.priority`` / ``meeting_requests.priority``
    (``PUT /moderation/sections|requests/{id}/priority``) and read by the bridge; this run param still overrides
    it per request, for experiments and counterfactual runs."""
    if not isinstance(value, dict) or len(value) > MAX_PRIORITY_KEYS:
        raise ParamError(f"params.priorities must be an object of at most {MAX_PRIORITY_KEYS} request ids")
    lo, hi = PRIORITY_RANGE
    out: dict[str, int] = {}
    for k, v in value.items():
        if not str(k).isdigit() or int(str(k)) <= 0:
            raise ParamError("params.priorities keys must be request ids")
        out[str(int(str(k)))] = int(_num(v, f"priorities.{k}", lo, hi, integer=True))
    return out


# --------------------------------------------------------------------------- per-term relaxation policy

#: the per-term setting (``settings`` table, the dotted ``term.<id>.*`` namespace; admins write it with
#: ``PUT /settings {"extra": {"term.<id>.relaxation_policy": "most_classes_first"}}`` or
#: :func:`set_term_relaxation_policy`)
TERM_POLICY_KEY = "term.{term_id}.relaxation_policy"


def term_policy_key(term_id: int) -> str:
    return TERM_POLICY_KEY.format(term_id=int(term_id))


async def term_relaxation_policy(session: Any, term_id: int) -> tuple[str, str]:
    """``(policy, source)`` of a term: the stored setting (``term``), or the default (``default``; also when
    the stored value is not a policy name — ``source`` is then ``invalid_setting``)."""
    from app.services.settings_service import get_value

    value = await get_value(session, term_policy_key(term_id))
    if value is None or value == "":
        return DEFAULT_RELAXATION_POLICY, "default"
    if value in RELAXATION_POLICIES:
        return str(value), "term"
    return DEFAULT_RELAXATION_POLICY, "invalid_setting"


async def set_term_relaxation_policy(session: Any, term_id: int, policy: str | None) -> None:
    """Store (or with ``None`` clear) the term's policy; raises :class:`ParamError` for an unknown name."""
    from app.services.settings_service import set_value

    if policy is not None and policy not in RELAXATION_POLICIES:
        raise ParamError(f"relaxation_policy must be one of {RELAXATION_POLICIES}")
    await set_value(session, term_policy_key(term_id), policy)


async def effective_relaxation_policy(session: Any, term_id: int, params: dict[str, Any] | None) -> tuple[str, str]:
    """The run's policy: ``params.relaxation_policy`` (``run``) over the term setting over the default."""
    value = (params or {}).get("relaxation_policy")
    if value in RELAXATION_POLICIES:
        return str(value), "run"
    return await term_relaxation_policy(session, term_id)


def clamp_server_params(params: dict[str, Any]) -> dict[str, Any]:
    """Defaults merged in by the server (settings) are clamped to the same bounds."""
    b = bounds()
    out = dict(params)
    for key in ("time_limit_s", "workers"):
        if key in out and isinstance(out[key], int | float):
            lo, hi = b[key]
            v = min(max(out[key], lo), hi)
            out[key] = int(v) if key == "workers" else float(v)
    if deterministic_run(out):  # the server default must not bring the threads back
        out["workers"] = 1
    return out


# --------------------------------------------------------------------------- studio seal


def _key() -> bytes:
    return hashlib.sha256(("studio-run-seal:" + get_settings().app_secret).encode("utf-8")).digest()


def _digest(term_id: int, kind: str, snap: dict[str, Any]) -> str:
    msg = json.dumps({"term": int(term_id), "kind": kind, "snap": snap}, sort_keys=True, default=str)
    return hmac.new(_key(), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def seal_studio(params: dict[str, Any], term_id: int, kind: str) -> dict[str, Any]:
    """``params`` with ``studio_sig`` for its ``studio`` snapshot (call only from studio.generate)."""
    snap = params.get("studio")
    if not isinstance(snap, dict):
        return params
    return {**params, "studio_sig": _digest(term_id, kind, snap)}


def trusted_studio_snapshot(run: Any) -> dict[str, Any] | None:
    """The run's draft snapshot when the server sealed it, else ``None`` (a forged one is ignored)."""
    params = run.params or {}
    snap = params.get("studio")
    if not isinstance(snap, dict) or not snap:
        return None
    sig = params.get("studio_sig")
    if isinstance(sig, str) and hmac.compare_digest(sig, _digest(run.term_id, run.kind, snap)):
        return snap
    log.warning("run %s: ignoring an unsealed params.studio snapshot", getattr(run, "id", None))
    return None


__all__ = [
    "DEFAULT_RELAXATION_POLICY",
    "MODERATION_KEYS",
    "PUBLISH_CANDIDATE",
    "deterministic_run",
    "RELAXATION_POLICIES",
    "RESERVED_KEYS",
    "ParamError",
    "clamp_server_params",
    "clean_client_params",
    "clean_priorities",
    "effective_relaxation_policy",
    "set_term_relaxation_policy",
    "term_policy_key",
    "term_relaxation_policy",
    "seal_studio",
    "trusted_studio_snapshot",
]
