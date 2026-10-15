# The suggester: from tester reports to tickets and ranked enhancements

The loop (README §9): testers run the flows and write reports → **the suggester** turns them into tickets → dedicated loop builders fix them → the testers re-verify.
The suggester writes **only** under `docs/ROADMAP.md` › `### Flow loop tickets` (and its sub-list "Flow loop enhancements"). It never edits another roadmap section, never edits code, and never changes a tester report.

## 1. Inputs

1. The round's reports: `docs/testing/flows/reports/<date>-<F-xx>-<persona>.md`. Read the table, the issue blocks and the closing `jsonl` block (README §6). The jsonl is the source of truth for results. The issue blocks give the details.
2. The previous round's tickets in "Flow loop tickets", to mark them verified or reopened.
3. Everything already planned, for de-duplication:
   - `docs/ROADMAP.md`: every section, including the routed persona issues (U-, A-, M-), the Phase 19 tickets (P19-…), the motion tickets (T1–T13) and the owner hand-offs;
   - the persona reports `docs/testing/2026-10-15-persona-*.md`;
   - `docs/review/2026-10-15-uiux-visual-review.md`;
   - `docs/review/2026-10-15-motion-audit.md`.
4. The snapshot commit of the round (`sha` in the jsonl), to check that the file hints exist: `git ls-tree -r --name-only <sha> | grep <path>`.

## 2. Procedure

1. **Collect.** Merge every jsonl row of the round. Keep FAIL, BLOCKED and INCONCLUSIVE. PASS rows matter only for closing tickets (step 6).
2. **Cluster.** One ticket = one root cause that one builder can fix in one file scope. Merge rows that share a root cause across personas, viewports and flows. For example, "focus falls to `<body>` after confirm" in F-01 S07, F-02 S08 and F-04 S10 is one ticket if the cause is the shared dialog primitive, and three if each screen handles focus itself. Split a row that needs two builders (backend 409 + frontend message) into two linked tickets.
3. **De-duplicate** against ROADMAP (search by the earlier issue id the tester cited, by the P19 / T ticket id, by the file hint and by 2–3 keywords in TR and EN):
   - **Open item exists** (`- [ ]`): no new ticket. Add one line `- re-seen FLT-… → <existing item's id or first words>: <flow step>, <sha>` under "Flow loop tickets", so the builder sees fresh evidence. Do not edit the existing line.
   - **Closed item exists** (`- [x]`) but the step fails: a **regression ticket**, severity one level higher than the tester gave (at most blocker), naming the closing commit of the original item.
   - **Owner decision missing** (the step is BLOCKED by a product choice, e.g. the SSO provider): not a ticket. Add it to the "Blocked by decisions" list (§4) once, with the flows it blocks.
   - **Nothing found:** a new ticket.
4. **Write tickets** in the format of §3, with ids `FLT-<nnn>`, numbered across all rounds and never reused.
5. **Rank enhancements** (§5), separately from the tickets.
6. **Close the previous round.** For each open FLT ticket whose steps now PASS on all their viewports, append `verified <sha> <date>` and tick it. For each that still fails, append `reopened <sha> <date>: <what still fails>` and keep it open. A ticket is verified only by a tester's PASS row, never by a builder's claim.
7. **Hand off** (§6).

## 3. Ticket format

One line per ticket, under `### Flow loop tickets`, grouped by owner area (§4), most severe first:

```
- [ ] FLT-<nnn> · <severity> · <owner area> · F-xx S<nn>[, F-yy S<nn>] · <one-sentence problem, user-visible>
      files: <path>[:line], <path> (checked at <sha>)
      check: <the acceptance check: the flow step(s) that must PASS on <viewports>, plus one automatable assertion (Playwright snippet name from MOBILE.md, or a curl with the expected status/body)>
      evidence: FL-xx-nnn (<persona>, <viewports>) <report path>
      dedup: new | regression of <item> (<closing sha>) | see also <item>
```

Rules:
- **Severity** follows README §6 (blocker / major / minor / trivial), with these overrides:
  - a KVKK or security leak is a **blocker**;
  - a failed MOBILE.md M-01, M-02, M-05 or M-12 on a primary screen is **major**;
  - a step that cannot be finished on touch because of a hover-only control is **major**;
  - **locator drift** is **trivial**.
- **The problem sentence** says what the user sees, not the fix: "The reject dialog accepts a rejection without a reason", not "add a radio group".
- **File hints** come from the tester and are verified at the round's sha. The ticket says "(not found at <sha>)" when a hint does not exist. Never invent a path.
- **The check** must be runnable by the re-tester without reading the ticket's history: the step ids, the viewports, and one assertion. Example: `F-01 S08 desktop+phone; curl POST /approvals/<id>/decide {"decision":"reject"} → 422 reason_required handled with a Turkish field error`.
- **KVKK:** no personal names, e-mails, tokens or cell contents in tickets. Use course codes, room codes, initials and ids.
- **One owner area per ticket**, so builders never collide on files (ROADMAP "Dedicated agents per new stream": non-interference is at file level).

## 4. Owner areas and routing

