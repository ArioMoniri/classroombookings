# Universal SmartSched — research for the Ingestion Council (2026)

*Research for the `claude/smartsched-universal` branch. It was compiled on 2026-10-08 from web sources
and from hands-on runs of the Ruflo CLI in a scratch copy of this repository. Claims are cited inline, and
all sources are collected at the end. **[measured]** marks what we observed ourselves; **[unverified]**
marks claims that come only from secondary sources.*

The question this answers: *an institution drops "the files they have about the schedule" — any format,
any language, any structure — and SmartSched must turn them, one file at a time, into rooms, sections,
meeting and exam requests, blocks, a term calendar and rules, with provenance and human review.* The
companion design is [ARCHITECTURE.md](ARCHITECTURE.md); the Ruflo developer harness is in
[RUFLO.md](RUFLO.md).

## Executive summary

1. **Ruflo (formerly Claude Flow) is a strong *developer* harness but not a fit for the *backend
   runtime*.** It is MIT-licensed and actively released (v3.55.0 on npm today), and it adds swarm
   topologies, shared memory, ~100 agent templates and a 300-tool MCP server to Claude Code
   ([README](https://github.com/ruvnet/ruflo); [releases](https://github.com/ruvnet/ruflo/releases)).
   It has no documented embeddable API for a Python server, and its agents run by launching Claude Code.
   `hive-mind spawn --claude` defaults `--dangerously-skip-permissions` to **true** **[measured]**, and
   even `--help` performs an update check that writes `~/.claude-flow/update-state.json`
   **[measured]**. We therefore use Ruflo to orchestrate our `.claude/agents/*` during development, and we
   keep the production council as an **in-process Python orchestrator** over the existing strict-tool
   `AIClient` (§1.6).
2. **Deterministic parsing first, LLM second.** For native digital formats (xlsx, csv, docx and
   text-layer PDF), local libraries give exact cells for free. The LLM is worth its cost in three
   places: deciding *what a table means* (classification and schema mapping), reading *free text*
   (rules and memos), and reading *pixels* (scans and photos). This matches Anthropic's own advice to
   start from the simplest workflow and add agents only where the subtasks cannot be predicted
   ([Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)).
3. **Spreadsheets are the hard case, and it is not a parsing problem.** Merged cells, multi-row
   headers and pivot-like timetables (rooms × time slots × days) break naive "first row = header"
   tools. SpreadsheetLLM shows that structural anchors plus compressed encodings beat plain
   serialization for LLM table detection (78.9 % F1, a 25× compression ratio)
   ([arXiv 2407.09025](https://arxiv.org/html/2407.09025v1)). We adopt the same idea: send the model
   the *anchors* (header candidates, axis cells, merged ranges, column statistics), not the whole sheet.
4. **Schema mapping should be "cheap retrieve, LLM rerank, human confirm".** Magneto (PVLDB 2025)
   pairs a small-model candidate generator with an LLM reranker and matches or beats the prior state
   of the art at lower cost ([arXiv 2412.08194](https://arxiv.org/abs/2412.08194)). Our version: a
   multilingual synonym lexicon proposes candidates with scores, the model adjudicates, and any column
   whose confidence stays below the threshold goes to the review screen.
5. **Validation is layered.** The order is schema-strict tool output, then deterministic cross-checks
   (types, ranges, duplicates, the solver's own `static_check`), then a sampled LLM-as-judge pass, then
   human review. LLM judges agree with humans about as often as humans agree with each other (> 80 %),
   but they show position, verbosity and self-preference biases
   ([Zheng et al. 2023](https://arxiv.org/abs/2306.05685)), so the judge only *flags* records and never
   edits them. Self-consistency, meaning majority voting over several samples
   ([Wang et al. 2022](https://arxiv.org/abs/2203.11171)), is cheap to apply to the one decision that
   matters most: the column mapping.
6. **Multi-agent is not free.** Anthropic's research system used about 15× the tokens of a chat
   ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system)), and
   most multi-agent failures trace back to specification and inter-agent misalignment rather than to
   model capability ([MAST, arXiv 2503.13657](https://arxiv.org/abs/2503.13657)). The council is
   therefore a **fixed pipeline of specialist roles over a shared blackboard**, with typed artifacts
   between the steps, per-step budgets, and no free-form agent-to-agent chat.

---

## 1. Ruflo (formerly Claude Flow)

### 1.1 What it is

* **Identity.** "An agent meta-harness for Claude Code and Codex" that adds specialised agents, swarm
  coordination, memory and federation around Claude Code. The README says "Claude Flow is now Ruflo"
  ([README](https://github.com/ruvnet/ruflo)). npm publishes both `ruflo` and `claude-flow`; both are at
  **3.55.0**, MIT, with `latest`, `alpha` and `v3alpha` all pointing at 3.55.0 **[measured: `npm view`]**.
  The changelog describes a three-package stable train published from tag-pinned checkouts
  ([CHANGELOG](https://raw.githubusercontent.com/ruvnet/ruflo/main/CHANGELOG.md)).
* **Coordination.** The `swarm` commands are `init`, `start`, `status`, `stop`, `scale` and
  `coordinate`. The topologies are hierarchical (the default), mesh, ring, star, hybrid and adaptive.
  `hive-mind` is "queen-led consensus-based multi-agent coordination" with `init`, `spawn`, `task`,
  `work`, `consensus`, `broadcast`, `memory` and `shutdown`
  ([User guide](https://raw.githubusercontent.com/ruvnet/claude-flow/HEAD/docs/USERGUIDE.md);
  **[measured: `--help`]**). The README advertises Raft, Byzantine and Gossip consensus under a queen-led
  hierarchy.
* **Memory.** AgentDB with an HNSW index, "ReasoningBank" and "SONA" learning, and a SQLite store.
  `init` creates `.swarm/memory.db` and `.swarm/agentdb-memory.db` plus a 1.6 MB `ruvector.db` at the
  repository root **[measured]**.
* **MCP.** `npx ruflo@latest mcp start` serves over stdio, or over HTTP with
  `--transport http --port 3000`. The README cites 314 MCP tools
  ([README](https://github.com/ruvnet/ruflo)). The documented Claude Code registration is
  `claude mcp add claude-flow -- npx -y ruflo@latest mcp start`.
* **How agents run.** `hive-mind spawn --claude -o "<objective>"` launches Claude Code with a
  coordination prompt. `hive-mind work` runs the next pending task "on an idle worker via Claude Code".
  `agent spawn -p anthropic|openrouter|ollama` creates agent records **[measured: `--help`]**. The
  README and the user guide make no claim that Ruflo embeds the Claude Agent SDK. The documented
  programmatic surface is a set of npm packages (`@claude-flow/integration`, `@claude-flow/guidance`,
  `@claude-flow/plugins`) ([User guide](https://raw.githubusercontent.com/ruvnet/claude-flow/HEAD/docs/USERGUIDE.md)).

### 1.2 What `init` writes [measured]

We ran the CLI in a scratch git repository that contained only a copy of `.claude/agents/`.
`claude-flow@3.55.0 init` failed with a packaging bug: "could not locate
.claude/helpers/statusline.cjs relative to @claude-flow/cli". It had already written `.swarm/`,
`.claude-flow/`, `.mcp.json` and part of `.claude/helpers/`. So a failed init still leaves state behind.

`ruflo@3.55.0 init --no-global --no-signup --no-mods --no-plugin-install --no-skills-sh --no-codex-detect`
succeeded. It reported 10 directories and 110 files created, and one file skipped because it already
existed:

| Path | Content | Safe to commit here? |
|---|---|---|
| `CLAUDE.md` (224 lines) | Ruflo's own rules, for example "NEVER add a `Co-Authored-By` trailer…", "Keep files under 500 lines", and a 12-step "Capability Brain" loop | **No.** It conflicts with this repository's commit attribution rules and agent protocol. |
| `.claude/settings.json` | Hooks for **PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, Stop, PreCompact, SubagentStart, SubagentStop and Notification**, all of which `exec node .claude/helpers/hook-handler.cjs`; a statusline; `"model": "claude-sonnet-5"`; `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`; daemon schedules; `learning.autoTrain`; `security.autoScan`/`cveCheck` | **No.** It would run Node hooks on every tool call and override the model. |
| `.claude/helpers/*` (44 files) | `hook-handler.cjs` spawns detached `npx` processes. `statusline.cjs` runs `npx --prefer-offline @claude-flow/cli hooks statusline --json`. `auto-commit.sh` runs `git commit` **and `git push origin <branch>`**. `standard-checkpoint-hooks.sh` makes checkpoint commits. | **No.** Unreviewed code that makes network calls and auto-pushes. |
| `.claude/agents/{browser,consensus,core,sparc,swarm,testing}/*.md` (17) | Agent templates whose front-matter hooks call `mcp__claude-flow__swarm_init`, `neural_train` and others | No. We map our own agents instead. |
| `.claude/commands/**` (about 150), `.claude/skills/**` (30) | Slash commands and skills | No. Too much surface to review. |
| `.mcp.json` | `npx -y ruflo@latest mcp start`, an **unpinned** `@latest` | No. We document a pinned, opt-in registration instead. |
| `.claude-flow/config.yaml` | Runtime config: topology `hierarchical-mesh`, `maxAgents: 15`, memory backend `hybrid`, `learningBridge`, `neural.enabled`, `hooks.autoExecute: true` | **Yes**, after rewriting it to safe values (see RUFLO.md). |
| `.claude-flow/.gitignore`, root `.gitignore` additions | Ignore runtime data, logs and sessions | Yes (merged). |
| `.claude-flow/memory-package.json` | Absolute path into the npx cache | No (machine-specific). |
| `.swarm/*.db`, `ruvector.db` | Binary state | No (ignored). |

Every later command, `swarm init`, `hive-mind init` and `hive-mind spawn --dry-run` included, also
**started a background worker daemon** ("Started Ruflo background daemon … (stop: ruflo daemon stop)";
opt-out `RUFLO_DAEMON_AUTOSTART=0`, found in `dist/src/index.js`). They also adopted a signed "proven
config" into `.claude/proven-config.json` and `.claude/.proven-config-version`, with no opt-out, and
auto-refreshed existing `.claude/helpers` *and* `~/.claude/helpers` (opt-out `RUFLO_HELPERS_LOCKED=1`)
**[measured]**. `hive-mind spawn` without `hive-mind init` fails ("Hive-mind not initialized").

Even `npx claude-flow@3.55.0 init --help` performed an update check and wrote
`~/.claude-flow/update-state.json` with `lastCheck` and `checksToday` **[measured]**. The npm `.mcp.json`
sets `npm_config_update_notifier=false` for the MCP server but not for the CLI. We found no
telemetry switch in the README or user guide (`grep -i telemetry` finds nothing). The network activity we
did find comes from `npx` fetches, the update check, the optional `--cloud-mcp` servers, Cognitum
"signup" enrolment (off with `--no-signup`), `npx skills add ruvnet/ruflo` (off with `--no-skills-sh`),
federation (`wss://` with mTLS/ed25519, per the README) and the optional remote ruOS endpoint
`https://ruos.cognitum.one/mcp`.

### 1.3 Security posture

* **Permissions.** `hive-mind spawn` has `--dangerously-skip-permissions` with **default: true**, and
  `--no-auto-permissions` turns it off **[measured]**. Our harness must always pass
  `--no-auto-permissions` and `--dry-run` first. This is the most important finding for this repository,
  because its agent protocol relies on scope fences.
* **Hive-mind HTTP clients.** Sensitive operations require a bootstrap secret
  (`.claude-flow/hive-mind/bootstrap.secret`, mode 0600, or `RUFLO_HIVE_BOOTSTRAP_SECRET`). The user
  guide itself calls this "a speed bump, not a boundary" against a local agent
  ([User guide](https://raw.githubusercontent.com/ruvnet/claude-flow/HEAD/docs/USERGUIDE.md)).
* **Supply chain.** The release history includes versions deprecated on npm because "two concurrent
  sessions raced to publish" and shipped a corrupted dependency graph (v3.38.17/18, fixed in 3.38.19;
  [releases](https://github.com/ruvnet/ruflo/releases)). We saw a packaging bug ourselves in
  `claude-flow@3.55.0` **[measured]**. **Pin exact versions and never use `@latest` in committed
  config.**
* **Maturity.** Activity is high (3.3x to 3.5x releases from July to October 2026), but the README is
  promotional and its counts are internally inconsistent (98 versus "100+" agents; 35 versus 33+21
  plugins). Benchmark claims link to gists we did not reproduce **[unverified]**.

### 1.4 Integration with Claude Code as a dev harness

Ruflo is designed for exactly this use. It reads `.claude/agents/*.md`, adds slash commands and an MCP
server, and coordinates several Claude Code workers. We map the eight existing roles
(`backend-engineer`, `solver-engineer`, `ai-engineer`, `frontend-engineer`, `design-pro`,
`devops-engineer`, `strict-reviewer`, `user-tester`) onto a hierarchical swarm with the orchestrator as
the "queen". We keep our ledger, scope fences and hand-off format from `docs/AGENTS.md`. The usage is
in [RUFLO.md](RUFLO.md).

### 1.5 Can it be the backend's council runtime?

| Requirement for the server-side council | Ruflo | In-process Python orchestrator |
|---|---|---|
| Runs inside the existing FastAPI/uvicorn container | Needs Node 20+, npx downloads, and a Claude Code CLI per worker | Yes, using the existing `anthropic` dependency |
| Uses the stored, encrypted per-installation API key and model settings | Reads env vars and `.mcp.json`; secrets would have to be exported into a sub-process | Uses `app.ai.client.get_client` |
| Strict-tool schemas, refusal handling, usage/cost accounting | Not exposed through a documented API | Already in `AIClient` and tested |
| Deterministic, testable without network | Spawns processes and starts daemons | Mockable at the SDK boundary (`tests/ai/conftest.py` pattern) |
| Auditable per-step records in *our* database | Keeps its own SQLite memory | Writes `council_jobs/steps/artifacts` |
| No permission bypass in production | Default `--dangerously-skip-permissions=true` | Has no shell and no file tools; only typed tools |
| Licence | MIT (compatible) | — |

### 1.6 Decision

**The in-process Python orchestrator is the primary and only production runtime.** Ruflo is supported
as an optional **developer harness**: repository config, agent mapping and documented commands. It is
not a backend dependency. If a later release ships a documented, embeddable runtime with a safe
permission default, the council's agent interface (`Agent.run(ctx) -> Artifact`) is small enough to put
behind an adapter. We have recorded this in the ROADMAP backlog instead of building it now.

---

## 2. Any-format document understanding: the 2026 state of the art

### 2.1 Multimodal LLM parsing of PDFs and images

* **Claude PDF input.** Each page is processed as text plus an image. A text-dense page costs about
  1,500–3,000 tokens, plus the image tokens for the page. The limits are 600 pages per request (100 on
  200k-context models) and 32 MB per request. The Files API avoids re-uploading the same file
  ([PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)).
* **Claude images.** An image costs `⌈w/28⌉ × ⌈h/28⌉` visual tokens. On Claude 4.7+ models the cap is a
  2576 px long edge or 4,784 tokens; on other models it is 1568 px or 1,568 tokens. Supported formats
  are JPEG, PNG, GIF and WebP, up to 600 images and 8000×8000 px per request. The documentation's own
  example costs a 1-megapixel image at about $6.48 per thousand on a $5/MTok model
  ([Vision](https://platform.claude.com/docs/en/build-with-claude/vision)).
* **Specialised parsers versus general VLMs.** On OmniDocBench (CVPR 2025; 981 pages across 9
  document types), general-purpose VLMs "still lag behind specialized solutions" on tables. Pipelines
  such as MinerU (layout detection, then OCR, then table models) lead the benchmark, and aggregator
  leaderboards put MinerU 2.5 at the top of v1.5
  ([OmniDocBench](https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.pdf);
  [arXiv 2412.07626](https://arxiv.org/pdf/2412.07626); [leaderboard, unverified](https://www.codesota.com/tasks/document-parsing)).
  Compact multilingual VLM parsers are improving fast: PaddleOCR-VL, at 0.9B parameters, reports 80.0 on
  olmOCR-Bench ([arXiv 2510.14528](https://arxiv.org/pdf/2510.14528)).
* **Implication.** Use the text layer when it exists (pypdf `layout` mode keeps column spacing). Send
  page images to Claude only for scans and photos, or when the text layer has no recoverable table
  structure. Ask for a typed `transcribe_page` tool output (tables as rows of cells) rather than prose.

### 2.2 Spreadsheet structure understanding

* Real scheduling workbooks are **not tables**. Our own fixtures include a weekly grid with day labels
  merged over 29 columns, room headers repeated every 20 rows, 18 time-slot rows, and vertically merged
  multi-period lessons (`docs/DATA_ANALYSIS.md` shape C). The planning lists have 16,375 "used" columns
  because of formatting and multi-line headers with parenthetical instructions.
* SpreadsheetLLM's SheetCompressor uses *structural-anchor* compression, an inverted index of repeated
  values and data-format aggregation, and reaches 78.9 % F1 on table detection. Its stated limitation
  is that it ignores colour and borders ([arXiv 2407.09025](https://arxiv.org/html/2407.09025v1)).
  FRTR-Bench (2026) shows that cross-sheet and multimodal reasoning remains open
  ([arXiv 2601.08741](https://arxiv.org/html/2601.08741v1)).
* **What we do.** Forward-fill merged ranges while keeping them as metadata. Detect **axes**: runs of
  time-slot cells down a column or across a row, and day-name cells, in any of the supported languages.
  Detect **header bands** (the row above a time-axis run). Classify a sheet as *list-shaped* (header row
  plus records) or *grid-shaped* (axis × axis with entries in the cells). Handle the transposed
  orientation of each. Only anchors and samples are sent to the model.

### 2.3 Table extraction tools and their licences

| Tool | Licence | Formats | Notes for us |
|---|---|---|---|
| **Docling** (IBM → LF AI) | MIT | PDF, DOCX, PPTX, XLSX, HTML, images, EPUB | Layout model (DocLayNet) plus TableFormer; GraniteDocling VLM pipeline; runs locally; DoclingDocument carries layout and provenance ([repo](https://github.com/docling-project/docling); [tech report](https://arxiv.org/html/2408.09869v5); [DoclingDocument](https://docling-project.github.io/docling/concepts/docling_document/)). It is a heavy dependency (PyTorch models), so we use it as an optional future adapter. |
| **Unstructured** (OSS) | Apache-2.0 | Many; `partition_pdf` / `partition_image` | Strategies `auto`, `fast` (rule-based, about 100× faster), `hi_res` (layout model) and `ocr_only`; `infer_table_structure`. The hosted API claims 2× table accuracy over OSS ([repo](https://github.com/Unstructured-IO/unstructured); [strategies](https://docs.unstructured.io/open-source/concepts/partitioning-strategies)). |
| **MarkItDown** (Microsoft) | MIT | PDF, Office, images (EXIF and OCR), HTML, CSV/JSON/XML, ZIP, EPUB | Optimised for LLM-readable Markdown, not fidelity. It warns that it "performs I/O with the privileges of the current process", so use `convert_stream()` for untrusted input ([repo](https://github.com/microsoft/markitdown)). It loses merged-cell structure, so it is not enough for timetables. |
| **Azure Document Intelligence** (layout) | Commercial | PDF, images, Office | About $10 per 1,000 pages for prebuilt layout; 500 free pages per month on the F0 tier ([LiteLLM provider page](https://docs.litellm.ai/docs/providers/azure_document_intelligence); [Azure China pricing](https://www.azure.cn/en-us/pricing/details/form-recognizer/index.html)). The US list price is **[unverified]** against Microsoft's page. |
| **Google Document AI** (Layout Parser) | Commercial | PDF, images | $10 per 1,000 pages including initial chunking ([pricing](https://cloud.google.com/document-ai/pricing)). |
| **LlamaParse** | Commercial (SaaS) | PDF, Office, sheets, audio | Credits at $1.25 per 1,000. Fast is 1 credit per page, Cost-effective 3, Agentic 10, Agentic Plus 45; spreadsheets cost 1 credit per sheet; 48-hour cache, opt out with `do_not_cache` ([pricing](https://developers.llamaindex.ai/llamaparse/general/pricing/); [FAQ](https://developers.llamaindex.ai/python/cloud/llamaparse/faq/)). |
| **openpyxl / python-docx / pypdf** (already dependencies) | MIT / MIT / BSD-3 | xlsx, docx, text-layer PDF | Exact cells, merged ranges, comments, fills; no models; already used by the importers. |

**Choice.** The baseline is the libraries we already ship, with no new heavy dependency. Claude
vision covers scans and photos. Docling and the commercial parsers are documented as optional adapters
behind the Intake agent's `render()` interface.

### 2.4 Schema inference and entity resolution

* **Schema matching.** Magneto's retrieve-then-rerank design (an SLM or embedding candidate generator,
  then LLM reranking) is the 2025 reference point, and it beats Unicorn, COMA++ and ISResMat on its
  benchmarks ([arXiv 2412.08194](https://arxiv.org/abs/2412.08194);
  [code](https://github.com/VIDA-NYU/magneto-matcher)). We mirror it without training. A lexicon of header
  synonyms in TR, EN, DE, FR, ES, IT and PT scores the candidates, together with *value profiles*: share
  of times, dates, day names, room-like codes, course-like codes, integers, person names and long text.
  The model then confirms or overrides the mapping per column with a confidence.
* **Entity resolution** across files (`A 101`, `A101`, `Room A-101`; `Dr. Öğr. Üyesi Ayşe Yılmaz` and
  `AYSE YILMAZ`) uses deterministic canonical keys: casefold with Turkish İ/ı handling, strip
  diacritics, remove academic titles, and collapse whitespace and punctuation. A string-similarity pass
  then puts *near* matches into review instead of merging them silently. The existing
  `app.importers.normalize` helpers already do this for this university's formats, and the council adds
  locale-independent versions.

### 2.5 Multilingual handling

* **Language identification.** fastText `lid.176` covers 176 languages (126 MB, or 917 kB compressed;
  CC-BY-SA) ([fastText](https://fasttext.cc/docs/en/language-identification)). Lingua is the most
  accurate on very short strings but much slower ([lingua-py](https://github.com/pemistahl/lingua-py)).
  Headers and cells are short, and we only need to pick a lexicon, so we use a dependency-free script
  and stop-word heuristic for TR, EN, DE, FR, ES, IT and PT. We fall back to the model's own `language`
  field when the heuristic is unsure.
* **Normalisation.** Day names, month names and boolean words in each supported language; Turkish
  casefolding; and decimal commas (`4,5`).
* **Prompting.** Uploaded content is wrapped in `<document>` and treated as data. Outputs use canonical
  English field names; titles and messages to the planner are in the UI language.

### 2.6 Provenance

* W3C PROV-O is the standard vocabulary: entity, activity and agent; `wasDerivedFrom`,
  `wasGeneratedBy`, `wasAttributedTo` ([PROV-O](https://www.w3.org/TR/prov-o/)). We store the
  lightweight equivalent. Every record carries a `source_ref` of
  `{file, sheet, row, col, cell}` or `{file, page, line|bbox}`. Every artifact records the step
  (activity) and agent that produced it, and the model id and usage when an LLM was involved.
* Docling and Claude citations (`page_location`, `char_location`) are alternative sources of the same
  information ([PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)). Claude
  citations cannot be combined with structured outputs, so we ask for unit numbers inside the strict
  tool output and map them back to the units we numbered ourselves. This is the pattern `app/ai/ingest.py`
  already uses.

### 2.7 LLM-as-judge and self-consistency

* **Judge.** Strong judges reach over 80 % agreement with humans, but they show position, verbosity and
  self-enhancement bias ([Zheng et al. 2023](https://arxiv.org/abs/2306.05685)). Mitigations: show the
  source row and the extracted record side by side, ask for per-field verdicts, never let the judge
  rewrite values, and sample a bounded number of records per file.
* **Self-consistency.** Sample k answers and majority-vote ([Wang et al. 2022](https://arxiv.org/abs/2203.11171)).
  Multi-agent *debate* also improves factuality ([Du et al. 2023](https://arxiv.org/abs/2305.14325)),
  but it costs several model calls per question. We apply voting only to the column mapping
  (`COUNCIL_SELF_CONSISTENCY=k`, default 1). The heuristic mapper and the model act as two independent
  "voters": agreement raises confidence and disagreement sends the column to review.
* **Strict outputs.** `strict: true` tools use grammar-constrained sampling, so the inputs always match
  the schema ([structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)).
  The documented complexity budget is at most 20 strict tools, 24 optional parameters and 16 union
  parameters per request, and `app/ai/catalog.py` already enforces it. On Claude Opus 5.5 and Sonnet
  5.5, forced `tool_choice` returns a 400, so we use `auto` plus an instruction to call the tool, and we
  re-validate the input on the client side.

### 2.8 Cost and latency (per typical file)

Prices are from the claude-api skill's model table (cached 2026-10-06): Opus 5.5 $4/$20, Sonnet 5.5
$2/$10 and Haiku 5.5 $0.10/$0.50 per MTok in/out; cache reads cost 10 % of input.

| Step | Deterministic path | LLM path (Opus 5.5 unless noted) |
|---|---|---|
| Intake (xlsx/csv/docx/text PDF) | 0.05–3 s locally (openpyxl on our 1,539-row workbook) | — |
| Intake (scan or photo page) | not possible ("needs AI" message) | about 1.5–4.8k visual tokens per page plus output: roughly $0.01–0.03 per page on Opus 5.5, or about 40× less on Haiku 5.5 |
| Structure analyst (per sheet) | under 50 ms | anchors and samples of about 3–6k tokens in, 1–2k out: about $0.03–0.06 and 5–20 s; × k for self-consistency |
| Extractor (list or grid) | linear, under 2 s for 1.5k rows | free-text only: 12k-char chunks at about $0.05 each |
| Rule miner | none (shows "needs AI" text) | notes and memo units, chunked like `ingest.py`: about $0.05–0.40 per file |
| Critic | `static_check` in under 1 s on about 700 events | judge sample of 12 records: about $0.03 |
| Commercial parsers (alternative) | — | Azure or Google layout $0.01 per page; LlamaParse $0.00125–0.056 per page |

A typical onboarding of 6 workbooks with notes columns therefore costs a few dollars on Opus 5.5 and
well under one dollar on Haiku 5.5 for the cheap roles. The orchestrator enforces a per-job token
budget (`COUNCIL_JOB_TOKEN_BUDGET`). When the budget runs out, the remaining steps fall back to the
deterministic path and say so.

---

## 3. Agent-council patterns

* **Workflow before agent.** Anthropic distinguishes *workflows* (LLMs and tools orchestrated through
  predefined code paths) from *agents* (the LLM directs its own process). For predictable
  decompositions it recommends prompt chaining, routing, orchestrator-workers and evaluator-optimizer
  ([Building effective agents](https://www.anthropic.com/engineering/building-effective-agents);
  [summary](https://simonwillison.net/2024/Dec/20/building-effective-agents)). Ingestion is predictable
  (intake, structure, extraction, rules, critique, reconciliation, planning), so the council is a
  **routed orchestrator-workers workflow with an evaluator** (the critic).
* **Planner, specialists, critic, consensus.** In our design:
  * *Planner* = the orchestrator's routing. It chooses the fast path or the general path per file and
    which specialists run. The *Planner agent* proposes the term setup.
  * *Specialists* = Intake, Structure analyst, Extractor, Rule miner, Reconciler.
  * *Critic/verifier* = deterministic checks, the solver's `static_check`, and a sampled LLM judge.
  * *Consensus* = heuristic versus model votes on each column mapping (plus optional k-sample voting);
    a disagreement becomes a review item. The human reviewer is the final consensus member.
* **Blackboard.** Steps communicate only through typed artifacts in `council_artifacts`. This avoids
  the "inter-agent misalignment" failure class in MAST
  ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657)), and it makes every step re-runnable and
  auditable.
* **Structured outputs and tools.** Each LLM role has exactly one strict tool
  (`transcribe_page`, `analyze_structure`, `extract_records`, `propose_constraints` reused from the
  catalogue, `judge_records`). Every response is re-validated client side, and truncated (`max_tokens`)
  or refused turns are discarded with a step message.
* **How to evaluate.**
  1. **Golden files.** The six real workbooks and their `parse_*` results serve as ground truth for the
     general path: compare record counts, course-code and room-code sets, and time fields.
  2. **Variant files.** The same real records rendered in other shapes and languages (CSV in English, a
     PDF, a transposed grid, a DOCX memo) must produce the same entities. These are the "metamorphic"
     tests in `tests/council`.
  3. **Per-step metrics** from `council_steps`: duration, tokens, cost, review-item rate.
  4. **A live smoke test** gated on `ANTHROPIC_API_KEY`. It checks that the strict schemas compile and
     that a real model maps a real sheet sensibly.
  5. **Human review acceptance rate** as the production metric. Items accepted unchanged mean the
     threshold can be raised; frequent edits mean the lexicon or the prompts need work.

## Sources

* Ruflo: https://github.com/ruvnet/ruflo · https://github.com/ruvnet/ruflo/releases ·
  https://raw.githubusercontent.com/ruvnet/ruflo/main/CHANGELOG.md ·
  https://raw.githubusercontent.com/ruvnet/claude-flow/HEAD/docs/USERGUIDE.md · npm `ruflo` / `claude-flow` 3.55.0
* Claude: https://platform.claude.com/docs/en/build-with-claude/pdf-support ·
  https://platform.claude.com/docs/en/build-with-claude/vision ·
  https://platform.claude.com/docs/en/build-with-claude/structured-outputs ·
  https://code.claude.com/docs/en/agent-sdk/subagents ·
  https://www.anthropic.com/engineering/building-effective-agents ·
  https://www.anthropic.com/engineering/multi-agent-research-system
* Parsing: https://github.com/docling-project/docling · https://arxiv.org/html/2408.09869v5 ·
  https://docling-project.github.io/docling/concepts/docling_document/ ·
  https://github.com/Unstructured-IO/unstructured ·
  https://docs.unstructured.io/open-source/concepts/partitioning-strategies ·
  https://github.com/microsoft/markitdown · https://cloud.google.com/document-ai/pricing ·
  https://docs.litellm.ai/docs/providers/azure_document_intelligence ·
  https://www.azure.cn/en-us/pricing/details/form-recognizer/index.html ·
  https://developers.llamaindex.ai/llamaparse/general/pricing/ ·
  https://developers.llamaindex.ai/python/cloud/llamaparse/faq/
* Benchmarks: https://arxiv.org/pdf/2412.07626 ·
  https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.pdf ·
  https://arxiv.org/pdf/2510.14528 · https://www.codesota.com/tasks/document-parsing ·
  https://arxiv.org/html/2407.09025v1 · https://arxiv.org/html/2601.08741v1
* Matching, judging, agents: https://arxiv.org/abs/2412.08194 · https://github.com/VIDA-NYU/magneto-matcher ·
  https://arxiv.org/abs/2306.05685 · https://arxiv.org/abs/2203.11171 · https://arxiv.org/abs/2305.14325 ·
  https://arxiv.org/abs/2503.13657
* Language ID and provenance: https://fasttext.cc/docs/en/language-identification ·
  https://github.com/pemistahl/lingua-py · https://www.w3.org/TR/prov-o/
