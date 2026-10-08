# SmartSched AI layer (`app/ai`)

Claude is used as a **translator and narrator, never as the planner** (docs/RESEARCH.md §4.3,
"Recommendations" 3). Every model output is schema-checked, resolved against the database and, for
timetable edits, validated by the solver before anything changes. Load the `claude-api` skill before
editing anything here.

## Flow

```
prompt text ─┐                                        ┌─> POST /terms/{id}/elicit/accept ─> constraints (source AI / UPLOAD)
             ├─> propose_constraints (strict tool) ──>│   proposals + section edits          + section edits applied
file upload ─┘   names only, ids resolved server-side └── review in the UI (status ok / needs_review / rejected)
(.xlsx .csv .docx .pdf .txt .md)                                       │
                                                                       v
                                       POST /runs  (solve)  ─> run ─> POST /runs/{id}/explain (TR/EN prose)
                                                                │
                              POST /runs/{id}/chat ─> tool loop ─> ProposedDiff (stored on the ChatMessage)
                                                                │      nothing applied
                              POST /runs/{id}/chat/apply ───────┘
                                  re-validate every op ─> child run (parent_run_id, prompt_text)
                                    * moves/swaps/locks only: patched copy, scores from the validator
                                    * constraint / section edits or re_solve: queued repair (stability)
                                      or full re-solve; SSE progress on GET /runs/{child}/events
```

| Module | Role |
|---|---|
| `client.py` | `AIClient` over `anthropic.AsyncAnthropic`: key from the encrypted settings table or a transient key, model from settings (`claude-opus-5-5` fallback), SDK retries/timeouts, server-side refusal fallbacks (`fallbacks="default"`) where supported, effort gating, usage + cost accounting (`UsageTracker`), typed errors (`AIConfigError` -> 409, `AIRefusal` -> 422, `AIUpstreamError` -> 502). `test_connection()` backs `POST /settings/test-ai`. |
| `catalog.py` | One `KindSpec` per registered solver constraint kind (TR/EN title + description, resolved-params JSON schema, examples, allowed hardness), the strict tool definitions, `validate_params`, `validate_tool_input`, `schema_complexity`. Served by `GET /ai/catalog`. |
| `resolve.py` | Term context (rooms, programmes, courses, sections, weeks) and name -> id resolution with `app.importers.normalize` + conservative fuzzy matching. Unresolved names become entities with candidates and `needs_review`; ids are never invented. |
| `elicit.py` | `propose()` (one strict `propose_constraints` round) and `elicit_constraints()`; `accept_proposals()` re-verifies every id against the DB before creating `ConstraintRow`s. |
| `ingest.py` | `extract_preferences()`: file -> numbered units (sheet row / paragraph / table row / PDF line / text line) with heuristic column detection, chunking and explicit limits; each proposal carries `source="UPLOAD"` and `source_ref` (`{"file": "prefs.xlsx", "row": 12, "sheet": ..., "excerpt": ...}`). |
| `edits.py` | `apply_section_edits()`: include / exclude / set enrolment, day/time, mode, preferred rooms. |
| `chat.py` | `handle_chat()` (read tools run, edit tools only record), `apply_diff()` (validation + child run), `explain_run()` (template, or grounded model prose). |
| `prompts/*.md` | System prompts (`mapping.md` is shared by elicitation and chat). |

## Safety rules

1. **Nothing is auto-applied.** Elicitation and uploads return proposals; chat returns a `ProposedDiff`.
   Only `/elicit/accept` and `/chat/apply` write, and both re-validate what the browser sends back.
2. **Strict schemas, re-checked.** All tools are `strict: true` with `additionalProperties: false` and
   every property required. The API limits strict requests to 20 tools, 24 optional and 16 union-typed
   parameters in total, so "unset" is an explicit sentinel (`""`, `[]`, `0`) instead of `null`
   (`test_catalog.py` enforces the budget). Inputs are validated again client-side
   (`validate_tool_input`); truncated (`max_tokens`) or refused turns are never acted on.
3. **Ids come from the database only.** The model names things; `resolve.py` maps names to ids, and
   `accept_proposals` / `apply_diff` check every id again (rooms exist, events belong to the term,
   assignments belong to the run, constraints are in the run's set).
4. **The solver is the judge.** Moves and swaps are evaluated with `app.solver.repair.validate`; an op
   that adds a hard violation is rejected with the validator's message. Re-solves use `repair()` with the
   stability objective (only the neighbourhood of changed events is freed) or a full solve on request.
   Hard rules are never relaxed silently.
5. **Explanations are grounded.** `explain_run` builds facts from the run's diagnosis / stats; model
   prose (structured output) is used only if every number in it appears in those facts, otherwise the
   deterministic TR/EN template is returned.
6. **Secrets.** The key is read decrypted from `settings` per request, passed to the SDK, never logged,
   never returned (`AIClient.__repr__` shows only the last 4 characters). Prompts and outputs are logged
   only as sizes/counts.
7. **Uploaded files are data.** File text is wrapped in `<document>` and the system prompt tells the model
   not to follow instructions in it. Files > 5 MiB are refused; > 1500 units or > 8 chunks are cut with a
   warning (`truncated=true`), never silently.

## Data written

* `constraints`: `source` = `AI` (prompt/chat) or `UPLOAD` (file); `nl_text` = the originating sentence;
  upload refs live in `params["_source_ref"]` until the table has a `source_ref` column (solver selectors
  and `validate_params` ignore keys starting with `_`).
* `chat_messages`: user text; assistant text with `tool_calls` = tool trace, `{"type": "diff", "diff": ..., "applied": <child run id | null>}`
  and `{"type": "usage", "model", "input_tokens", "output_tokens", "cache_*", "estimated_cost_usd"}`.
* `schedule_runs`: child runs with `parent_run_id`, `prompt_text`, `label`, `stats.mode` (`patch` / `repair` / `full`).
* `sections` / `meeting_requests`: section edits (exclude = `needs_room=false`, reversible).

## Adding a tool

1. Define it in `catalog.py` with `_tool(name, description, props)`; keep every property required and
   non-nullable (use sentinels), no `minimum`/`maxLength`-style keywords. Add it to `READ_TOOLS`
   (executed during the loop, must be side-effect free) or `EDIT_TOOLS` (recorded into the diff).
2. Re-run `tests/ai/test_catalog.py`: the complexity budget for the whole chat request must still hold.
3. Read tool: implement `tool_<name>(state, inp, lang)` in `chat.py` and dispatch it in `handle_chat`.
   Edit tool: add a branch in `record_edit` that validates ids against `RunState`, appends a typed op
   (new op types go into `app/schemas/ai.py` `DiffOp`), and handle the op in `apply_diff` with
   server-side re-validation and a `rejected` reason when it fails.
4. Mention the tool's intent in `prompts/chat.md` only if the description is not enough.
5. Test with the scripted fake SDK (`tests/ai/conftest.py`: `fake_sdk.script = [tool(...), text(...)]`).

## Adding a constraint kind

Register it in `app/solver/constraints`; `catalog.KINDS` picks it up automatically (with placeholder
texts). Add a `KindSpec` (TR/EN texts, params schema, examples) and a `MODEL_FIELDS_BY_KIND` hint, and map
the model params in `resolve.resolve_proposal`.

## Tests

`python -m pytest tests/ai -q` (mocked SDK, in-memory / temp SQLite, real CP-SAT for the repair path).
`tests/ai/test_live_smoke.py` calls the real API only when `ANTHROPIC_API_KEY` is set
(`SMARTSCHED_LIVE_MODEL` overrides the model) and checks that the strict schemas compile server-side.
