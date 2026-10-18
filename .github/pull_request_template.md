## What and why

<!-- One topic per pull request. Link the issue or the docs/ROADMAP.md ticket: "Closes #123". -->

## How it was verified

<!-- Commands and their results. For UI changes: screenshots at 1440 px and 390 px, light and dark. -->

- [ ] Tests first: a failing test before the fix (pytest / vitest / Playwright)
- [ ] `make -C smartsched check` passes (or the backend / frontend part this change touches)
- [ ] `python3 -I scripts/docs/sync_docs.py --check` and `python3 -I scripts/record/check_readme.py` pass

## Checklist

- [ ] Every new user-facing string is in Turkish and English (`messages/tr.json` + `en.json`, `message_tr` / `message_en`)
- [ ] Keyboard and screen reader work; 44 px touch targets; no hover-only affordances; reduced motion respected
- [ ] No secrets, internal host names or real personal data (instructors as initials only)
- [ ] No new GitHub workflow that runs on push or pull request (CI runs on the pod)
- [ ] Docs updated (`docs/features.yml`, `docs/ROADMAP.md`, the relevant guide) when behaviour changes
- [ ] The integrity guards (`publish_guard.py`, `pin_guard.py`, `move_guard.py`, `run_truth.py`, `precheck.py`) are untouched, or the change was agreed in an issue
