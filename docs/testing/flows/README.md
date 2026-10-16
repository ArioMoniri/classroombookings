# Flow loop: how to run a flow and report it

Ledger: `flow-test-plan-2026-10-15` · Written by the test planner (Fatih Bey, classroom planning officer) · 2026-10-15
Owner request (docs/ROADMAP.md, "Standing flow loop: test → suggest → build → re-test"): tester agents run every feature flow step by step as academician, staff and admin, on desktop and on touch devices. A suggester turns their reports into tickets, builder agents fix them, and the testers re-verify.

This folder holds what the testers run:

| File | What it is |
|---|---|
| `README.md` (this file) | stack, browser, viewports, data, evidence, report format, KVKK rules |
| `MOBILE.md` | acceptance criteria every screen must pass at 390×844 and 768×1024, each with a Playwright assertion |
| `SUGGESTER.md` | how tester reports become tickets in docs/ROADMAP.md "Flow loop tickets" |
| `F-01-…` to `F-13-…` | one flow each: preconditions, numbered steps per persona, the expected result per step, mobile expectations |

Inputs these scripts are built on (read them when a step is unclear):
- earlier findings: `docs/testing/2026-10-15-persona-{user,academician,admin}.md` (issue ids U-, A-, M-), `docs/testing/2026-10-15-academician-needs.md` (scenarios I1–I13, L1–L11, S1–S4, M1–M9), `docs/review/2026-10-15-uiux-visual-review.md` (mobile findings), `docs/review/2026-10-15-motion-audit.md` (probe method);
- design specs: `docs/design/v2/phase19-{intake,moderation,priority-policy,program-wizard,suggestions}.md`, `docs/design/*.md`;
- owner decisions: `docs/ROADMAP.md`, in particular "Approval-first bookings + user channels + credential-free login", "Phase 19 UX decisions" and "Solver decisions".

---

## 1. Flow index and what can be tested today

Snapshot read for this plan: `origin/claude/gracious-cerf-w1598m` at `b75047b` (2026-10-15 22:30); F-01 S13 and the F-12 SSO part were revised against `d2ed4a8` after the owner decisions of 22:45/22:50. "Today" means on those commits.

