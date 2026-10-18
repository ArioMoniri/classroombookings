# Flow loop round 3: persona re-test brief (session focused-wright, 2026-10-17)

Round 3 is a **re-test round**: every round-2 ticket (T-R2-01…35, docs/ROADMAP.md "Flow loop tickets — round 2"
and `docs/testing/flows/rounds/round-2-tickets.json`) is marked done by its builder; you confirm or reopen it as a
user. Everything in ROUND2.md applies (snapshot of the pushed head, own stack and ports, seed, SMTP sink, KVKK,
report format, ledger) with these changes:

1. **What to run.** (a) The "Re-test list for round 3" line at the end of the round-2 block in docs/ROADMAP.md names
   your persona's steps; run all of them. (b) Every round-2 finding you authored (`R2-<X>-nn`): re-run its step on
   its viewport(s) and write `verified <sha>` or `reopened <sha>: <what still fails>`; the T-R2 ticket that covers
   it is in round-2-tickets.json (`findings`). (c) Round-1 ids still open for round 3 (named in that line) with the
   corrected flow files lane G wrote (docs/testing/flows/F-xx, MOBILE.md §3). (d) Smoke the rest of each flow you
   touch at 1440 and 390 touch (not every step again unless a shared primitive changed under it: dialogs, sheets,
   tab bar, switches, checkboxes, segments, chips and toasts did change in T-R2-05/02/04, so run MOBILE M-02/M-05 on
   every route of your flows once more).
2. **Report**: `docs/testing/flows/rounds/round-3-<persona>.md` + `.jsonl` with `R3-<X>-nn` for anything new, and
   one re-verification row per R2 id and per re-tested R1 id. BLUF first: verified / reopened counts, new findings by
   severity, and your one-line verdict "ready for release from this persona's point of view: yes/no, because …".
3. Ledger name `flow-r3-<persona>-2026-10-17`. Ports: staff 19410/19411 (fresh 19412/19413), academician 19420/19421,
   admin 19430/19431 (fresh 19432/19433); SMTP 2626/2627/2628. Never commit.
