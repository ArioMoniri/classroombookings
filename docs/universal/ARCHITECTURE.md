# Universal SmartSched — Ingestion Council architecture

Branch `claude/smartsched-universal`. The main branch keeps the rules for this university's own six
workbooks (`docs/DATA_ANALYSIS.md`). This branch generalises onboarding: an institution drops *the files
it has about its schedule*, in any format, language or structure. The **Ingestion Council** reads them
one at a time and turns them into SmartSched rooms, sections, meeting and exam requests, blocks, weeks
and rule proposals. Each value has provenance, uncertain values go to human review, and the reviewed
result is written into a term. The research behind the design is in [RESEARCH-2026.md](RESEARCH-2026.md).

```
               POST /api/v1/council/jobs (multipart files[], mode, lang, year_hint, ai)
                                   │
        ┌──────────────── for each file, one by one ─────────────────┐
        │  intake ──► router ──► known shape? ──yes──► fast path    │   app/council/render.py, fastpath.py
        │   (format, language,        │            (importer parser)  │
        │    grids/units, vision)     no                              │
        │                             ▼                               │
        │                structure analyst ──► extractor              │   structure.py, lexicon.py, extract.py
        │      heuristic voter + model votes → consensus              │   llm.py (report_structure)
        └──────────────────────────────┬──────────────────────────────┘
                                       ▼
          reconciler ──► planner ──► rule miner (per file) ──► critic (+ judge)
          reconcile.py   planner.py   rules.py                 critic.py, llm.py (judge_records)
                                       │
               blackboard: council_jobs / council_steps / council_artifacts (append-only)
                                       │
       GET /review ─► human decisions (POST /review, deterministic re-extract) ─► POST /commit
                                                                                 commit.py
```

## 1. Roles

