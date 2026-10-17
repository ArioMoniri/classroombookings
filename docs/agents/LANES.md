# Agent lanes: who is doing what, and how to resume after a limit

Updated 2026-10-18 01:10 UTC by the focused-wright orchestrator (session `claude/focused-wright-ktt0ss`).
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

| Lane | Ledger name | What | Brief / tickets | Ports | Waits on |
|---|---|---|---|---|---|
| Round-3 lane C (intake) | `loop-r3-laneC` | R3-S-04, R3-M-02/03/04/07 (re-upload deltas, phone onboarding), the person_match merge review in the council, AI notices on the onboarding upload | ROUND3.md, ROADMAP round-2/3 blocks | 19320/19321 | — |
| CAL-B | `cal-b-2026-10-17` | Calendar export backend CAL-01..07 (stable UIDs, scoped links, .ics, push to a dedicated calendar); migration 0039 | ROADMAP "Calendar export & sync" | — | — |
| CAL-F | `cal-f-2026-10-17` | "Takvimime ekle" 3-tap sheet + admin settings CAL-08/09 | same | 19750/19751 | CAL-B API |
| Launch video | `media-launch` | Recordly + Lottie + Remotion launch/explainer/README videos, phone variants | MEDIA.md | own | final UI |
| Mobile A, phase 2 | `mobile-a` | Fixes 1–15 of docs/testing/mobile/2026-10-17-mobile-a.md plus the shared primitives from mobile B (inputs, small buttons, tab/top bar) | that report | 19620/19621 | — |
| Mobile B, phase 2 | `mobile-b` | Route-level fixes of docs/testing/mobile/2026-10-17-mobile-b.md (runs, studio, classes, timetable, moderation, admin, dashboard, analytics, invigilation, policies) | that report | 19630/19631 | — |
| WG-B | `wg-b-2026-10-17` | Welcome guide backend WG-01..03; migration 0040 | ROADMAP "Welcome guide per role", docs/design/v3/welcome-guide.md | — | — |
| WG-F | `wg-f-2026-10-17` | Welcome sheet, tour (React Joyride), checklist, hints, /admin/welcome WG-04..08 | same | 19780/19781 | WG-B API |
| Charts phase 2 | `charts-p2-2026-10-17` | EvilCharts ECharts install + ChartCard shell CH-01/02 | docs/design/v3/charts.md | — | — |
| AS-B | `as-b-2026-10-17` | Adaptive scheduling backend AS-01..07, 09..11, 13, 18 (+ RF-02 weights, RF-07 learning refresh); migration 0041 | docs/research/2026-10-17-adaptive-scheduling.md | — | — |
| VO-B | `vo-b-2026-10-18` | Voice backend VO-01..04, VO-10 (admin-moderated cloud speech-to-text, no on-prem) | docs/research/2026-10-17-voice-ai.md | — | security follow-up (providers/ai_usage) |
| VO-F | `vo-f-2026-10-18` | Mic button, consent, /admin/ai voice UI, mounts VO-06..08 | same | 19790/19791 | VO-B API |
| HB-A | `hb-a-2026-10-18` | Helper backend HB-01..05, 08, 09 (feature index, search without AI, action registry, guardrails, memory) | docs/research/2026-10-17-ai-helper-architecture.md | — | helper UX for the card contract |
| RF-1 | `rf-1-2026-10-18` | Enrolment edit, invite e-mail switch, admin catalogue screens (instructors, courses, faculties, sections) | docs/testing/audits/2026-10-17-no-mock-and-editability.md | 19800/19801 | — |
| RF-2 | `rf-2-2026-10-18` | Senders for reminder, series, approval receipt, calendar consent, new-device e-mails | same | — | — |
| Auth UX | `auth-ux-2026-10-18` | Sign-in, 2FA challenge, Profil › Güvenlik, admin resets, input system, motion; AUX tickets | ROADMAP "Sign-in, 2FA and passkeys — UX", docs/design/v3/auth.md | — | — |
| AU-B | `au-b-2026-10-18` | TOTP, recovery codes, passkeys (WebAuthn), trusted devices, MFA policy, admin MFA reset + reset link (local accounts only) | docs/research/2026-10-18-auth-backend.md, ROADMAP "— backend" | — | — |
| Deploy one-click | `deploy-1click-2026-10-18` | Both branches one-click deployable; every setting reachable from the CLI or the first admin's setup | this file, docs/deploy | — | — |

## Queued (start when the named lane hands off)

| Next | Starts after | Notes |
|---|---|---|
| CAL-10 academician tester | CAL-B + CAL-F | test plan T1–T19 in the calendar research doc |
| WG-09 motion (one hosted transitions.dev fix) + WG-10 role testers | WG-B + WG-F | |
| AS solver lane AS-08, AS-12, AS-14 | AS-B AS-02 (see `scratchpad/as/AS-B-STATUS.md`, or AS-B's report) | |
| AS frontend AS-15..17, AS tester AS-20 | AS-B | |
| VO-05 (`microphone=(self)` in nginx/Caddy) | security follow-up | |
| HB-06/12/13 (helper turn loop, capability detection, local-model fixes) | VO-01 | same gateway files |
| HB-10/11 (quota chain org → faculty → department → role → user, limits in PostgreSQL: fixes the 2-worker doubling) | VO-02 | |
| Helper frontend HX-01..13 | HB-A + WG-F + mobile A (shell mounts) | docs/design/v3/helper.md; helper UX design done 2026-10-18 |
| CH-04..12 chart migrations | charts phase 2 | |
| RF-04, RF-10 (phone month arrows, density) | mobile A/B | |
| RF-06, RF-08, RF-09 (re-import keeps admin edits, seed imports in history, editable period grid) | round-3 lane C, CAL-B | |
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
