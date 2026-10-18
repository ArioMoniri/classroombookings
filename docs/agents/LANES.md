# Agent lanes: who is doing what, and how to resume after a limit

Updated 2026-10-18 09:55 UTC by the focused-wright orchestrator (session `claude/focused-wright-ktt0ss`).
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
| IDP-2 | `idp2-2026-10-18` | SAML wizard fields (signing cert, SP key, sign requests); refuse AES-CBC unless the Response is signed | IDP PROGRESS rows | — |
| HX | `hx-2026-10-18` | Helper frontend HX-01..13 (HX-09 after HB-14/15) | helper.md, scratchpad helper/API.md | HB-C for HX-09 |
| Launch video | `media-launch` | Recordly + Lottie + Remotion videos | MEDIA.md | final UI |
| E2E lane | `e2e-2026-10-18` | docs/testing/e2e-queue section by section → results-2026-10-18.md | e2e-queue README | — |

Done 2026-10-18: RF-F (RF-06, RF-08 ticked; RF-09 part done: client still uses fixed period times → RF-16), RF-C (RF-14, RF-15), IDP (RF-12, encrypted assertions, request signing, profile linking; e2e pending), Sweeper 2 (W3-AI capsule + history spotlighting, F13 hashed locks, /grafana/ drift test, mobile B capsules, fix 15 two of three, A5 density rows), HB-C (HB-14, HB-15; HB-16 part done: needs a GPU host walk-through), CH-B (chart routes; CH-07/10/11 wait on e2e only), RF-B (RF-06/08/09 backend, `mfa_state` filter), CH-M (CH-08 done; CH-07/10/11 frontend waiting on CH-B), HB-B (HB-06, HB-10..13; e2e pending), WG-09 (part done: e2e pending, hosted fix unspent), RF-M (RF-04, RF-10; e2e pending), AUX-10 (part done: e2e pending, the hosted fix "signin-hero-settle" is unspent because `TRANSITIONS_AGENT_LICENSE` is not set in this session), HB-A (HB-01/03..05/07..09), AS-B, AS-F, AUX-F, AU-B, CAL-F, VO-F, WG-F, charts p2, mobile A/B, RF-1, RF-2, sweeper.

## Queued (start when a slot frees; at most 8 agents)

| Next | Starts after | Notes |
|---|---|---|
| RF-16 period grid loaded at app start (frontend) | HX (shell mount) | frontend-engineer; closes RF-09 |
| **Tester wave** against the pod over HTTPS (not a local stack): WG-10 role testers, CAL-10 academician (T1–T19), round-4 personas (staff, academician, admin; Simplicity), AS-20 adaptive, CH-12 charts, VO-09 voice (fixtures, bench, personas), AUX-12 sign-in (auth.md §16 checks 1–13), HB-18 helper red team and personas | pod health 200 | reports in docs/testing/ |
| HB-17 local-model bench + HB-16 GPU walk-through | running in child session session_01PJDxbGh1r6tTTr7RXHJySF (Lambda A10, cap 2.5 h, teardown check 13:25 UTC) | tester |
| HB-07 design sign-off on the 4 card-contract differences | HX report | design-pro, review only |
| CAL-13 exam/invigilation duties scope | a published invigilation plan in the fixtures (AS-12 advisor data exists now) | |
| Council full re-run (round-3 lane C, lost) | E2E lane, on its stack | queued in e2e-queue |
| README/docs media pass, final merges | launch video + tester wave | merge rules below |

Deferred by the plan ("later" in ROADMAP, not started on purpose): CAL-11, CAL-12, WG-11, AS-19, VO-11..13, HB-19, HB-20, HX-14.

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
