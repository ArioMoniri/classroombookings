# Component sources & licences

Every file in `src/components/ui` and every pattern borrowed from a component site is listed here
(docs/design/navigation-shell.md §9 and tokens.md §9 are the research-side tables).

| Component(s) | Source | Licence | Modified | Notes |
|---|---|---|---|---|
| avatar, badge, button, card, checkbox, command, dialog, dropdown-menu, input, input-group, label, popover, progress, scroll-area, select, separator, sheet, skeleton, slider, sonner, switch, table, tabs, textarea, tooltip | shadcn/ui `npx shadcn@latest add …` (https://ui.shadcn.com) — style `base-nova`, built on `@base-ui/react` | MIT | no (generated as-is) | Tokens are aliased in `src/app/globals.css` so no edits were needed |
| cmdk (inside `command.tsx`) | https://github.com/pacocoursey/cmdk | MIT | no | |
| sonner (inside `sonner.tsx`) | https://github.com/emilkowalski/sonner | MIT | no | |
| `@base-ui/react` primitives | https://base-ui.com | MIT | — | transitive dependency of the shadcn style |
| `tw-animate-css` | https://github.com/Wombosvideo/tw-animate-css | MIT | — | imported by `globals.css` |
| `cn` helper (`src/lib/utils.ts` re-exports the `cn` package) | https://www.npmjs.com/package/cn | MIT | no | |
| lucide-react icons | https://lucide.dev | ISC | — | |
| @dnd-kit/core, @dnd-kit/utilities | https://dndkit.com | MIT | — | timetable drag-drop |
| @tanstack/react-virtual, react-table, react-query | https://tanstack.com | MIT | — | |
| motion | https://motion.dev | MIT | — | springs, `useReducedMotion` |
| next-themes | https://github.com/pacocoursey/next-themes | MIT | — | |

## Patterns re-implemented from references (no code copied)

| Pattern | Reference | Why not copied |
|---|---|---|
| Sliding nav indicator (`layoutId`) | transitions.dev "Tabs sliding" | custom licence; re-implemented with `motion` springs from tokens.md §6 |
| Undo toast with drain | Kinetics "Undo Snackbar", Linear | no licence file; built on sonner `action` |
| Conflict pulse / drop-ok outline | Clockwise & Motion (Mobbin) | product screenshots, pattern only |
| Command palette footer legend | Devin / Supabase (Mobbin) | pattern only |

No code from kobra.systems, reverseui.com, Kinetics or transitions.dev is included in this repository.
