# Contributing to SmartSched

Thank you for helping. SmartSched is a timetabling, exam-planning and room-booking app for a university, built
as a superset of classroombookings. This guide covers the set-up, the checks a change has to pass and the few
house rules. Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug** with the **Bug report** form (Issues → New issue)
  (steps, what you expected, what happened, the screen width).
- **Suggest a feature** with the **Feature request** form.
  Say who it is for (planner, coordinator, academic, staff, administrator) and what they do today instead.
- **Fix something.** Small fixes can go straight to a pull request. For anything larger, open an issue first so
  we can agree on the approach.
- **Security problems are never public issues.** Follow [SECURITY.md](SECURITY.md).

## Repository layout

```
smartsched/backend/    FastAPI, SQLAlchemy 2, Alembic, OR-Tools CP-SAT (Python 3.12+)
smartsched/frontend/   Next.js 16, React 19, TypeScript, Tailwind 4, TanStack Query, vitest, Playwright
smartsched/deploy/     docker compose, deploy.sh, nginx, Caddy, the legacy CRBS image, pod CI
infra/aws/             the AWS pod
scripts/               dev.sh, docs/ (generated docs), record/ (recordings and screenshots), parity_check.py
docs/                  architecture, roadmap, status, design specs, test reports
```

The original classroombookings PHP app stays unchanged at the root (`crbs-core/`, `index.php`, `assets/`).
Please do not move or rename directories: the deploy scripts, the pod CI and the tests depend on the paths.

## Set-up

Requirements: Python 3.12+, Node.js with npm, git. Docker Engine 24+ with Compose v2 only for the full stack.

```bash
scripts/dev.sh --run
```

This creates the Python venv, installs the frontend, seeds an administrator into SQLite and starts the backend
on :8000 and the frontend on :3000. The frontend always talks to a real backend; there is no mock API.
[docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) has the details, and
[docs/deploy/ONE-CLICK.md](../docs/deploy/ONE-CLICK.md) the Docker deploy.

## Checks before a pull request

| Area | Command |
|---|---|
| Everything fast | `make -C smartsched check` (backend ruff, mypy, pytest; frontend tsc, eslint, design check, vitest) |
| Backend only | `cd smartsched/backend && make check` (`make test-slow` for the heaviest real-workbook tests) |
| Frontend only | `cd smartsched/frontend && npm run check` |
| Generated docs | `python3 -I scripts/docs/sync_docs.py --check` (run it without `--check` to rewrite stale blocks) |
| README links and media | `python3 -I scripts/record/check_readme.py` |
| classroombookings parity | `python3 scripts/parity_check.py` |
| End to end | `E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test` against a real backend |

CI runs on the project's own pod (every gate in Docker for each new commit), not on GitHub-hosted runners. The
GitHub workflows in this repository are manual. Please do not add workflows that run on push or pull request.

## House rules

1. **Tests first.** A failing test (pytest, vitest or a Playwright spec) before the fix. Never skip, disable or
   quarantine a test to make a change pass.
2. **Turkish first, English second** for every user-facing string: keys in both
   `smartsched/frontend/messages/tr.json` and `en.json`, and `message_tr` / `message_en` in the backend. After a
   change to those two files, run `cd smartsched/backend && python3 -m tools.crbs_lang_import` and commit the
   regenerated language files with it. No raw enum or snake_case keys on screen.
3. **Simple screens.** One primary action per screen in plain Turkish, advanced options behind "Gelişmiş", and
   defaults that work without configuration. Booking a free period stays two taps.
4. **Accessible and phone-ready.** Keyboard and screen-reader complete, 44 px touch targets, 16 px inputs on
   phones, no hover-only affordances, motion that respects `prefers-reduced-motion`.
5. **Generated docs.** Text between `<!-- AUTO:… -->` markers is generated. Edit the source
   (`docs/features.yml`, `docs/ROADMAP.md`, …) and run `python3 -I scripts/docs/sync_docs.py`.
6. **Integrity guards are read-only.** `publish_guard.py`, `pin_guard.py`, `move_guard.py`, `run_truth.py` and
   `precheck.py` protect published timetables; changes there need an issue and a maintainer's review first.
7. **No secrets and no personal data.** Never commit keys, passwords, internal host names or real people's
   names. Test fakes for provider-shaped secrets are built by concatenation. Workbook fixtures and recordings
   show instructors as initials only (KVKK).

## Pull requests

- Keep a pull request to one topic and fill in the template.
- Describe how you verified the change (commands and results; screenshots at 1440 px and 390 px for UI work).
- Update `docs/features.yml`, `docs/ROADMAP.md` or the relevant doc when behaviour changes.
- Commit messages follow the existing style: `type(scope): summary` (for example `fix(bookings): …`).

## Licence

By contributing you agree that your contribution is licensed under the
[GNU Affero General Public License v3.0](../LICENSE.txt), the licence of this repository.
