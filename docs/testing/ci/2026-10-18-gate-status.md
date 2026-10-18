# Pod-CI gate status, 2026-10-18 (ci-green-2026-10-18)

Reproduced in the agent container (4 shared cores, no Docker stack, no `next build`), under `nice -n 10`.
Two trees: **gracious d9647b59** (the commit the pod deploys next, coordinator priority) and **focused-wright HEAD**
(working branch, checkpoints up to 0bc13d2b). The PostgreSQL tests ran on the local postgresql binaries
(tests/pg_support.py), not on the gate's service container.

## gracious d9647b59 (fresh py3.12 venv, `pip install -c requirements.lock -e .[dev]` as in its gates/backend.sh)

| Gate step | Command | Result | Cause | Fix (patch: gracious-backend-gate.patch, in the session scratchpad) |
|---|---|---|---|---|
| lint | `make lint` | pass | | |
| type | `make type` | pass (303 files) | | |
| alembic heads | `alembic heads` | pass (one head, 0046_ai_quota_units) | | |
| solver / ai ruff | `ruff check app/solver`, `ruff check app/ai` | pass | | |
| pytest | `make test` (2667 tests) | **14 real failures** | see below | all 14 pass after the fixes |
| | | 1 flake | tests/test_review_jobs.py::test_m13_cancel_queued_run_and_per_user_limit failed in the full run under load, passes alone | none (timing under load) |

Real failures on gracious (each one also fails when run alone):
1. tests/council/test_ai_intake.py (2: scanned PDF, ruled PDF tables): `ModuleNotFoundError: reportlab`. Not in any
   dependency list; local venvs had it by accident. Fix: `reportlab>=4.0` in the `dev` extra of pyproject.toml.
2. tests/parity/test_parity_bookings.py::test_permissions_are_grouped_like_crbs and
   tests/test_crbs_roles.py::test_seeded_roles_…: `39 == 37` (calendar.department_feed CAL-03 + ai.usage_faculty
   HB-11 were added, the counts were not). Fix: HEAD's hunks (37 -> 39 and the comment).
3. tests/test_channels_dispatch.py (3): `drain() == 2`, "too many values to unpack". RF-11 added the submitter's
   receipt (approval.submitted) on every channel, so Telegram gets 2 messages. Fix: the tests expect the receipt
   and check the rejection separately (same patch on HEAD).
4. tests/test_crbs_languages.py::test_generated_language_files_are_fresh: messages/cs.json etc. are stale. Fix: run
   `python -m tools.crbs_lang_import` (12 catalogues + locale data + coverage report).
5. tests/test_w3b_mail_smtp.py (5): `ValueError: check_hostname requires server_hostname`. **Production bug on
   Python 3.12** (the image and pod CI): app/services/mail.py `_open()` builds `smtplib.SMTP()` / `SMTP_SSL()` without
   a host and calls `connect()`. Python 3.12 sets the TLS `server_hostname` (`_host`) only in the constructor (3.13
   also does it in `connect()`), so STARTTLS and SSL with a transcript (the admin "test e-mail" path) fail on 3.12.
   Hidden locally because the dev venvs are 3.13. Fix: `server._host = host  # type: ignore[attr-defined]` before
   `server.connect(host, port)`.

## focused-wright HEAD

| Gate | Command | Result | Failures fixed | Left |
|---|---|---|---|---|
| backend lint | `make lint` | **fail** | | HB-D (running lane): tests/helper/test_hb_d_asks.py:329 F811 `env` redefined; app/ai/helper/guard.py:118 E501; `ruff format` on guard.py and remember.py |
| backend type | `make type` | **fail** | | HB-D: app/ai/helper/page_context.py:83 `List item 0 has incompatible type "None"` |
| backend pytest | `make test` | not run in full on HEAD (the gracious run had priority) | channels (3), languages (regen), reportlab (dep), SMTP 3.12 (mail.py): the same fixes as gracious, all pass on HEAD | a full `make test` run on HEAD, in py3.12 |
| backend locks | aarch64/cp312 wheel coverage, per pin, hash-matched (requirements-dev.lock 111 pins, build 1) | pass but one sdist | reportlab==5.0.1 added via `make lock` (py3-none-any) | http-ece==1.2.1 has no wheel (pure Python, sdist hash locked; builds with setuptools under build isolation). The full fresh `pip install --require-hashes` was not run |
| frontend | `npm run check` | not run (time) | | |
| frontend generators | `node scripts/gen-helper-features.mjs --check`, `gen-helper-schema.mjs --check` | pass | | |
| validate | `sync_docs.py --check --diff`, docs unittest (27), `check_readme.py`, `bash smartsched/deploy/validate.sh` | pass after fix | STATUS.md roadmap block regenerated | re-run `sync_docs.py` before every commit (ROADMAP and PROGRESS change continuously) |
| infra | `ruff check infra/aws smartsched/deploy/pod-ci` + seed | pass | | pytest not run here (coordinator fixed the duplicate test_bootstrap_settings.py) |
| e2e (static) | playwright.config testMatch vs e2e/*.spec.ts | pass after fix | `rf-[a-z-]+` added: e2e/rf-f.spec.ts was never matched | rf-f.spec.ts has not run on a stack yet; e2e-real will run it now |
| images (static) | next.config / Dockerfile / .dockerignore | pass | | Next 16 runs no lint in `next build`; `typescript.ignoreBuildErrors: false`; e2e/ is outside the build context, so the build's type-check is the same tsc minus e2e. tsc itself not run here |
