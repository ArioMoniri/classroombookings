# Generate + chat — horizon picker, preference prompt, solver progress, side chat with diff/apply/undo, constraint list

Owner: design-pro (B). Routes `/generate` (new run) and `/runs/[id]` (run page hosting the chat side panel;
`/runs/[id]/grid` and `/runs/[id]/report` belong to the other design agent — this doc only defines the
**chat panel** that overlays/attaches to those pages and the **constraints drawer**).
Backend: `POST /runs {term_id, kind, horizon, horizon_params, params, prompt?} → 202 {run_id}`,
`GET /runs/{id}` (status, scores, stats, diagnosis), `POST /runs/{id}/chat {message}` → tool calls
(`move_event, swap_rooms, lock_assignment, add_constraint, remove_constraint, explain_assignment, re_solve`),
child run via `parent_run_id`; `GET/POST /constraints` (hardness, weight, enabled, nl_text, source).
AI layer: pre-generation `propose_constraints` tool → typed Constraint list the admin reviews.
Licences: `navigation-shell.md §9`.

---

## 1. References

| # | Reference | Borrow |
|---|---|---|
| 1 | [Claude – composer with model picker & suggestion chips](https://mobbin.com/screens/99067951-15dc-4fba-8ca8-94686a70985c) | Rounded composer card, `+` attach, model selector bottom-right, **suggested chips row under the composer** (Write · Learn · Code …) → our preference chips |
| 2 | [Claude – model dropdown w/ extended thinking toggle](https://mobbin.com/screens/a584de73-9ae1-4c5c-851d-73c1131e0a21) | Model list with 1-line descriptions + a toggle row inside the menu → "Stability (keep previous)" toggle inside the solver options menu |
| 3 | [ChatGPT – tool chip inside composer](https://mobbin.com/screens/35e287bd-158a-4413-8cc9-07b9dabe798b) | Selected mode chip rendered inside the composer ("Shopping research") → our horizon chip inside the prompt box |
| 4 | [Microsoft Copilot – working card with Cancel](https://mobbin.com/screens/c2cad8e4-77eb-4cd8-ae5e-26748339323c) | "I'm working on this… Reading X ›" progress card with step line and Cancel → solver status card |
| 5 | [Krea – "1 minute remaining / Applying effects"](https://mobbin.com/screens/a758fbe6-2cae-4f81-98e3-ddcb0b0cfd13) | Big remaining-time headline + current phase subtitle + Cancel link |
| 6 | [HubSpot – generating step in a stepper](https://mobbin.com/screens/534cedd1-7910-43a2-91d7-6dee1d64ce56) | Blocking generation screen with disabled footer CTA |
| 7 | [Notion AI – side panel with "Suggested revision" + Ask mode/model footer](https://mobbin.com/screens/7e25606f-869e-4867-8400-cfac83d7e1b1) | Right side panel (~360 px) next to content; structured answer sections; composer footer with mode + model |
| 8 | [Grammarly – review suggestions with Accept/Dismiss](https://mobbin.com/screens/82d0d01f-8aa2-4fe4-a658-1498c92fb1ae) | Suggestion card: old struck → new bold, **Accept / Dismiss**, category tabs |
| 9 | [Mintlify – agent panel with file-change summary (+92 −14)](https://mobbin.com/screens/02c0a504-56be-40be-9b69-e2e58068a00f) | "1 file change" collapsible with +/- counts → our "3 moves · 1 constraint" diff summary |
| 10 | [Confluence AI – inline proposal card with Discard / Refine / Insert / Replace](https://mobbin.com/screens/dd2bcb8c-3a64-4168-a614-b821d293df08) | Proposal card action row incl. "Refine ▾" and "Tell AI what to do next" input |
| 11 | [Grok – generating overlay with % and Cancel](https://mobbin.com/screens/e71178ee-b02f-40b4-8f4d-533a1991efcc) | Blurred preview behind a progress pill |
| 12 | [Linear – undo toast](https://mobbin.com/screens/14cbb61d-2120-46fa-b29c-b7678e4b85cc) | Apply → "Applied · Undo" toast |

## 2. Information architecture

### `/generate` (single page, three stacked sections, max-width 880 px centred)
```
1. Horizon        [Hafta | Ay | Dönem | Sınav]  + parameters for the chosen horizon
2. Preferences    prompt box (TR/EN) + suggested chips + "Önerilen kısıtlar" review list (from LLM)
3. Constraints    accordion: hard (n) / soft (n) with toggles & weight sliders; solver options menu
[Generate]  sticky bottom bar with estimate "~1 300 meetings · 60 rooms · 14 weeks · est. 2–5 min"
```
After Generate → navigates to `/runs/[id]` which shows the **status card** until FEASIBLE/OPTIMAL/INFEASIBLE, then the grid/report (other agent) with the **chat side panel** open.

### `/runs/[id]` chat side panel
```
header   "Run #42 · Bahar W3–W6 · OPTIMAL 100/92"  [constraints ⚙] [history ▾] [close]
thread   messages (user / assistant), tool cards (ProposedDiff, Explanation, ReSolve status)
composer textarea + chips row ("Move…", "Swap…", "Why is…", "Lock…") + send; model label
```

## 3. Interaction spec

### 3.1 Horizon picker
- Segmented control (beUI Tabs "segment" variant, spring indicator): **Hafta / Ay / Dönem / Sınav**.
- Parameters by horizon:
  - *Hafta*: week chips `W1 … W16` from `weeks` (kind badge LECTURE/EXAM/HOLIDAY; holiday disabled), multi-select contiguous; shows dates under each.
  - *Ay*: month `Select` from term range → resolves to week set, shown as chips.
  - *Dönem*: whole term; info line "16 weeks, 14 lecture".
  - *Sınav*: date-range picker (beUI Date Range Picker) within FINAL/BUT weeks; `kind=EXAM`.
- Right side of the section: live estimate card (`GET /sections?term=&count`) "1 302 roomed meetings · 48 rooms + 4 labs · prior run #41 reused as `previous_assignments`" with a **Stability** toggle (default ON when a prior run exists) — explains "minimise changes vs run #41".
- Validation: at least one week; exam horizon requires exam requests imported (else inline CTA to `/import`).

### 3.2 Preference prompt (TR/EN)
- Composer card (Claude #1): autosize textarea (min 3 rows, max 12), placeholder rotates between TR/EN examples depending on locale: *"TIP derslikleri sadece Tıp için; eczacılık pazartesi C blokta kalsın; hemşirelik 1. sınıf 17:30'dan sonra ders olmasın"*. `⌘Enter` submits for analysis, `Enter` newline.
- Suggested chips under the composer (scrollable row, max 8): generated from data + locale, e.g. `TIP rooms only medicine` `Keep programme in one building per day` `No lectures after 17:30 for year 1` `Avoid 20 students in 156-seat halls` `Keep A 204 free Wed P7–P9` `Evening (İÖ) in B/C blocks`. Click inserts the phrase (TR or EN) at cursor with a trailing "; ". Chips are `button`s, not links.
- Inside-composer chip (ChatGPT #3): the horizon summary ("Bahar · W3–W6") sits as a removable chip at the start so the user sees what the prompt applies to.
- **Analyse** button (secondary) → `propose_constraints` tool call (≤ 10 s; button shows spinner + "Çözümleniyor…"; streaming not required). Result renders a **Proposed constraints** list (Grammarly #8 style cards):
  - each card: kind icon, generated title (e.g. "TIP rooms reserved for Faculty of Medicine"), params rendered as chips (`rooms: A 201, A 202, A 203` · `faculty: Tıp`), **Hard/Soft** segmented, weight slider (soft only), source quote (the sentence it came from, highlighted in the prompt on hover), actions **Accept · Edit · Dismiss**.
  - "Accept all (n)" at top. Accepted ones get `source=AI`, appear in §3.4 list. Nothing is sent to the solver until accepted (AI layer rule).
  - Unparseable parts → amber card "Couldn't turn this into a rule: 'danışmanla görüşülecek' — keep as note?".
- Prompt text is stored on the run (`prompt_text`) for the report.

### 3.3 Solver status (streaming progress) on `/runs/[id]`
- Status card (Copilot #4 + Krea #5), centred, max 640 px, grid behind it rendered blurred/dimmed when assignments start arriving (Grok #11) — optional, only if the backend streams partial solutions.
- Content: headline per status: `QUEUED` "Sırada · 1 önde" → `RUNNING` "Çözülüyor · %63 · ~1 dk kaldı" (percentage from `stats.progress` if present, else indeterminate bar) → phase line from `stats.phase` (`building model · 1 302 vars`, `search · 12 solutions`, `polishing (LNS)`); live counters: hard violations (must reach 0), soft score; elapsed time; **Cancel** (→ `DELETE /runs/{id}` or status CANCELLED) with confirm.
- Transport: SSE `GET /runs/{id}/events` (fallback 2 s polling). Phase list rendered as beautifului **Task Rows** (running/completed/failed) or **Thinking** expandable trace for solver log lines (collapsed by default, "Show solver log").
- Terminal states:
  - `OPTIMAL/FEASIBLE`: card morphs (300 ms, beUI Morphing Modal idea) into a result strip "100 / 92 · 1 302 placed · 0 conflicts · View grid · Open report"; chat panel auto-opens with assistant message summarising (from `explain` tool), suggestions chips ("Why is BME 419 in A 204?", "Move PHAR 240 …").
  - `INFEASIBLE`: red card "Çözüm yok — 3 çakışma" listing diagnosis items with fixes as buttons ("Release A 204 for TIP Wed P7–P9" → creates constraint change and offers **Re-solve**); link to report (other agent) for full detail.
  - `FAILED`: error id, "Retry", log download.
- Reduced motion: no blur, no morph; status text updates only. Progress bar never animates indefinitely with motion; indeterminate bar uses opacity pulse 1.2 s (disabled under reduced motion → static striped).

### 3.4 Constraint list (drawer, shared by `/generate` §3 and the chat header ⚙)
- Right `Sheet` 480 px (inline accordion on `/generate`). Two groups: **Hard (n)** / **Soft (n)**, each a list of rows:
  `[enabled switch] [kind icon] title · params chips · source badge (FILE / ADMIN / AI) · nl_text (muted, 1 line, expand) · [Hard|Soft] segmented · weight slider (soft) · ⋯ (edit/duplicate/delete)`
- Hard/Soft toggle: switching Soft→Hard shows a tooltip-warning "Hard rules are never relaxed; infeasible runs will name this rule". Switching a FILE-sourced hard rule to soft requires confirm.
- Weight slider: 1–10 integer, beUI Range Slider (tick dots), value bubble; keyboard arrows ±1, `Shift` ±5. Debounced `PUT /constraints/{id}` 400 ms; row shows a "saved" check (Spinner-to-check morph, transitions.dev free).
- Add rule: "+ Rule" opens a `Dialog` with kind `Select` (catalogue from backend `GET /constraints/kinds`) and a dynamic param form; or "Describe in words" tab reusing the prompt analyser.
- Bulk: "Disable all AI rules", "Reset weights to defaults".
- Changes after a run exist show a banner "Constraints changed since run #42 · Re-solve" (stability on by default).

### 3.5 Chat side panel (post-generation edits)
- Panel: 400 px right (Notion #7), resizable via drag handle (320–560 px, persisted), collapsible to a 40 px rail with a sparkle icon + unread dot; `⌘J` toggles. Below 1024 px becomes a bottom Sheet (snap 50/100 %).
- Thread: messages left-aligned (assistant) / right card (user). Assistant messages are streamed (SSE on `POST /runs/{id}/chat`), rendered as Markdown-lite (bold, lists, code for course codes). beautifului **Streaming Text** / transitions.dev **Streaming text** (Pro — reference only; implement a simple append + 80 ms word opacity fade, disabled under reduced motion).
- **Tool cards** (one per tool call, Mintlify #9 + Grammarly #8):
  - `ProposedDiff`: header "Proposed change · 3 moves · 1 lock" with +/−-style counters; body rows: `PHAR 240 · Mon P4–P6 · A 203 → A 206 · from W3 (23 Feb)` with old struck in `muted`, new in `primary`; conflicts the solver found while validating listed in red ("A 206 busy W5 Mon P5: NRS 304"); footer **Apply · Refine ▾ (Tell the assistant…) · Dismiss** (Confluence #10). Apply → `POST /runs/{id}/chat` confirm step or direct move endpoints → creates child run (`parent_run_id`), grid re-renders changed cells (highlight pulse 600 ms, other agent's grid handles the highlight class `data-changed`), toast "Applied · Undo" 8 s (Linear #12). **Undo** → `POST /runs/{child}/revert` (or re-activate parent run id) — backend open question §7.
  - `Explanation` (`explain_assignment`): card with the structured reasons rendered as a checklist (capacity 102 ≤ 156 ✓, TIP reserved ✗ released by rule #12 …) and a "Show constraints involved" link that opens the drawer with those rows highlighted.
  - `ReSolve`: inline mini status (phase + %), cancel; on completion shows score delta "92 → 94 soft, 0 hard" and "View changes (18)".
  - `Error`: model/tool failure → red card with retry; never show raw stack traces.
- Composer: textarea + chips row (contextual: if a cell is selected in the grid, chips become "Move {code} to…", "Swap with…", "Why here?", "Lock"); `@` mention autocomplete for course codes / rooms (cmdk popover); `⌘Enter` send, `Esc` blur; model label bottom-right (read-only, from settings; link to settings for ADMIN).
- Grid ↔ chat linkage: hovering a diff row highlights the target cells in the grid (emit `ui.hoverAssignment(id)` via Zustand); clicking scrolls the grid to it.
- History ▾: list of child runs (`#42 → #43 (chat) → #44 (manual)`) with "Make active" and "Compare" (compare = backlog).
- States: `idle (empty thread → 3 starter chips + "Ask about this run")` · `streaming (stop button replaces send)` · `tool pending (card skeleton with phase)` · `applied` · `undone (card dims, label "Undone")` · `error`.
- Rate/cost: show a small "~1 200 tokens" hint per message only in dev; never in prod UI.

### 3.6 Keyboard
`⌘J` chat panel · `⌘Enter` send/submit · `Esc` stop streaming / close · `a` apply focused diff card · `d` dismiss · `u` undo last apply (within 8 s window) · `⌘⇧C` constraints drawer · in slider `←/→` ±1.

### 3.7 Touch
Chips row horizontally scrollable with fade edges; diff rows 48 px; Apply/Dismiss as full-width buttons in the card footer; bottom-sheet composer stays above the keyboard (`100dvh`, `env(safe-area-inset-bottom)`).

### 3.8 Motion budget
Segmented indicator spring {500,40}; chips enter stagger 30 ms × n ≤ 8 (≤ 240 ms total); diff card enter height+fade 180 ms; status card morph 300 ms max; streaming word fade 80 ms. All gated by `useReducedMotion`.

## 4. Component list

| Component | Source | Licence | Note |
|---|---|---|---|
| Tabs (segment variant, spring indicator) | beUI https://beui.dev/components/motion/tabs | MIT | `bunx --bun shadcn add @beui/tabs` → horizon picker |
| Date Range Picker | beUI https://beui.dev/components/motion/date-range-picker | MIT | exam horizon |
| Range Slider (tick dots, bouncy thumb) | beUI https://beui.dev/components/motion/range-slider | MIT | constraint weights; fall back to shadcn `slider` (Radix) if a11y needs win |
| Morphing Modal | beUI https://beui.dev/components/motion/morphing-modal | MIT | status card → result strip |
| Switch (spring thumb) | beUI https://beui.dev/components/motion/switch | MIT | constraint enabled |
| Thinking (expandable trace), Task Rows (live status), Streaming Text, Approval Card, Tool Chips, Prompt Bar, Diff Table, Recommendation Card | beautifului.dev https://beautifului.dev (#thinking-state, #task-rows, #streaming-text, #approval-card, #tool-chips, #prompt-bar, #diff-table, #recommendation-card) | MIT | copy-paste; Approval Card = our ProposedDiff footer; Prompt Bar = composer with `/` commands & model picker |
| Textarea autosize, Sheet, Dialog, Accordion, Slider, Switch, Toggle Group, Tooltip, Badge, Progress, Card | shadcn/ui | MIT | |
| Mention autocomplete | cmdk inside Popover | MIT | |
| Conversation, Message, Chat Input, Reasoning Steps, Plan Card, File Diff, Streaming Text | kobra.systems (Agents section; only Conversation/Command Menu/Toast are in the Free set, and free = personal use) | paid / personal-only | reference only (Plan Card ≈ ProposedDiff) |
| Thinking states / Reasoning stream / Streaming text | transitions.dev (Pro) | Pro subscription | reference only; free "Skeleton loader and reveal", "Spinner to check morph", "Success check" are usable |
| Progress Ring / Segment Loader / Hold to Confirm | kinetics | no licence | reimplement; Hold-to-confirm (600 ms ring) is a nice fit for **Apply** on destructive diffs |
| Markdown rendering | `react-markdown` + `remark-gfm` | MIT | sanitise; no raw HTML |
| SSE client | native `EventSource` / `fetch` streams | — | reconnect with backoff |

## 5. Responsive behaviour

| Width | /generate | Run status | Chat panel | Constraints |
|---|---|---|---|---|
| 360 | sections stack; horizon segmented control scrolls horizontally; week chips wrap; sticky Generate bar full-width | full-screen card | bottom Sheet (50/100 %), composer pinned above keyboard | full-screen Sheet; slider value bubble always visible |
| 768 | 1 column 720 px; estimate card below picker | centred card | bottom Sheet | right Sheet 400 px |
| 1280 | 880 px column; estimate card to the right of picker | centred card over dimmed grid | right panel 400 px (resizable) | right Sheet 480 px |
| 1920 | 960 px column; constraints accordion opens inline two-column (hard/soft side by side) | same | right panel up to 560 px | inline two-column |

## 6. Accessibility
- Segmented controls are `role="radiogroup"`; week chips `aria-pressed` toggle buttons with date in `aria-label`.
- Prompt textarea has `aria-describedby` for the hint and the horizon chip; suggestion chips are buttons labelled "Insert suggestion: …".
- Status card uses `role="status"` `aria-live="polite"`; percentage changes throttled to announce every 10 %; terminal state announced assertively.
- Streaming text: the message container is `aria-live="polite"` with `aria-busy="true"` while streaming; the final text is announced once (do not announce every token).
- Diff cards: `<table>` semantics with `<th scope>`; old/new not colour-only (struck + "was"/"now" visually-hidden text); Apply/Dismiss buttons have the change count in `aria-label`.
- Sliders: Radix `Slider` semantics (`aria-valuemin/max/now`, `aria-valuetext="weight 7 of 10"`).
- Focus management: opening the chat panel moves focus to the composer only when user-initiated; auto-open after a run keeps focus on the result strip and announces "Assistant panel opened".
- Hold-to-confirm must have a plain-click alternative (confirm dialog) for motor-impaired users.

## 7. Open questions
1. **Undo semantics**: ARCHITECTURE has `parent_run_id` but no revert endpoint. Proposal: `POST /runs/{id}/activate` to switch the "current" run back to the parent (no data loss). Needs backend-engineer.
2. Does the solver stream partial solutions (`stats.progress`, phases)? If not, status card is indeterminate + phase names only.
3. Where does the chat live when the user is on the report page vs the grid — same panel instance (Zustand store keyed by run id) is assumed.
4. Model picker in the composer (per-message) or settings-only? Spec: settings-only (cost control), label read-only in chat.
5. Token/cost visibility for ADMIN in production?
6. Cross-agent contract: grid must expose `data-assignment-id` on cells and accept `highlightAssignmentIds[]` + `changedAssignmentIds[]` from the store so the chat's hover/apply can highlight.
