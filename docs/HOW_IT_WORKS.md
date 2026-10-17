# How SmartSched works

Moved from the README on 2026-10-15.

1. **Import.** Planning lists, exam lists and weekly room grids are read from the office's workbooks;
   a room master CSV corrects capacities and tags. Turkish day names, dotted times, comma decimals,
   room spellings such as `A 101`, `A101` and `B Blok Bilg. Lab.` and multi-value cells are normalised
   ([docs/DATA_ANALYSIS.md](DATA_ANALYSIS.md)). Every import ends with a report of what was read,
   what was skipped and why.
2. **Rules.** Settings, rule templates, the workbooks themselves and, with an Anthropic API key,
   sentences in Turkish or English and uploaded preference files (`.xlsx`, `.csv`, `.docx`, `.pdf`,
   `.txt`, `.md`) all become the same thing: a typed rule that is either *Must* (hard) or *Try to*
   (soft, weighted), with a link to where it came from. Nothing written by the AI is used until a
   person accepts it. The contents of an uploaded file go to the Claude API only after an
   administrator turns on AI intake (`PUT /api/v1/ai/policy`, off by default, with a KVKK
   acknowledgement); otherwise the file is read on the server and its rows are left for a person.
3. **Pre-check.** Before solving, the Generator Studio checks the plan against the data and lists what
   cannot work (a locked room that is too small, two classes locked into one room at once), each with
   fixes.
4. **Solve.** OR-Tools CP-SAT places classes into rooms and periods for a week, a month or the whole
   term (14 weeks), or exams into exam slots.
5. **Validate and explain.** Scores are computed again in plain Python from the finished timetable, so
   the solver, manual moves and AI edits are judged by the same code. Anything not placed is explained
   one class at a time. A second, independent check compares the stored timetable with the raw
   workbook rows (`app/services/planner_check.py`); pod CI runs it on four real instances for every
   commit.
6. **Publish and book.** Activating a run publishes it: its classes hold their slots in the booking
   grid, and staff book the free periods around them.

<table>
  <tr>
    <td align="center" width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/lottie/nl-to-rules-dark.gif">
        <img alt="Animation: a Turkish sentence becomes a typed rule card that can be reviewed before it is used" src="images/lottie/nl-to-rules-light.gif" width="360">
      </picture>
      <br><sub>With an API key, a sentence becomes a rule you review before it is used (illustration).</sub>
    </td>
    <td align="center" width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="images/lottie/file-to-rules-dark.gif">
        <img alt="Animation: rows of an uploaded preference file become rule cards, each linked to its source row" src="images/lottie/file-to-rules-light.gif" width="360">
      </picture>
      <br><sub>Rules read from an uploaded file keep a link to their source row (illustration).</sub>
    </td>
  </tr>
</table>

## Hard rules, waived exceptions and partial runs

The hard rules are: a room seats the class, a room holds one class at a time, a cohort and an
instructor are in one place at a time, fixed times stay fixed, and a class that needs a lab gets one.
SmartSched never relaxes one of them quietly.

Real planning data breaks these rules in a few known ways, and the planner usually knows. A class is
locked into a room with fewer seats than its enrolment estimate; two fixed classes of the same
instructor overlap; two rows lock the same room at the same time. SmartSched does not overrule the
planner here. It keeps the planner's decision, records each case as a *waived exception* with the
class and the room named, and lists them under *Problems in your data* in the run report, grouped and
exportable to Excel. Only the planner's own locks are trusted this way: a lock made by a fix button, a
manual move or an AI edit (`lock_trusted=False`) must fit the room like any other placement. Three switches control this, all on by default and all per run:
trust the planner's locked rooms, treat clashes between fixed classes as warnings, and keep the best
partial timetable when not everything fits
([solver README](../smartsched/backend/app/solver/README.md#real-data-modes-d1d3)).

When not every class can be placed, the run is **partial**, labelled for example
*Partial · 522/548 placed*. A relaxation first places as many classes as it can, keeping the
planner's locks where it can; the placed classes are then optimised for the soft rules. Every placed
class keeps every hard rule, apart from the waived exceptions it lists (hard score 100, re-checked
against the workbook rows). Each class
left out is listed with the reason (for example: *every room that fits is taken at that time*, with
the rooms and what holds them) and with fixes such as freeing a named room. Applying a fix creates a
new run; the old one stays as it was.

Claude is optional and is never the planner. It turns sentences and files into rule proposals,
proposes edits from the chat panel, and writes explanations. Every proposal goes through the same
validation as a manual move. Import, solving, the calendar, bookings and manual edits work without a
key. Details: [solver README](../smartsched/backend/app/solver/README.md),
[AI README](../smartsched/backend/app/ai/README.md), [research notes](RESEARCH.md).

## Bookings, calendar sync and approvals

Every change to a booking, a series or an approval goes through one function,
`app/services/events.publish_event`, inside the database transaction of the change. It writes the
audit row, sends the e-mail notification when there is one, and calls its subscribers: the calendar
push outbox and the outgoing webhooks. A failing subscriber is logged and never undoes the booking.

- **Audit log.** `audit_events` is append-only; database triggers refuse updates and deletes on SQLite
  and PostgreSQL. Secrets are redacted. A booking create, series create, move or cancel can be undone
  while nothing later has changed it, within 24 hours or before it starts.
- **Calendar sync.** A feed link carries a random token; only its SHA-256 hash is stored. A user can
  hold several links, revoke one or reset all. The organisation switch `calendar_sync_enabled` (KVKK)
  turns every feed into a 404. Google Calendar and Microsoft 365 push appears only after an
  administrator enters the organisation's OAuth client; no client ships with the product.
- **Webhooks.** Signed with HMAC-SHA256, retried with backoff, switched off after five failures in a
  row. They send data outside the server, so `webhooks_enabled` is off by default; payloads carry no
  notes and no e-mail addresses.
- **Approvals.** A rule on a room, a room group or a room type sends requests to designated approvers.
  The booking answers `202` and waits as `PENDING`; the approver approves, rejects or suggests another
  room. A background sweep every 60 seconds expires overdue requests and releases tentative holds. With
  no rule, booking works as in CRBS.
- **Sessions.** Each token carries the user's token version. Sign-out, a password change or reset,
  disabling the account, a role change and deleting the role raise the version, so every earlier
  token stops working on every device.
