# Round-2 builder addendum (read COMMON.md first, then this)

Everything in COMMON.md applies, with these substitutions for round 2:

- Ticket source: docs/ROADMAP.md `#### Flow loop tickets — round 2 (suggester, 2026-10-17)` (lines ~1328–1642) and
  `docs/testing/flows/rounds/round-2-tickets.json` (your lane's `owns`, `tickets[*].check`, `files`, `depends_on`).
  The finding ids (R2-A/S/M-nn) point into `docs/testing/flows/rounds/round-2-<persona>.md`: read the finding
  block for the user's words before you fix anything; the evidence folders of the testers are under
  /tmp/claude-0/-home-user-classroombookings/46e08325-505b-5c43-93e9-784868588343/scratchpad/r2{acad,staff,admin}/ev
  (read-only).
- Ledger name: `loop-r2-lane<X>-2026-10-17`. Done lines: `done (…; loop-r2-lane<X>-2026-10-17)`; set `status` and
  `resolution` on your tickets in round-2-tickets.json.
- A ticket with `depends_on: ["T-R2-05"]` waits for lane A's primitives fix: do your other tickets first; when you
  reach it, check `git log --oneline -- smartsched/frontend/src/components/ui` for lane A's hit-area change (the
  orchestrator checkpoints the shared working tree every ~30 min, so lane A's change appears in your tree as soon
  as it is written); if it is not there yet, finish everything else, then do it on the primitives as they are and
  say so in your report.
- Reopened round-1 tickets your T-R2 ticket names: re-read their round-1 done-line, do not undo what they did.
- Nine agents share the 4-core host: `nice -n 10` for builds and stacks, one stack per lane, `stack.sh down` at
  the end, kill only your own PIDs.