| Flow | Name | Personas | Testable on b75047b | What blocks the rest |
|---|---|---|---|---|
| F-01 | Request an empty slot → approve / reject with reason → notified → withdraw | staff, academician, admin | **Partly.** Backend complete (approval_mode, reason codes, notify_dispatch, preferences API). UI: request, approve, withdraw, bell work | frontend builder not started: approval-mode setting, reject dialog with required reason code + text, reason in My bookings, Profile › Bildirimler. External channels (Apprise + pywebpush, decided 22:45) have no API or UI yet |
| F-02 | Direct booking (admin/approver bypass), recurring with book/skip/replace, cancel with scope | admin, staff | **Yes** | – |
| F-03 | Find a room with capacity + feature → reserve from the results | staff, academician | **Yes** (features need the starter catalogue, see preconditions) | – |
| F-04 | My bookings + ICS feed subscribe + regenerate | staff, academician | **Yes**, after the admin KVKK sign-off for calendar sync (API only: no admin screen, M-40) | admin KVKK screen |
| F-05 | Academician "Taleplerim" self-view, then the coordinator's moderation of that person | academician, admin | **Mostly** (P19 UI follow-up 2026-10-16: Taleplerim nav, person/programme priority, baseline + chain, "Akademisyenlere bildir" publish notices). The login ↔ instructor link has an API (`PUT /auth/sso/admin/users/{id}/instructor`) | "Tercih ekle" (P19-T2, backend) |
| F-06 | Learned suggestions accept / reject / snooze + memory reset / undo | admin, planner | **Yes** | – |
| F-07 | Program from scratch → pre-check → generate → publish | admin | **Yes** (server drafts, P19 UI follow-up 2026-10-16) | – |
| F-08 | File intake: Bahar xlsx + CSV export + scanned PDF (AI off) → review → dry-run diff → commit → remembered mappings | admin | **Partly.** Council API complete (rows, decisions, dry-run, memory). The Phase 19 intake UI (stepper, Fark step, remembered chips) is assigned to the design-system agent and not built | intake UI (I7, onboarding frontend hand-off) |
| F-09 | Generator Studio → run → honest run report → publish / partial-publish confirm | admin, planner | **Yes** | – |
| F-10 | Timetable: open a class, keyboard move, forced move with a reason (admin), undo | admin, planner | **Partly.** Forced move with a written reason has backend support (M-02/M-09) but no UI field yet | forced-move reason UI (design-system agent hand-off) |
| F-11 | Admin setup: users/roles (no escalation), rooms + features, approval rules / mode, KVKK sign-offs | admin, limited admin | **Partly.** Approval-mode setting and the calendar-sync KVKK screen have no UI; the AI-policy screen exists | approval-mode UI, KVKK screen (M-40) |
| F-12 | Login, logout, password change, session expiry; Microsoft Entra ID sign-in | all | **Yes** for local login. **SSO partly:** the provider is decided (Entra ID, 22:45/22:50) and the backend (`/auth/sso/*`) exists, so config guards, the start redirect, callback refusals, invites and break-glass are testable via API | sign-in page (docs/design/v2/sign-in.md) not built; a real round trip needs tenant credentials from IT; spec/backend path mismatch (`/auth/oidc/microsoft` vs `/auth/sso/entra`) |
| F-13 | TR/EN, reduced motion, keyboard-only pass over F-01..F-04 | all | **Yes** (inherits F-01's UI gaps) | – |

Live AI is never needed. Every flow runs with **no Anthropic key** and AI intake switched off. Steps that would need a key are marked `NEEDS-AI` and are skipped (report `SKIP`, reason "no AI key").

---

## 2. Personas and accounts

Every account is fictional, uses `@smartsched.local`, and carries initials only (KVKK, §7).

| Persona | Who | Account | Role | Created by |
|---|---|---|---|---|
| **admin** | Fatih Bey, classroom planning officer and system administrator; also the designated approver for every room | `admin@smartsched.local` / `Admin-2026!` | ADMIN | `stack.sh` seed |
| **staff** | department staff member who books rooms (no teaching load in the data) | `personel.test@smartsched.local` / `Flow-2026!pw`, name "P. T." | TEACHER (CRBS "Teacher": `book_single.create`, `room.view`) | §4.4 seed |
| **academician** | senior academician, the instructor of PSY 278 (Bahar) / PSY 277 (Güz), A-block habit 8/8 | `akademisyen.test@smartsched.local` / `Flow-2026!pw`, name "A. T." | TEACHER, linked to that instructor | §4.4 seed |
| planner (helper) | planning office member without admin rights; used for permission refusals | `planner.test@smartsched.local` / `Flow-2026!pw`, name "P. L." | PLANNER | §4.4 seed |
| limited admin (helper, F-11) | user admin without planning rights; used for no-escalation checks | `limited.admin@smartsched.local` / `Flow-2026!pw` | custom role, made in F-11 | F-11 |

`stack.sh` with `REC_TEACHER=1` also creates `ogretmen@smartsched.local` ("Ayşe Öğretmen", TEACHER). Do not use it in screenshots: rename it to "A. Ö." in the masking step or leave it unused.

---

## 3. Viewports and browser

- **Browser:** Playwright **library** (not the test runner), Chromium from `/opt/pw-browsers` (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; `chromium-1194`, headless shell). Playwright itself is `smartsched/frontend/node_modules/playwright` (1.56.1). Scripts live in the tester's scratch folder and load Playwright by path, like `measure.mjs`:
  ```js
  import { createRequire } from "node:module";
  const require = createRequire(import.meta.url);
  const { chromium } = require(process.env.PW ?? "/home/user/classroombookings/smartsched/frontend/node_modules/playwright");
  ```
- **Viewports.** Every flow runs in all three unless the flow says otherwise.

  | Id | Context options | Interaction API |
  |---|---|---|
  | `desktop` | `{ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: "tr-TR", timezoneId: "Europe/Istanbul" }` | `click`, `keyboard`, `hover` |
  | `tablet` | `{ viewport: { width: 768, height: 1024 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" }` | `tap` only |
  | `phone` | `{ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" }` | `tap` only |

  For `tablet` and `phone`, also emulate a coarse pointer without hover right after `newPage()`, so `@media (hover: none)` and `(pointer: coarse)` rules apply whatever the Chromium build infers:
  ```js
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "hover", value: "none" }, { name: "pointer", value: "coarse" }, { name: "any-hover", value: "none" }] });
  ```
  On touch viewports, never call `hover()` and never use `click()` on an element only reachable after a hover: a step that needs a hover there FAILs (MOBILE.md M-11).
- **Timezone is mandatory.** The backend uses Europe/Istanbul. A UTC browser hides or shows the wrong past periods (U-04).
- **Language.** `locale: "tr-TR"`. The UI follows the **profile** language (`PUT /auth/profile {"language":"tr"}`, set by the seed), not the browser. F-13 switches it.
- **Theme.** Light by default. F-13 repeats a sample in dark.
- **Mobile pass = the flow plus MOBILE.md.** On `phone` and `tablet`, run MOBILE.md M-01…M-14 on every screen the flow visits, once per screen per viewport, and report each criterion as its own row (`step` = `M-xx@<route>`).

---

## 4. Running a flow

### 4.1 Frozen snapshot of the pushed HEAD

Test what is pushed, never the shared working tree (other agents edit it while you test).

```bash
REPO=/home/user/classroombookings
BR=claude/gracious-cerf-w1598m
git -C "$REPO" fetch -q origin "$BR"
SHA=$(git -C "$REPO" rev-parse "origin/$BR"); S7=${SHA:0:7}
SCR=<your scratchpad>                      # the session scratch folder, never inside the repo
SNAP="$SCR/flow-src-$S7"
git -C "$REPO" worktree add --detach "$SNAP" "$SHA"
ln -sfn "$REPO/smartsched/frontend/node_modules" "$SNAP/smartsched/frontend/node_modules"
```

- Write `$SHA` into the report header. Every step result belongs to that commit.
- Do not edit anything under `$SNAP`. It is a test object.
- At the end of the round: `git -C "$REPO" worktree remove --force "$SNAP"` (the owner wants no stray worktrees).
- The backend runs on the system `python3` (FastAPI, OR-Tools, openpyxl, Pillow and reportlab are installed). `stack.sh` uses `$SNAP/smartsched/backend/.venv` instead when it exists.

### 4.2 An isolated stack per tester

`scripts/record/stack.sh` builds everything outside the repository, under its own `REC_WORKDIR`, on its own ports, from the snapshot's code (it resolves its root from its own path).

Port plan (pick your row; never reuse another tester's ports):

| Tester | `REC_API_PORT` | `REC_WEB_PORT` |
|---|---|---|
| staff | 19110 | 19111 |
| academician | 19120 | 19121 |
| admin | 19130 | 19131 |
| admin, fresh stack (F-07 empty term, F-08) | 19132 | 19133 |
| re-test runs | +100 on the row above | +100 |

```bash
export REC_WORKDIR="$SCR/flow-stack-<persona>" REC_API_PORT=191x0 REC_WEB_PORT=191x1
export REC_TEACHER=1 REC_LANG=tr
bash "$SNAP/scripts/record/stack.sh" up          # ≈ 2–4 min: all three terms + room master, prod build
REC_RUNS="2026-BAHAR:WEEK:3:120 2026-BAHAR:TERM:-:240 2026-GUZ:WEEK:3:120 2026-GUZ:TERM:-:240" \
  bash "$SNAP/scripts/record/stack.sh" runs      # ≈ 15 min: real solver runs; full-term runs are published
export SMTP_PORT=2526 SINK="$SCR/flow-mail-<persona>"   # one port per tester: 2526 staff, 2527 academician, 2528 admin
python3 -I "$SCR/smtp_sink.py" "$SMTP_PORT" "$SINK" &      # §4.5; keep it running for the whole round (or start it as a background task)
bash "$SCR/flow-seed.sh"                        # §4.4: accounts, link, masking, SMTP settings, approver
bash "$SNAP/scripts/record/stack.sh" snapshot    # every flow then starts from this state in seconds
```

Before **each flow**: `REC_SNAPSHOT=1 REC_SKIP_BUILD=1 bash "$SNAP/scripts/record/stack.sh" up` (restores the database and uploads, keeps the build), then apply the flow's own preconditions. Flows mutate data. Never run two flows on one stack at the same time.

- The fresh stack (`stack.sh up --fresh`) has only the admin and an empty `2026-BAHAR` term. F-08 uses it.
- `stack.sh status` prints PIDs and URLs. `stack.sh down` (with the same env) stops **only your** stack. Never `pkill -f`: other agents' servers run on this host (ROADMAP "Agent hygiene").
- Record `uptime` (load average) in the report header. The host has 4 cores and is shared.

### 4.3 Dates

The booking flows use the current term **Güz 2026-27** (`2026-GUZ`, 21 Sep–27 Dec 2026, 14 weeks, 18 periods, holiday Thu 29 Oct "Cumhuriyet Bayramı"). Compute the dates once per run and write them in the report header:

```js
// node dates.mjs  → prints the variables the flows use
const tz = "Europe/Istanbul";
const today = new Date(new Date().toLocaleString("en-US", { timeZone: tz }));
const iso = (d) => d.toLocaleDateString("sv-SE");
const next = (from, wd, minDays) => { const d = new Date(from); d.setDate(d.getDate() + minDays); while (d.getDay() !== wd) d.setDate(d.getDate() + 1); return d; };
const D1 = next(today, 4, 3);                    // a Thursday ≥ 3 days ahead
if (iso(D1) === "2026-10-29") D1.setDate(D1.getDate() + 7);   // never the holiday
const D2 = next(D1, 1, 1);                        // the Monday after D1
const plus = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const D3 = plus(D1, 14), D4 = plus(D1, 21), D6 = plus(D1, 35);   // Thursdays 2, 3 and 5 weeks after D1
console.log(JSON.stringify({ TODAY: iso(today), D1: iso(D1), D2: iso(D2), D3: iso(D3), D4: iso(D4), D6: iso(D6) }));
```

On 2026-10-15 this gives `D1 = 2026-10-22`, `D2 = 2026-10-26`, `D3 = 2026-11-05`, `D4 = 2026-11-12`, `D6 = 2026-11-26`; the holiday 29 Oct lies between D1 and D3, which F-02 relies on. If `TODAY` is after 2026-12-10, the Güz term is too short for the recurring steps: report F-02 S05–S10 as `BLOCKED (term ends)`.

Planning flows (F-05, F-09, F-10) use **Bahar 2026** (`2026-BAHAR`, week 1 starts Mon 2 Feb 2026), where the scenario data lives (PHAR 240 §1, nursing year 1, ING 302).

### 4.4 Common seed (`flow-seed.sh`)

Save this to `$SCR/flow-seed.sh`. It changes only the throwaway database of your stack. Each block is idempotent.

```bash
#!/usr/bin/env bash
set -euo pipefail
API="http://127.0.0.1:$REC_API_PORT/api/v1"; DB="$REC_WORKDIR/rec.db"
tok() { curl -fsS -X POST "$API/auth/login" -H 'content-type: application/json' -d "{\"email\":\"$1\",\"password\":\"$2\"}" | jq -r .access_token; }
A=$(tok admin@smartsched.local 'Admin-2026!'); H=(-H "Authorization: Bearer $A" -H 'content-type: application/json')

# 1. accounts (initials only)
for u in "personel.test|P. T.|TEACHER" "akademisyen.test|A. T.|TEACHER" "planner.test|P. L.|PLANNER"; do
  IFS='|' read -r e n r <<<"$u"
  curl -sS -o /dev/null -w "user $e %{http_code}\n" -X POST "$API/users" "${H[@]}" \
    -d "{\"email\":\"$e@smartsched.local\",\"full_name\":\"$n\",\"role\":\"$r\",\"password\":\"Flow-2026!pw\"}"
done
for e in personel.test akademisyen.test planner.test; do
  T=$(tok "$e@smartsched.local" 'Flow-2026!pw')
  curl -fsS -o /dev/null -X PUT "$API/auth/profile" -H "Authorization: Bearer $T" -H 'content-type: application/json' -d '{"language":"tr"}'
done

# 2. the admin approves for every room (designated approver)
ADMIN_ID=$(curl -fsS "$API/auth/me" -H "Authorization: Bearer $A" | jq -r '.id // .user.id')
curl -fsS -o /dev/null -X PUT "$API/approvals/approvers/$ADMIN_ID" "${H[@]}" -d '{"scopes":[{"type":"all"}]}'

# 3. SMTP test sink (§4.5), then the SmartSched SMTP settings and one test mail
curl -fsS -o /dev/null -X PUT "$API/org/smtp" "${H[@]}" \
  -d "{\"host\":\"127.0.0.1\",\"port\":$SMTP_PORT,\"security\":\"none\",\"from_address\":\"noreply@smartsched.local\",\"from_name\":\"SmartSched\"}"
curl -fsS -X POST "$API/org/smtp/test" "${H[@]}" -d '{"to":"admin@smartsched.local"}' | jq -c .   # expect "status":"SENT"

# 4. test fixture (NOT a product feature; no API exists, see F-05): link the academician to the PSY 278 instructor,
#    and mask every person name to initials (KVKK, §7). Runs on the throwaway SQLite file only.
python3 -I - "$DB" <<'PY'
import re, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
uid = db.execute("select id from users where email='akademisyen.test@smartsched.local'").fetchone()[0]
iid = db.execute("""select si.instructor_id from section_instructors si join sections s on s.id=si.section_id
  join courses c on c.id=s.course_id where c.code in ('PSY278','PSY 278') order by si.instructor_id limit 1""").fetchone()[0]
db.execute("update instructors set user_id=null where user_id=?", (uid,))
db.execute("update instructors set user_id=? where id=?", (uid, iid))
TITLES = {"prof.", "doç.", "dr.", "öğr.", "üyesi", "gör.", "arş.", "uzm.", "okt.", "prof", "doç", "dr", "öğr", "gör", "arş"}
def initials(name):
    if not name: return name
    out = []
    for w in re.split(r"\s+", name.strip()):
        out.append(w if w.lower() in TITLES or re.fullmatch(r"\w\.", w) else (w[0].upper() + "."))
    return " ".join(out)
for table, col in (("instructors", "full_name"), ("users", "full_name")):
    for rid, v in db.execute(f"select id, {col} from {table}").fetchall():
        if v and v not in ("Administrator", "Yönetici") and initials(v) != v:
            db.execute(f"update {table} set {col}=? where id=?", (initials(v), rid))
db.commit()
print("linked user", uid, "-> instructor", iid)
PY
echo "ACADEMICIAN_INSTRUCTOR_ID=$(python3 -I -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute(\"select id from instructors where user_id=(select id from users where email='akademisyen.test@smartsched.local')\").fetchone()[0])" "$DB")"
```

- If the schema has moved (a column renamed), fix the fixture SQL in your scratch copy and note it in the report. It is not a product defect.
- After the seed, run `stack.sh snapshot`. The flow-specific preconditions (approval mode, approval rules, KVKK sign-offs, features) are set per flow, after the restore.

### 4.5 SMTP test sink

There is no mail server on the host and `aiosmtpd` is not installed. This standard-library sink accepts every message and writes it to `$SINK/<n>.eml`. Start it before the seed (`SMTP_PORT=2525+N`, one per tester), in the background:

```python
# smtp_sink.py  —  python3 -I smtp_sink.py <port> <dir>
import asyncio, pathlib, sys
port, out = int(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
async def handle(r, w):
    send = lambda s: (w.write((s + "\r\n").encode()), None)[1]
    send("220 sink ESMTP"); await w.drain(); data = None
    while line := await r.readline():
        cmd = line.decode("utf-8", "replace").strip()
        if data is not None:
            if cmd == ".":
                n = len(list(out.glob("*.eml"))) + 1
                (out / f"{n:04d}.eml").write_bytes(b"".join(data)); data = None; send("250 queued")
            else:
                data.append(line[1:] if line.startswith(b"..") else line)
        elif cmd.upper().startswith(("EHLO", "HELO")): send("250-sink"); send("250 8BITMIME")
        elif cmd.upper() == "DATA": data = []; send("354 end with .")
        elif cmd.upper() == "QUIT": send("221 bye"); await w.drain(); break
        else: send("250 ok")
        await w.drain()
    w.close()
async def main(): await (await asyncio.start_server(handle, "127.0.0.1", port)).serve_forever()
asyncio.run(main())
```

Read a message with `python3 -I -c "import email,sys;from email import policy;m=email.message_from_bytes(open(sys.argv[1],'rb').read(),policy=policy.default);print(m['To'],'|',m['Subject']);print(m.get_body(('plain',)).get_content())" $SINK/0002.eml`. Queued mails leave through the integrations worker after the commit (retries 1 min, 5 min, …). Poll the sink folder for up to 90 s before you report a missing e-mail.

### 4.6 Locators

1. The `data-testid` the flow names (they are listed per step; most already exist).
2. Otherwise `getByRole(role, { name })` with the **Turkish** name quoted in the step.
3. Never CSS classes or DOM position.

When the behaviour is there but the named locator is not, the step **PASSes** with the note `locator drift: <what you used>` (the suggester files a trivial ticket). When the behaviour is missing, the step FAILs.

### 4.7 Checks on every step (do not repeat them in the flow files)

Collect these for the whole flow and attach them to the step where they happened:
- `page.on("pageerror")` and `console.error`: each is a finding (React hydration errors were M-37).
- Responses with status ≥ 500, or an unexpected 401/403 on a page the persona may use: FAIL that step.
- After a successful action (submit, approve, withdraw, cancel, save), `document.activeElement` is not `BODY` (U-07, A-21, motion T4).
- In TR mode, the surface you touched shows no English UI words (U-09, M-36). Note the exact string.
- Busy state: a pressed button that waits shows a gerund label (`"Aranıyor…"`, `"Kaydediliyor…"`) and `aria-busy="true"` (motion T1).
- The toast text, quoted exactly.

---

## 5. Evidence

```
EV="$SCR/flow-ev/<YYYY-MM-DD>/<F-xx>/<persona>"
  shots/F01-S03-staff-phone.png      # <flow>-<step>-<persona>-<viewport>.png
  curl/F01-S04-decide.txt            # exact request + status + body, tokens redacted
  mail/0002.eml                      # copies of the sink messages the flow produced
  logs/console.jsonl  logs/http.jsonl  perf/<step>.json
  scripts/*.mjs                      # the Playwright scripts you ran, so a re-test can repeat them
```

- Evidence stays in the scratch folder. **Never commit screenshots.** The report cites paths.
- Redact secrets in every saved text: `Authorization: Bearer <redacted>`, ICS feed tokens `…/feeds/<redacted>/mine.ics`, reset codes, webhook secrets.
- One full-page screenshot per step per viewport is enough. Add a crop when the finding is small.

---

## 6. Report format

One report per flow, persona and round: `docs/testing/flows/reports/<YYYY-MM-DD>-<F-xx>-<persona>.md`. Header:

```
# F-01 · staff · round 1 · 2026-10-16
Snapshot: b75047b (origin/claude/gracious-cerf-w1598m) · stack API :19110 web :19111 · load 11.8/4 cores
Dates: TODAY 2026-10-16 · D1 2026-10-22 · D2 2026-10-26 · D3 2026-11-05 · D4 2026-11-12 · D6 2026-11-26 · Chromium 141 (chromium-1194)
Preconditions applied: approval_mode=all, approver=admin(all rooms), SMTP sink :2526
```

Then one table, one row per step × viewport (and per MOBILE.md criterion on touch viewports):

| Flow | Step | Persona | Viewport | Result | Evidence | Issue |
|---|---|---|---|---|---|---|
| F-01 | S03 | staff | phone | FAIL | `shots/F01-S03-staff-phone.png`, `logs/http.jsonl#L14` | FL-01-004 |
| F-01 | M-02@/bookings | staff | phone | PASS | `perf/M02-bookings.json` | – |

- **Result** is one of `PASS` · `FAIL` · `BLOCKED` (a precondition or an unbuilt feature; give the reason in the issue cell, e.g. `BLOCKED: reject dialog not built`) · `SKIP` (not applicable, e.g. `NEEDS-AI`) · `INCONCLUSIVE` (timing under host load, §8).
- **Issue** ids are `FL-<flow>-<nnn>` (`FL-01-004`), numbered per flow and kept across rounds: a re-test reuses the id.
- Under the table, one block per issue:

```
### FL-01-004 (major) Reject dialog lets an empty reason through
- Step: F-01 S07 · persona admin · viewport desktop, phone
- Expected: "Reddet" stays disabled until a reason code is chosen ("Diğer" also needs text); API 422 reason_required otherwise
- Actual: dialog has only "Talep edene not"; POST /approvals/12/decide {"decision":"reject"} → 422 (backend correct, UI cannot recover)
- Evidence: shots/F01-S07-admin-desktop.png, curl/F01-S07-decide.txt
- Seen before as: – (new) | U-xx / A-xx / M-xx | ROADMAP line "…"
- File hints: smartsched/frontend/src/components/approvals/…
```

- End with a fenced `jsonl` block, one object per row, for the suggester:
  `{"flow":"F-01","step":"S03","persona":"staff","viewport":"phone","result":"FAIL","evidence":["shots/…"],"issue":"FL-01-004","severity":"major","sha":"b75047b"}`
- Severity, as in the persona reports: **blocker** (a persona cannot finish the flow, data loss, a security or KVKK leak) · **major** (wrong result, missing core step, a11y failure on the main path, a MOBILE.md criterion failed on a primary screen) · **minor** (friction, wording, a secondary screen) · **trivial** (locator drift, cosmetic).

---

## 7. KVKK rules for testers

- **Initials only in screenshots.** The seed (§4.4) rewrites every instructor and user name in the throwaway database to title + initials ("Dr. Öğr. Üyesi A. Y."). Check before the first screenshot that no word of two or more letters survives outside the titles (expect `0`):
  ```bash
  python3 -I -c "import re,sqlite3,sys;T={'prof.','doç.','dr.','öğr.','üyesi','gör.','arş.','uzm.','okt.'};db=sqlite3.connect(sys.argv[1]);print(sum(1 for (v,) in db.execute('select full_name from instructors union all select full_name from users') if v and v not in ('Administrator','Yönetici') and any(len(w)>2 and w.lower() not in T for w in re.split(r'\\s+',v))))" "$REC_WORKDIR/rec.db"
  ```
  Then open the class inspector of PSY 278 and confirm it shows initials.
- F-08 imports the real workbooks into a **fresh** stack, so names arrive unmasked during review. Every screenshot of a row table there passes `mask: [page.locator("table tbody, [role=grid] [role=row]:not(:first-child), [data-testid=review-row]")]`, and the report quotes counts, never cell values. Run the masking block of §4.4 right after the commit step, before any other screenshot.
- Type only neutral text in notes and titles: "Telafi dersi", "Bölüm toplantısı", "Ders tekrarı". Never a real name.
- E-mails go to the local sink only. Never configure a real SMTP server, and never put a real address in a test account.
- Do not paste feed tokens, JWTs, reset codes or real names into reports or tickets.
- The evidence folder is scratch. It is deleted with the session and never committed.

---

## 8. Performance and motion numbers

MOBILE.md M-14 and some flow steps measure frames with the motion-audit probe (the `measure.mjs` method: an rAF frame counter, a `long-animation-frame` PerformanceObserver and a Chrome trace for Layout events; see `docs/review/2026-10-15-motion-audit.md` §1). A copy of the probe functions is in MOBILE.md M-14.

- Run the no-op baseline (4 clicks on the page `h1`) first, in the same session.
- If the baseline drops more than 1 frame per interaction, or the load average exceeds the core count, mark timing rows `INCONCLUSIVE` and record the load. Functional results stand.
- Gate: worst long animation frame ≤ 200 ms per tap (M-14). Report dropped frames per interaction too (the CI gate is ≤ 3); they are not a FAIL on their own on this shared host.

---

## 9. Round protocol

1. **Round N test.** Each persona tester runs its flows (the persona column in §1) on a new snapshot, writes one report per flow and hands the report paths to the suggester.
2. **Suggest.** The suggester (SUGGESTER.md) turns reports into tickets under docs/ROADMAP.md "Flow loop tickets".
3. **Build.** Dedicated loop builders fix tickets in non-overlapping file scopes, test-first, and name the ticket ids in their commits.
4. **Re-test.** The same persona re-runs only the affected steps (plus the whole flow if a ticket touched a shared component), on a snapshot that contains the fix commit. In the report and in the ticket line: `verified <sha> <date>` or `reopened <sha> <date>: <what still fails>`.
5. A flow is **green** when every step is PASS or a documented SKIP on all three viewports, and MOBILE.md passes on every screen it visits.
