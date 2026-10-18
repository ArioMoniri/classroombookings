# Agent lanes: who is doing what, and how to resume after a limit

Updated 2026-10-18 09:32 UTC by the focused-wright orchestrator (session `claude/focused-wright-ktt0ss`).
Background agents belong to the session that started them. If a session hits a usage limit or ends, its
agents stop, but every change they made is in git: the orchestrator commits the tree every 30 minutes
(`wip: checkpoint of running agents' work`). To resume a lane in a new session:

1. Read docs/HANDOFF.md (the progress log, newest first) and this file.
2. Run `git log --oneline -30` and `git status --short` to see what each lane left behind.
3. Re-launch the lane with its brief (`docs/agents/briefs/COMMON.md` plus the lane brief or ticket section
   named below). Tell it: "resume: read your tickets, the ROADMAP ticks and PROGRESS rows for your
   ledger name, then continue from the first unticked ticket; tests first".
4. The API contracts lanes exchange (`scratchpad/<lane>/API.md`) live in the old session's scratchpad and are
   lost with it. A resumed backend lane writes its API.md again from its code before the frontend lane starts.

Rules for every lane: docs/agents/briefs/COMMON.md (no commits by agents, tests first, own ports, never
`pkill -f`, Turkish first, 44 px / 16 px on phones, the Simplicity principle, no demo/mock code in production).

## Running now

| Lane | Ledger name | What | Brief / tickets | Waits on |
|---|---|---|---|---|
| HB-A | `hb-a-2026-10-18` | Helper backend HB-05/09, card contract | helper architecture doc | — |
| HB-B | `hb-b-2026-10-18` | HB-12/13/06/10/11, DECISIONS row for provider capabilities | helper architecture doc | — |
| Launch video | `media-launch` | Recordly + Lottie + Remotion videos | MEDIA.md | final UI |
| E2E lane | `e2e-2026-10-18` | Runs docs/testing/e2e-queue section by section → results-2026-10-18.md | e2e-queue README | — |
| RF-B | `rf-b-2026-10-18` | RF-06 re-import keeps edits, RF-08 seed imports in history, RF-09 backend, `/users/search?mfa_state` | audit doc | — |
| AUX-10 | `aux-10-2026-10-18` | Sign-in hero (one hosted fix "signin-hero-settle") | auth.md §11.3–§11.4 | — |
| RF-M | `rf-m-2026-10-18` | RF-04 phone month arrows, RF-10 density on timetable | audit doc | — |
| WG-09 | `wg-09-2026-10-18` | Welcome-guide motion pass (one hosted transitions.dev fix) | welcome-guide.md | — |
| HX | `hx-2026-10-18` | Helper frontend HX-01..13 (search without AI, chat with live cards, confirm/undo, memory, status) | helper.md, scratchpad helper/API.md | — |

Done 2026-10-18: HB-A (HB-01/03..05/07..09; HB-02 p95 needs a stack), AS-B (AS-S merges, backtest B1–B9 pass), AS-F (AS-15..17 + RF-07 UI, part done until e2e), AUX-F (AU-18 wiring), AU-B, CAL-F, VO-F, WG-F, charts p2, mobile A/B, RF-1, RF-2, sweeper.

## Queued (start when the named lane hands off)

| Next | Starts after | Notes |
|---|---|---|
| **Tester wave** (against the pod over HTTPS, not a local stack): WG-10 role testers (teacher, staff, admin), CAL-10 academician tester (T1–T19), round-4 personas (staff, academician, admin), AS-20 adaptive tester, CH-12 chart pass | pod health 200 after the 09:29 merge | one slot each as lanes free up; at most 8 agents; reports in docs/testing/ |
| CAL-10 academician tester | CAL-B + CAL-F | test plan T1–T19 in the calendar research doc |
| WG-09 motion (one hosted transitions.dev fix) + WG-10 role testers | WG-B + WG-F | |
| AS frontend AS-15..17, AS tester AS-20 | AS-B | |
| VO-05 real-stack check of getUserMedia behind nginx and Caddy | VO-F e2e | headers done by VO-B |
| CAL-13 exam/invigilation duties scope | a published invigilation plan in the fixtures | |
| Helper frontend HX-01..13 | HB-A + WG-F + mobile A (shell mounts) | docs/design/v3/helper.md; helper UX design done 2026-10-18 |
| CH-04..12 chart migrations | charts phase 2 | |
| RF-04, RF-10 (phone month arrows, density) | mobile A/B | |
| RF-06, RF-08, RF-09 (re-import keeps admin edits, seed imports in history, editable period grid) | CAL-B (lane C done 2026-10-18) | |
| RF-12 (SAML metadata signature) | — | SAML library done |
| Round-4 persona testers (staff, academician, admin) | the fix lanes above | re-seed: old snapshots lack migrations ≥ 0037 |
| Auth frontend AUX | auth UX + AU-B | |
| README/docs media pass, final merges into gracious + universal | launch video + round 4 | merge rules below |

## Branches and the pod

- `claude/focused-wright-ktt0ss`: the working branch; everything lands here first.
- `claude/gracious-cerf-w1598m`: institution profile (Bahar/Güz/Final workbooks). Fast-forward from the
  working branch after merging gracious in, keeping gracious's `infra/aws/POD_ACTION` unchanged, so the
  AWS workflow doesn't fire. The pod deploys this branch by polling.
- `claude/smartsched-universal`: empty profile (`SEED_PROFILE=empty`, `profile.env` is merge=ours: run
  `git config merge.ours.driver true` in each clone). Merge the working branch in, then restore
  universal's `infra/aws/POD_ACTION`.
- Pod control: push `infra/aws/POD_ACTION` (start / status / logs / stop) **only on gracious or universal**;
  the OIDC role trusts only those two branches.
- The manual pod-CI refresh command (SSM) is in docs/HANDOFF.md; the owner ran it at 23:19 UTC on 2026-10-17.
