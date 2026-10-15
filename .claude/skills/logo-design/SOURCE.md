# Source of this vendored skill

- Upstream: https://github.com/kaankiziltug/logo-design-skill (path `skills/logo-design/`)
- Commit: `0ecf52e9a4b3ac92b714f7cc6e3148ab8c774134` (HEAD of `main`, fetched 2026-10-15)
- Licence: MIT, Copyright (c) 2026 kaankiziltug. Full text in `LICENSE` (kept verbatim, as MIT requires).

## What is vendored

Plain markdown only, byte-for-byte from upstream:

- `references/*.md` (14 files: principles, discovery-brief, mark-types, visual-techniques, color, typography,
  process, svg-construction, testing-checklist, presentation-delivery, identity-system, redesign, critique,
  library-guide)
- `templates/brand-guidelines-template.md`
- `SKILL.md`, with one addition: a block quote marked "Local note" directly after the front matter, saying
  that the scripts and the library are not present here.

## What is deliberately not vendored

- `scripts/` (Python tools): not vendored and never run, per the task rules. Rendering in this repo uses
  `sharp`/librsvg, already a frontend dependency.
- `assets/library/svg/` (1,432 third-party logos): these are trademarks of their owners and are **not**
  covered by the MIT licence (upstream `TRADEMARKS.md`). `library-guide.md` still describes them; treat it as
  background reading.
- `templates/*.json`, README images, release zips.

## How it was used

SmartSched's mark (`docs/design/brand.md`) followed the skill's process: brief, research, concepts, black-first
SVG builds, test-and-refine loops, then the kit. The concept checkpoint (pause for the user) was collapsed
because the task brief asked for all three concepts plus a refined pick in one pass; the three concepts are kept
in `docs/images/brand/concepts/` so the user can still steer.