| Owner area | Typical paths | Builder (ROADMAP, "Dedicated agents per new stream") |
|---|---|---|
| `design-system` | `frontend/src/components/ui/**`, `app/globals.css`, tokens, focus ring, control sizes, segmented control, sheets/dialog primitives | design-system overhaul agent |
| `mobile` | per-screen responsive work against MOBILE.md (layouts, card lists, bottom sheets, sticky actions, safe area, viewport meta) | dedicated mobile builder, per screen after its owner finished |
| `shell-bookings` | `components/{shell,bookings,approvals,findroom,notifications,auth}/**`, `/my-bookings`, profile, admin screens | shell/admin sweep agent, then the approval-first frontend builder |
| `approval-first` | approval-mode setting, reject dialog with reason, reason shown to requesters, Profile › Bildirimler | approval-first frontend builder (backend builder for API gaps) |
| `p19-ui` | `components/{moderation,learning,program-wizard,onboarding}/**`, `/moderation/**`, `/programs/new`, `/onboarding` | P19 UI agent (onboarding: design-system agent until it hands over) |
| `studio-calendar` | `components/{studio,timetable,runs,classes,chat}/**` | studio/calendar sweep agent |
| `backend` | `smartsched/backend/app/{api,services,models,schemas}/**`, migrations | backend agent |
| `solver` | `app/solver/**`, `solver_bridge`, run params | solver agent |
| `importer-intake` | `app/importers/**`, `app/council/**` | importer agent / intake agent |
| `ai` | `app/ai/**` | AI agent |
| `i18n` | `frontend/messages/{tr,en}.json`, page titles, plurals | the screen's owner; i18n-only sweeps |
| `devops` | `scripts/**`, `smartsched/deploy/**`, CI gates | devops agent |
| `integrations` | external channel provider, SSO login | integration builder / login builder, after the owner chooses a provider |
| `tests` | `docs/testing/flows/**` (the scripts themselves were wrong) | test planner |

**Blocked by decisions** (a sub-list under "Flow loop tickets"; one line each, never a ticket):
- `SSO provider not chosen` → F-12 S11–S13. Waiting for `docs/product/2026-10-15-integrations-options.md` and the owner's choice.
- `External notification channel provider not chosen` → F-01 S13.
- `No AI key on the test stacks` → F-03 (natural-language search, if built), F-08 S15, F-09 S03 (free-text path). These are environment, not product.

## 5. Enhancements, ranked by user value

Testers propose enhancements in their reports ("Enhancements" section, or issue blocks marked `enhancement`). The suggester also proposes them where a flow shows friction but no defect (several steps, a workaround, a dead end that is "by design").

Score each one: **value = reach × pain × fit ÷ effort**.
- **reach:** how many personas meet it × how often (1 = once a term, 2 = weekly, 3 = daily). Example: staff + academician on every booking = 2 × 3 = 6.
- **pain:** 1 = cosmetic, 2 = extra steps, 3 = a workaround outside SmartSched (e-mail, Excel), 4 = the task cannot be done.
- **fit:** 1.5 if it implements an owner decision or an open P19 ticket, 1 otherwise, 0.5 if it bends an owner decision (needs the owner's yes first).
- **effort:** 1 (S, one file), 2 (M, one area), 3 (L, several areas or a migration).

Write them under `#### Flow loop enhancements (ranked)` as:
```
1. FLE-<nnn> · score <n> · <persona(s)> · <what the user gets, one sentence> · maps to: <P19-… / persona Enh. #n / new> · flows: F-xx S<nn>
```
Re-rank the whole list each round. Never delete an entry: mark it `done <sha>` or `declined by owner <date>`.

Seed candidates already visible in the flow scripts (score them in round 1 with real evidence, do not copy the order):
- "Derslerim" and a teacher home (P19-T1)
- the academician's own planning requests with "Tercih ekle" (P19-T2)
- publish-change digests per academician (P19-T3)
- class meetings in personal feeds (P19-T4)
- a make-up shortcut from a class to Find a room (persona-academician Enh. #2)
- one row / one VEVENT per multi-period booking (persona-user Enh. #2, A-12)
- scope counts before a series cancel (persona-user Enh. #7)
- undo on cancel (persona-user Enh. #9)
- a user↔instructor picker (F-05 S00)
- a KVKK sign-off admin screen (M-40)

## 6. Hand-off message (to the orchestrator, at the end of each round)

```
BLUF: round <n> on <sha>: <x> tickets (<b> blocker, <M> major, <m> minor, <t> trivial), <r> re-seen, <g> regressions, <v> verified, <o> reopened.
Top 5: FLT-… (area, one line each)
Per builder: design-system <n> · mobile <n> · shell-bookings <n> · approval-first <n> · p19-ui <n> · studio-calendar <n> · backend <n> · …
Blocked by decisions: <list with flows>
Re-test list for round <n+1>: <flow steps per persona>, after the builders report the fix commits
```

## 7. Examples (format only; do not append these)

```
- [ ] FLT-001 · major · approval-first · F-01 S08 · The reject dialog lets an admin reject a request without choosing a reason
      files: smartsched/frontend/src/components/approvals/approvals-view.tsx (checked at b75047b)
      check: F-01 S08 desktop+tablet+phone; with no code chosen "Reddet" is disabled; "Diğer" + blank text is refused with a Turkish field message; curl POST /approvals/<id>/decide {"decision":"reject"} → 422 reason_required
      evidence: FL-01-004 (admin; desktop, phone) docs/testing/flows/reports/2026-10-16-F-01-admin.md
      dedup: see also ROADMAP "Approval-first bookings … Frontend after the backend lands" (the open item; this ticket is its acceptance)
- [ ] FLT-002 · minor · mobile · F-01 S02, F-03 S06 · The book sheet's "Talep et" scrolls out of reach on a 390 px phone
      files: smartsched/frontend/src/components/bookings/book-sheet.tsx (checked at b75047b)
      check: MOBILE.md M-05 on /bookings with the sheet open, phone; PRIMARY = getByTestId("book-submit")
      evidence: FL-01-006, FL-03-002 (staff, academician; phone)
      dedup: new
```
