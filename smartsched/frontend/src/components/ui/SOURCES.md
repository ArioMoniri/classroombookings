# Component sources & licences

Every file in `src/components/ui` is listed here. Each imported file also carries a
`// Source: … — Licence: … — Modified: …` header. Full licence texts are in `LICENSES/`. The research
and licence verification are in `docs/design/v2/references.md` §4, and the system spec is
`docs/design/v2/liquid-glass.md`. Licences were checked on 2026-10-08 by fetching the actual licence file or page.

## shadcn/ui primitives (restyled for Liquid Glass v2, APIs unchanged)

| Component(s) | Source | Licence | Modified | Notes |
|---|---|---|---|---|
| button, badge, card, input, input-group, textarea, select, dropdown-menu, popover, tooltip, dialog, sheet, tabs, command, sonner, table, switch, checkbox, progress, skeleton, slider | shadcn/ui `npx shadcn@latest add …` (https://ui.shadcn.com), style `base-nova` on `@base-ui/react` | MIT | **yes**: v2 classes, glass materials, transitions.dev hooks, layoutId tab thumb; badge adds `tone`, card adds `variant` | header comment in each file |
| avatar, label, separator, scroll-area | shadcn/ui (same) | MIT | no | read the re-valued tokens |
| cmdk (inside `command.tsx`) | https://github.com/pacocoursey/cmdk | MIT | no | |
| sonner (inside `sonner.tsx`) | https://github.com/emilkowalski/sonner | MIT | no | retimed via `[data-sonner-toast]` in globals.css |

## Imported from the reference sites

| File(s) | Source | Licence (verified) | Install / how | Modified |
|---|---|---|---|---|
| `beui/tabs.tsx` | beUI `@beui/tabs`, https://beui.dev (repo github.com/starc007/ui-components) | MIT © 2026 Saurabh Chauhan, `LICENSES/beui-MIT.txt` | `npx shadcn add @beui/tabs` (registry `https://beui.dev/r/{name}.json` in `components.json`) | yes: import paths; `labelClassName` prop on TabsTrigger |
| `beui/number-ticker.tsx` | `@beui/number-ticker` | MIT (same) | shadcn registry | import paths |
| `beui/animated-toast-stack.tsx` | `@beui/animated-toast-stack` | MIT (same) | shadcn registry | import paths |
| `beui/file-upload.tsx` | `@beui/file-upload` | MIT (same) | shadcn registry | import paths |
| `beui/charts/status-bar.tsx`, `beui/charts/status-bar/{context,legend,plot,tooltip}` | `@beui/status-bar` | MIT (same) | shadcn registry | import paths |
| `beui/expandable-action-bar.tsx` | `@beui/expandable-action-bar` | MIT (same) | shadcn registry | import paths |
| `beui/dock.tsx` | `@beui/dock` | MIT (same) | shadcn registry | import paths |
| `beui/tooltip.tsx`, `beui/tooltip-surface.tsx`, `beui/tooltip/{positioner,use-position}` | dependencies of `@beui/status-bar` | MIT (same) | shadcn registry | import paths |
| `beui/lib/{ease,touch,utils}.ts`, `beui/lib/hooks/{use-dismiss,use-hover-capable,use-hover-gesture,use-tap-gesture}.ts` | beUI shared libs pulled by the items above | MIT (same) | shadcn registry, **relocated** from `src/lib` so `src/lib/utils.ts` is not overwritten | import paths |
| `evilcharts/charts/recharts-{bar,area,radial}-chart.tsx` | EvilCharts `@evilcharts/recharts-*`, https://evilcharts.com (repo github.com/legions-developer/evilcharts) | MIT © 2026 Gurbinder, `LICENSES/evilcharts-MIT.txt` | `npx shadcn add @evilcharts/recharts-bar-chart …` (registry `https://evilcharts.com/r/{name}.json`) | import paths |
| `evilcharts/ui/recharts-{chart,tooltip,legend,dot,brush,background}.tsx` | EvilCharts registry dependencies | MIT (same) | shadcn registry | no (chart/tooltip/legend), import paths (others) |
| `beautifului/diff-table.tsx` | beautifului.dev "Diff Table" (`https://www.beautifului.dev/r/diff-table.json`) | MIT © 2026 Shane Levine, `LICENSES/beautifului-MIT.txt` (text from https://beautifului.dev/license) | source from the registry JSON, ported | yes: demo timers and data removed, data-driven, real checkbox controls, tokens re-mapped |
| `beautifului/task-rows.tsx` | beautifului.dev "Task Rows" (`/r/task-rows.json`) | MIT © 2026 Shane Levine | ported | yes: status prop instead of the scripted ticks, retry button, i18n labels, layout tweens removed |
| `beautifului/prompt-composer.tsx` | beautifului.dev "Chat Composer" (`/r/chat-composer.json`), composer part | MIT © 2026 Shane Levine | ported | yes: extracted from the demo, auto-grow textarea, busy/stop, suggestions |
| `transitions/transitions-dev.css` | transitions.dev free transitions "Modal open / close", "Panel reveal", "Error state shake" | Transitions.dev License © 2026 Jakub Antalik: commercial use allowed, no redistribution of the library, keep the `Transitions.dev — <name>` comment. `LICENSES/transitions-dev-LICENSE.txt` | copied from `transitions.dev/transitions/<slug>/` | yes: ≤ 300 ms, Base UI `data-starting-style` mapping, no filter/will-change on glass popups |
| `src/assets/lottie/*.json`, `*-poster.png` (used by `empty-state.tsx`) | `docs/lottie`, `docs/images/lottie` (original SmartSched work) | AGPL-3.0 (same as the repository) | copied | no (the background layer is dropped at runtime) |

npm dependencies added: `recharts@^3.10.1` (MIT, for EvilCharts), `@floating-ui/dom@^1.8.0` (MIT, for the
beUI tooltip/status-bar), `lottie-react@^3.1.2` (MIT, for EmptyState). `clsx`, `tailwind-merge` and
`motion` were already present.

## Original SmartSched primitives (Liquid Glass v2)

| File | What | Pattern references (no code copied) |
|---|---|---|
| `glass-panel.tsx` | GlassPanel (5 materials) | Apple iOS 26 materials (Mobbin A1–A15), Craft H15 |
| `toolbar.tsx` | floating capsule Toolbar | Apple Music A1, Fey H20, Things 3 H3 |
| `sidebar-glass.tsx` | SidebarGlass with gliding pill | macOS 26 sidebars, Linear H4, Craft |
| `segmented-glass.tsx` | SegmentedGlass, **built on `beui/tabs` (MIT)** | Weather A15, Arcade H19, MD Vinyl F2 |
| `chip.tsx` | toggle/token Chip | Linear H4, Kinetics "Choice Chips" (feel only, no licence, so no code) |
| `kbd-hint.tsx` | keycaps | Frame.io H22, Linear H5, Arcade H18 |
| `empty-state.tsx` | EmptyState + Lottie with poster fallback | Linear H5, Superlist H23 |
| `appearance-preferences.tsx` | in-app Reduce motion / Reduce transparency | motion.md §5 |
| `field-styles.ts` | shared filled-field surface | Apple text fields |
| `motion-presets.ts` | aliases of `@/lib/motion` springs | `@/lib/motion` = verbatim copy of `.claude/skills/motion_designer/references/motion-tokens.ts` |

## Reference only (nothing copied)

| Site | Why | What we used |
|---|---|---|
| kinetics.colorion.co | no LICENSE in github.com/ckissi/kinetics (404), no licence field | the feel of springs; our parameters are in `@/lib/motion` |
| astryx.atmeta.com | MIT, but StyleX is a second styling runtime | semantic token naming (label/fill/hairline), status-with-glyph |
| kobra.systems | Free tier "Personal use only"; Individual $199 / Teams $599 | see the purchase recommendations in references.md §4.1 |
| reverseui.com | paid (Essential $39 / Team $175); the free tier has no OSS licence text | see references.md §4.1 |

## Earlier patterns (v1, still valid)

| Pattern | Reference | Why not copied |
|---|---|---|
| Sliding nav indicator (`layoutId`) | transitions.dev "Tabs sliding" | re-implemented with motion springs |
| Undo toast with drain | Kinetics "Undo Snackbar", Linear | no licence file; built on sonner `action` |
| Conflict / drop-ok outline | Clockwise & Motion (Mobbin) | product screenshots, pattern only |
| Generator Studio segmented, upload rows, diff list | beUI motion tabs / file upload, beautifului Diff Table | re-implemented in `components/studio` (2026-10-08) |

No code from kobra.systems, reverseui.com or Kinetics is included in this repository.

## Paid-component decisions (user decision 2026-10-08: do not buy; free parts or free alternatives only)

Recorded by the glass-shell agent. Nothing below was bought or copied.

| Need | Paid suggestion | Decision | Evidence / what ships instead |
|---|---|---|---|
| Run-progress timeline (`/runs/[id]` while solving) | reverseui.com "Timeline Progress" (Essential $39) | **Not imported.** reverseui's pricing page lists "Free plan includes: 19 free components, full source, Commercial use", but the site has **no licence or terms page** (`/terms`, `/license` → 404; no legal URL in `sitemap.xml`, checked 2026-10-08 with curl), so there is no text granting modification or redistribution inside this AGPL repository. | Built on our primitives: `beautifului/task-rows` (MIT) fed with the worker's real phases (`components/runs/run-view.tsx`, `SolveProgress`). reverseui used as visual reference only. |
| Run-report log viewer | reverseui.com "Logs Explorer" | **Not imported** (same licence gap). | No backend log route exists yet; the report shows planner-facing groups from `GET /runs/{id}/data-issues` with an Excel download instead. Backlog item in ROADMAP. |
| Import dropzone | kobra.systems "Magnetic Dropzone" ($199; free tier "Personal use only") | **Not allowed** (personal-use-only free tier, paid otherwise). | `beui/file-upload` (MIT) wrapped in `components/import/magnetic-drop.tsx`: magnetic lift/lean on drag from the /motion_designer patterns §7 + §14 (transform only, reduced-motion safe). |
| Menu morph, spinner → check | transitions.dev Pro | **Not used.** Only the free set already in `transitions/transitions-dev.css` (Modal, Panel reveal, Error shake). | Our own motion patterns (`@/lib/motion`, motion_designer §1, §10). |
