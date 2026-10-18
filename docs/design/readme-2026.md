# README and repository presentation, October 2026

Lane README-X (ledger `readme-x-2026-10-18`). Owner ask: "check new repo structures or README components that
make them shine and be industry level as of Oct 2026, and do the redesigns." This file records the research, the
patterns chosen for `README.md`, the community-health files added under `.github/`, and what the owner still has
to do on github.com.

## 1. Reference repositories and what we took

Each README was read on 2026-10-18 (raw `README.md` on the default branch).

| Repository | What it does well | Taken for SmartSched |
|---|---|---|
| [twentyhq/twenty](https://github.com/twentyhq/twenty) | `<picture>` logo and banner that follow the reader's colour scheme; a link bar instead of a badge wall; "Why Twenty" before installation; a two-column screenshot grid | Theme-aware header (kept), the centred link bar, a "Why SmartSched" section before the features |
| [makeplane/plane](https://github.com/makeplane/plane) | Same licence (AGPL-3.0) and the same audience (self-hosting organisations); feature list as bold name + one sentence; a dedicated Security section with private reporting; contributing as "ways to help" | Bold-name + one-sentence feature tiles, a Security section that sends reports to a private channel, "Ways to help" in CONTRIBUTING |
| [calcom/cal.com](https://github.com/calcom/cal.com) | Closest domain (scheduling); callouts above the fold about self-hosting risk; deploy options grouped; acknowledgements | One `[!NOTE]` alert near the top that states the maturity honestly; deploy options in one collapsible |
| [immich-app/immich](https://github.com/immich-app/immich) | A short warning about backups and a note pointing to the docs; a feature table by platform (mobile / web); translated READMEs | Alerts kept to two (GitHub's guidance: one or two per page); an in-page Türkçe section instead of a full translation |
| [supabase/supabase](https://github.com/supabase/supabase) | A feature checklist where every item links to its docs; an architecture section that names each component; community and support channels by purpose | Feature tiles that point at evidence; a Mermaid architecture with one box per container; SUPPORT.md as a "you want to → go to" table |
| [excalidraw/excalidraw](https://github.com/excalidraw/excalidraw) | Hero image in `<picture>` with a dark variant; demo screenshot directly under the tagline; short quick start | Hero media straight under the tagline and badges, a quick start before any detail |
| [astral-sh/uv](https://github.com/astral-sh/uv) | Three meaningful badges only; a one-line value proposition; highlights as short bullets; licence and a small footer | Badges cut from six to five (licence plus the four stack facts a self-hoster asks about); a one-sentence value proposition |
| [n8n-io/n8n](https://github.com/n8n-io/n8n) | Quick start in three commands; a short licence section that explains the model | Quick start in two commands from a clone; the licence section names the AGPL fork and the citation file |

Guidance used besides the examples:

- GitHub Docs, [basic writing and formatting](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax):
  the five alert types (`[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`), "one or two per
  article", never back to back, never nested.
- GitHub Docs, [default community health files](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file):
  CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, issue and PR templates may live in `.github/`, the root or
  `docs/` (GitHub looks in that order); issue templates and `config.yml` must be in `.github/ISSUE_TEMPLATE`.
- GitHub Docs, [issue forms syntax](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms):
  `name`, `description`, `body` are required; element types `markdown`, `input`, `textarea`, `dropdown`,
  `checkboxes`; `validations.required`.
- GitHub Docs, [social media preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview):
  PNG, JPG or GIF under 1 MB, 1280 × 640 for the best display, uploaded in Settings (not read from the tree).
- `CITATION.cff` (Citation File Format 1.2.0) at the repository root turns on GitHub's "Cite this repository".

## 2. The README, top to bottom

| # | Block | Pattern | Notes |
|---|---|---|---|
| 1 | Header | `<picture>` with `prefers-color-scheme` (existing SVG lockups) | unchanged |
| 2 | Tagline | one English line + one Turkish line | the Turkish line marks a Turkish product without a second README |
| 3 | Link bar | Quick start · How it works · Docs · Roadmap · Türkçe · Contributing | in-page anchors are checked by `check_readme.py` |
| 4 | Badges | licence, Python 3.12, Next.js 16, OR-Tools CP-SAT, PostgreSQL 16 | static shields only: no build badge, because CI runs on the pod and a GitHub badge would show the manual workflow |
| 5 | Hero | desktop hero WebP with the reduced-motion poster, links to the MP4 / AV1 / vertical / phone loop | byte-identical to docs/launch/README.md §4 |
| 6 | Inline video | a bare `https://github.com/user-attachments/assets/…` line under the hero | GitHub renders it as a `<video>` player; the owner replaces the URL after re-uploading the re-rendered video |
| 7 | Value proposition | the existing two-sentence paragraph | |
| 8 | `[!NOTE]` | maturity statement with links to STATUS and ROADMAP | honesty first; alert 1 of 2 |
| 9 | See it work | `AUTO:recordings` (3 featured clips + "More clips") | generated, unchanged |
| 10 | Why SmartSched | four bold claims beside the phone loop | each claim is a Done item |
| 11 | Parity | `AUTO:parity` | generated, unchanged |
| 12 | Features | 3 × 3 tile grid | from the Done items of `docs/features.yml`; backend-only and in-progress items are not tiles |
| 13 | Comparison | spreadsheets + classroombookings vs SmartSched | rows are the "what stays / what is added" list of docs/CLASSROOMBOOKINGS.md |
| 14 | Quick start | two commands + `[!TIP]` to docs/deploy/ONE-CLICK.md + collapsible options, AWS, local dev | alert 2 of 2 |
| 15 | Architecture | Mermaid `flowchart LR`, one node per compose service | from docs/ARCHITECTURE.md "Deployment" and docs/SECURITY.md §2 |
| 16 | Screenshots | 31 light/dark `<picture>` screens by role, in `<details>` | one table row per source line to keep the file short |
| 17 | What is built | the part-done list and `AUTO:status only=done`, each in `<details>` | generated block unchanged; collapsed so the page stays scannable |
| 18 | Privacy, KVKK and security | four bullets + links to docs/SECURITY.md and .github/SECURITY.md | every claim maps to a control in docs/SECURITY.md or `app/services/kvkk.py` |
| 19 | Documentation | index table | adds One-click deploy, Security model, Launch notes |
| 20 | Roadmap, Contributing | links to ROADMAP, STATUS, CONTRIBUTING, CODE_OF_CONDUCT, SUPPORT, AGENTS | |
| 21 | Türkçe | short paragraph and three bullets | |
| 22 | Licence | AGPL fork statement (unchanged) + CITATION.cff | then `AUTO:last-updated` |

Rules kept: no absolute repository URL, owner handle or branch name in the README or the images (the repository
will be renamed); relative links everywhere, so `check_readme.py` checks them. The only absolute URLs are the
shields.io badges (one block at the top), classroombookings.com, gnu.org and the user-attachments video line.

Length: about 410 source lines, of which 75 are the generated Done table and about 40 the screenshot gallery; the text a
reader scrolls through without opening a `<details>` is about 270 lines.

## 3. Community-health files

| File | Content | Source of truth |
|---|---|---|
| `.github/CONTRIBUTING.md` | ways to help, layout, set-up (`scripts/dev.sh --run`), the checks table, house rules (tests first, TR+EN, simplicity, accessibility, generated docs, read-only guards, no secrets or personal data), PR rules, licence | docs/DEVELOPMENT.md, docs/AGENTS.md, docs/agents/briefs/COMMON.md |
| `.github/CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, unmodified except the contact method (SUPPORT.md "Private reports") | contributor-covenant.org |
| `.github/SECURITY.md` | private vulnerability reporting, what to include, response time, scope, the per-instance security.txt | docs/SECURITY.md (security.txt row) |
| `.github/SUPPORT.md` | "you want to → go to" table, private reports, Turkish summary | |
| `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `config.yml` | issue forms with area / role dropdowns, a no-personal-data checkbox; blank issues off; a private security contact link | |
| `.github/pull_request_template.md` | what and why, verification, the TR+EN / accessibility / no-secrets / no-workflow / guards checklist | |
| `CITATION.cff` | CFF 1.2.0, "SmartSched contributors", AGPL-3.0, upstream classroombookings as a reference | |

Not added, on purpose: `CODEOWNERS` (no owner handle appears in the git history; every commit is by the agent
account or the upstream author), `FUNDING.yml` (no funding channel), `.github/dependabot.yml` (it would open
pull requests on GitHub, and the project's CI and dependency audit run on the pod), and any workflow.

## 4. Social preview

`docs/launch/media/social-preview.png`, 1280 × 640, 0.26 MB: dark brand lockup, the English tagline, the Turkish
line, four chips (Excel import, CP-SAT solver, Booking grid, Self-hosted) and a crop of the run-report poster on
the GitHub dark background with a navy glow (`--brand-navy` #0B3F86). It names no repository, owner or branch.
Made from a small HTML page (Inter from the system fonts) with headless Chromium at 1280 × 900, then cropped to
1280 × 640. Referenced from docs/launch/README.md §6 so the orphan check passes.

## 5. Owner steps on github.com

1. **Social preview.** Settings → General → Social preview → Edit → Upload an image… → `docs/launch/media/social-preview.png`.
2. **About** (the gear next to "About" on the repository page):
   - Description: `Timetabling, exam planning and room booking for universities: reads the planning office's Excel workbooks, solves with OR-Tools CP-SAT, and runs the classroombookings booking grid on top. Turkish and English.`
   - Website: the public URL of the production instance, if there is one; otherwise leave it empty.
   - Topics: `timetabling`, `course-scheduling`, `exam-scheduling`, `room-booking`, `university`, `education`,
     `constraint-programming`, `or-tools`, `cp-sat`, `fastapi`, `nextjs`, `postgresql`, `self-hosted`, `kvkk`,
     `classroombookings`, `turkish`.
   - Untick "Packages" and "Deployments" if they stay empty.
3. **Private vulnerability reporting.** Settings → Code security → Private vulnerability reporting → Enable.
   SECURITY.md, SUPPORT.md, the Code of Conduct and the issue chooser all point at it.
4. **Labels.** The issue forms apply `bug` and `enhancement`, GitHub's default labels; recreate them if they were deleted.
5. **Inline video.** After uploading the re-rendered launch video in the README editor, replace the
   `https://github.com/user-attachments/assets/…` line under the hero with the new one (on a line of its own).
6. **Optional:** add `.github/CODEOWNERS` with `* @<owner-handle>` once the final handle is settled.