| Role | Module | Deterministic part | Model part (strict tool) | Output artifact |
|---|---|---|---|---|
| **Intake** | `render.py` | Format by magic bytes and extension (xlsx/xlsm, csv/tsv, txt/md, json, docx, pdf, png/jpg/webp/gif; .xls/.ods/.doc/.pptx refused with a "save as" hint). Workbooks are read in openpyxl read-only mode, with the width bounded by the first 80 rows (Excel reports 16k columns). Merged ranges come from the sheet XML and are forward-filled; hidden sheets are read with a warning. PDF text layer in `layout` mode: runs of ≥ 3 lines with ≥ 3 space-separated cells become a table, and the same header on several pages makes one table. DOCX paragraphs and tables. Language from stop words and script hints. | `transcribe_document`: images and scanned PDFs → tables (rows of cells) plus text lines. Only when the file has no text layer. | `rendered` (summary: grids, units, language, sha256) |
| **Router** | `fastpath.py` | `detect_shape`: the university's `planning-list`, `exam-list`, `weekly-grid` and `room-master` shapes, checked by the importers' own header specs. Known shapes go to the **fast path**: the importers' pure parsers produce records, and on commit the importers write them. `mode=general` turns the fast path off. | — | route on the file (`fast:<shape>` / `general` / `vision` / `error`) |
| **Structure analyst** | `structure.py`, `lexicon.py` | **Timetable axes**: runs of ≥ 4 strictly increasing time slots down a column (vertical) or across a row (horizontal, a transposed board). The row before the run holds entity headers; "day rows" sit above. **Lists**: a header row (most lexicon hits in the first 30 rows; a second header row is merged in). Each column gets a field from the header score (TR/EN/DE/FR/ES/IT/PT synonyms; the longest phrase wins) combined with value fit (times, dates, day names, course codes, integers, people, room codes, long text). Fields are assigned one-to-one, except `notes` and repeated column groups (`DERSLİK │ KAPASİTE │ DERSLİK │ KAPASİTE`). The sheet kind follows from the fields present. | `report_structure`: kind, header row and field per column, each with a confidence. With `COUNCIL_SELF_CONSISTENCY=k` there are k votes and the majority wins. **Consensus** (`llm.merge_votes`): agreement gives noisy-or confidence; disagreement keeps the stronger proposal, caps it below the threshold so it goes to review, and lists the other proposal as an alternative. | `structure` (one `SheetAnalysis` per grid) |
| **Extractor** | `extract.py` | Records from a fixed mapping, re-parsed by the locale-independent parsers in `text.py`: `meeting`, `exam`, `room`, `staff`, `calendar`, `booking` (one per timetable run of equal cells, merged or not). Every record has a `source` (`file` + `sheet`/`row`/`col`/`cell` or `page`/`line`) and `warnings`. Notes and rule-like paragraphs become `rule_text` units. | `report_records`, for prose-only files. Every value must appear in the cited unit and is re-parsed, so the model cannot add data. | `records`, `rule_texts` |
| **Rule miner** | `rules.py` | Without a key it lists the rule-like texts as a review item ("needs the AI model") and invents nothing. | The catalogue's own `propose_constraints` tool and `elicit.build_system`, with a context built from the council's records (transient ORM objects). Proposals stay name-based until commit. | `rules` |
| **Reconciler** | `reconcile.py` | Rooms merge on a punctuation-free key; capacities rank room list > board header > summary sheet; two room lists that disagree are a conflict. Meetings and exams repeated across files are marked `duplicate_of`. Near-duplicate rooms or instructors (similarity ≥ 0.9) become **merge** review items and are never merged silently. | — | `dataset` |
| **Planner** | `planner.py` | Term groups from season words (bahar/spring/güz/fall/yaz/summer/final/büt …) and years in the file name (sheet names when the name is silent), plus exam dates. Room and staff files are *global* and join every group. Weeks: every sheet of a board, plus week numbers from request lists and exam dates. Period grid: the board's time axis, else the default 18-period grid when ≥ 90 % of start times fall on it, else a grid inferred from the starts (GCD step, 15–60 min). | — | `plan` (also `council_jobs.plan`) |
| **Critic / verifier** | `critic.py` | `time_order`, `unknown_room`, `capacity` (students > seats of the assigned rooms), `source_double_booking`, `exam_weekend`, `room_capacity_conflict`, plus **`solver_static:*`**: the records become a `SolverInput` (fixed times on the planner's grid, locked rooms, cohort and instructor keys) and `app.solver.diagnose.static_check` runs on it. Findings are grouped by code. | `judge_records`: a stride sample (`COUNCIL_JUDGE_SAMPLE`) of general-path records next to their source rows → ok / mismatch / unsure. It only flags records. | `issues` |

Every model call goes through `app.ai.client.AIClient.complete`. That means the stored, encrypted key;
server-side refusal fallbacks on current models; usage and cost accounting; typed errors; and one
`strict: true` tool per request with `tool_choice: auto` plus `disable_parallel_tool_use` (forced
`tool_choice` returns a 400 on current models). Inputs are re-validated with `app.ai.catalog._check`.
Truncated (`max_tokens`) or refused turns are discarded, and the step message says so. File content is
wrapped in `<document>` and treated as data (`prompts/council.md`).

## 2. Orchestrator and blackboard

`app/council/orchestrator.py` runs a job on the existing in-process queue (`council:<id>`). It takes
the files one by one, then runs the cross-file steps.

* **`council_jobs`**: status (`QUEUED → RUNNING → REVIEW | READY → COMMITTED`, or `FAILED`), mode
  (`auto` / `general`), `ai_mode` (`llm` / `heuristic`), the file list (stored name, sha256, route,
  counts), the plan, summary, usage and commits. A job interrupted by a restart is marked `FAILED`
  (`recover_interrupted`) and can be re-run.
* **`council_steps`**: one row per agent per file (or per job for cross-file steps), with attempt
  number, status (`RUNNING` / `DONE` / `SKIPPED` / `FAILED`), duration, model, tokens, cost and a
  human-readable message ("no Anthropic API key configured: deterministic path only …", "model output
  truncated …", "token budget exhausted …").
* **`council_artifacts`**: typed, append-only outputs: `rendered`, `structure`, `records`, `rule_texts`,
  `rules`, `dataset`, `plan`, `issues`, `review`, `commit`. The latest artifact per (job, file, kind) is
  current, and the older ones are the audit trail (`GET /council/jobs/{id}/artifacts`).
* **Budgets.** Each step runs under `COUNCIL_STEP_TIMEOUT_S` (`asyncio.wait_for`). The job has
  `COUNCIL_JOB_TOKEN_BUDGET`; once it is spent, the remaining roles keep their deterministic result.
  A failing step never fails the job: intake marks the file failed, and every other role keeps or falls
  back to its deterministic output.
* **Re-runnable.** `POST /council/jobs/{id}/rerun` runs the council again on the stored files (new
  attempts, new artifacts), optionally with another mode or with AI on or off. Review edits re-run
  extraction → reconciliation → planning → critic deterministically for the affected files.

## 3. Human review

`GET /council/jobs/{id}/review` builds the items from the latest artifacts (`app/council/review.py`):

| kind | blocking | decision |
|---|---|---|
| `classification`: sheet kind below `COUNCIL_REVIEW_THRESHOLD` | yes | accept / edit `{kind}` |
| `mapping`: a column below the threshold, or an unmapped column with a candidate | yes | accept / reject (unmap) / edit `{field}` |
| `merge`: near-duplicate room or instructor | yes | accept (written as one) / reject |
| `issue`: critic finding (error, warning) | no | accept (acknowledged) |
| `rule`: a constraint proposal | no | accept / reject / edit `{hardness, weight}`; only accepted rules are committed |
| `rule_text`: rule-like text with no model available | no | acknowledged |
| `plan`: one term group | no | accept / edit `{code, name, kind, week_count, start_date, year}` |
| `file`: a file that could not be read | no | acknowledged |

Decisions are stored as `review` artifacts with the user and time. Unknown item ids and invalid values
are reported back and ignored.

## 4. Commit

`POST /council/jobs/{id}/commit {group | files, term_id | term, include_rules, allow_pending}`
(`app/council/commit.py`):

1. Refused (409) while blocking items are open (`allow_pending` overrides this) or while the job runs.
2. Term: an existing `term_id`, else the planner group edited by the reviewer and overridden by `term`.
   The planner's period grid is stored in `terms.periods_json` when the term has none.
3. **Fast-path files** are written by the university importers in dependency order: `room-master` →
   `weekly-grid` → `planning-list` → `exam-list`. They follow every university rule exactly.
4. **General-path files**: rooms (an existing capacity is kept; a room-master value is never
   overwritten), courses, programmes, faculties and instructors through `importers.catalog.Catalog`,
   sections and meeting requests (times mapped to the term's periods; assigned rooms are definitive,
   status `LOCKED`), exam requests, non-course timetable entries as blocks (course entries are
   *observed*, not imported as bookings), weeks, and staff as instructors. Accepted merges are applied.
   Rows carry `source_key = CC:<job>:<file>:<record>`, so a second commit updates rows instead of
   duplicating them.
5. Accepted rule proposals are resolved against the new term (`ai.resolve.resolve_proposal`) and
   saved with `ai.elicit.accept_proposals`, which re-verifies every id. They are saved with source
   `UPLOAD` and the file/paragraph reference.

Several term groups (for example the user's Bahar, Güz and Final files in one upload) are committed one
group at a time.

## 5. Decision: in-process Python orchestrator, Ruflo only as a developer harness

Ruflo was evaluated as the council runtime (RESEARCH-2026.md §1). It has no documented embeddable API
for a Python server. Its workers are Claude Code processes, and `hive-mind spawn` defaults to
`--dangerously-skip-permissions`. Every CLI command starts a background daemon, checks npm for
updates and adopts a "proven config" into `.claude/` (measured; RUFLO.md). It would also need Node and
a per-worker CLI inside the backend container, and its own SQLite memory instead of our blackboard. The
council needs one strict tool per role, the stored key, the job's audit trail and offline tests. The
in-process orchestrator provides all of that in plain Python (about 5.8k formatted lines in `app/council`)
and adds no runtime dependency.
**Ruflo is used to orchestrate the development agents** (`.claude/agents/*`; RUFLO.md). If Ruflo ships
an embeddable runtime with safe defaults, the agent interface (`render`/`analyze`/`extract`/… are pure
functions over typed artifacts) can be put behind an adapter. That item is in the ROADMAP backlog.

## 6. Settings

| Variable | Default | Meaning |
|---|---|---|
| `COUNCIL_AI` | `1` | Use Claude when a key is configured (`0` = deterministic only). The per-job form field `ai=false` does the same for one job. |
| `COUNCIL_MODEL` | `""` | Model for the council; empty = `ANTHROPIC_MODEL` / Settings (`claude-opus-5-5`). |
| `COUNCIL_FAST_MODEL` | `""` | Model for vision and the judge; empty = `COUNCIL_MODEL`. Set `claude-haiku-5-5` to cut cost. |
| `COUNCIL_REVIEW_THRESHOLD` | `0.75` | Below this confidence an item needs review; per job via the form field `review_threshold`. |
| `COUNCIL_STEP_TIMEOUT_S` | `300` | Per step. |
| `COUNCIL_JOB_TOKEN_BUDGET` | `600000` | Input + output tokens per job. |
| `COUNCIL_MAX_FILES` / `COUNCIL_MAX_FILE_MB` | `25` / `15` | Upload limits (nginx accepts 50 MB per request). |
| `COUNCIL_SELF_CONSISTENCY` | `1` | Model votes per sheet. |
| `COUNCIL_JUDGE_SAMPLE` | `12` | Records per file for the judge; `0` = off. |

Deployment is unchanged: `smartsched/deploy/deploy.sh` (one click). It runs Alembic up to
`0003_council`, the variables above are in `.env.example` and `docker-compose.yml`, and nginx streams
`/api/v1/council/jobs/{id}/events` unbuffered. See `smartsched/deploy/README.md` → "Onboarding (Ingestion
Council)".

## 7. What is verified, and how

* **The fast path is equivalent to the importers.** All six real workbooks and the room master route to
  the fast path (`tests/council/test_intake_structure.py`).
* **The general path, forced on the same files, gives the same results**
  (`tests/council/test_general_vs_fast.py`):
  * planning lists: meeting count within 0.5 %, ≥ 99 % of the course codes, and ≥ 97 % of rows with the
    same days, start and assigned rooms;
  * exam list: ≥ 95 % of rows with the same code, date and start;
  * timetable boards (Final, Güz, and the first four Bahar weeks): **the same occupied room-slots, cell
    for cell**.
* **Variants built from the real records** (`tests/fixtures/universal/build_*.py`):
  * English CSV: ≥ 97 % of meetings equal to the Bahar list;
  * printed PDF: ≥ 95 % of the first 120 exam rows;
  * DOCX memo: all 36 room capacities equal to the room master, and the notes become rule texts;
  * transposed board: identical bookings;
  * PNG scan: vision path, model mocked with the page's real rows.
* **Cross-file** (`test_cross_file.py`): the six files group into 2026-BAHAR, 2026-FINAL and
  2026-2027-GUZ, with the room master global. The critic finds the real over-full request (MAT112: 180
  students, 156 seats) and the solver static checker runs.
* **API end to end** (`test_council_api.py`): heuristic job → review → commit (idempotent re-commit),
  blocking review flow with a mapping edit that re-runs extraction, fast-path commit through the
  importers, image without a key, SSE, auth and limits.
* **With the model** (`test_council_llm.py`, SDK mocked at the client boundary): strict tool requests,
  consensus with a disputed column, rule proposal → committed `ConstraintRow` (`UPLOAD`, source ref),
  judge mismatch issue, vision intake, truncated or invalid outputs discarded, token budget.
  `test_live_council.py` runs against the real API when `ANTHROPIC_API_KEY` is set.
* **Migration** (`test_council_migration.py`): `0003_council` creates the three tables, which match the
  models.
