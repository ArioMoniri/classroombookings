# SmartSched v2: references (Liquid Glass)

Owner: design-pro (liquid-glass v2) · Status: v2.0 (2026-10-08) · Companion: [`liquid-glass.md`](liquid-glass.md)

All screens below came from the **Mobbin MCP** in this session (`search_screens` / `search_flows`, 17 queries,
iOS and web). Each link opens the screen on Mobbin. Where a requested app was **not** in Mobbin's results,
this doc says so and names the substitute. Nothing here is copied pixel for pixel. We took the patterns
and wrote our own code (see the component table in §4 for what was actually imported, and under which licence).

Search log, so it can be reproduced: "Apple Calendar week view with translucent glass toolbar", "Settings
grouped inset lists glass nav bar iOS 26", "Fantastical day view", "Notion Calendar week view", "Linear issue
list", "Apple Music Liquid Glass tab bar", "Apple Reminders/Notes large title floating glass buttons",
"Things 3 today", "Raycast/Arc command palette", "Vercel deployments", "Cron/Amie week grid", "Apple Maps/
Weather sheet", "Apple Calendar iOS 26 capsules", "Craft workspace", "empty state left aligned", "Apple
Settings grouped rows", "segmented control sliding indicator" (flows), "Raycast settings keyboard chips".

**Not available on Mobbin in this session:** Fantastical, Cron, Raycast, Arc, Notion Calendar (the app) and
Apple Calendar/Reminders/Settings on iOS 26. For each one, the query returned other apps. Substitutes:
Amie (web and iOS, a Cron-lineage calendar) for Cron/Fantastical, Arcade + Fey + Frame.io for
Raycast/Arc, the Notion database calendar for Notion Calendar, and Apple Music / Notes / Maps / Weather /
Apple Store on iOS 26 for the Apple Liquid Glass material itself. Those four Apple apps show the
real iOS 26 chrome.

## 1. Apple, iOS 26 Liquid Glass (the material itself)

| # | Screen | What makes it feel native | Pattern we name |
|---|---|---|---|
| A1 | [Apple Music · Library](https://mobbin.com/screens/98264793-0d40-4f0f-93c9-c5ca32a2cb78) | The tab bar is a **floating capsule** inset 16 px from the edges. Search is a **separate circular glass button** next to it. The mini-player is a second, thinner capsule stacked above. Album art scrolls *under* the glass and stays legible through it. The large title is 34 pt bold with tight tracking. Rows are separated by **inset hairlines** that start at the text, not the icon. | Floating capsule bar · split search orb · inset hairline |
| A2 | [Apple Music · Recently Added](https://mobbin.com/screens/81599485-eb26-4bde-acb6-8eba65af4c14) | The glass has **no visible border**, only a 1 px specular top edge and a very soft shadow. The selected tab is a **lighter glass lozenge inside the capsule**, not a coloured pill. The tint (Music red) appears only on the selected icon and label. | Lozenge selection · tint only on the active glyph |
| A3 | [Apple Music · Playlist detail](https://mobbin.com/screens/0428f139-f9c8-4f8b-b76f-0e6adcf5e7d6) | Play and Shuffle are **fill-tinted capsules** (grey fill, red text), not solid red buttons. Top-bar actions are grouped into a single glass capsule (people · stop · more). | Grouped icon capsule · fill-tinted secondary buttons |
| A4 | [Apple Music · Edit Sections menu](https://mobbin.com/screens/d64116dc-a2a0-43ef-9cd9-fa388dbdaf23) | The menu **grows out of the button it came from** (morph), as a glass panel with a soft lens edge. | Morph-from-trigger popover |
| A5 | [Apple Music · Library edit](https://mobbin.com/screens/c84f684e-be47-49d7-a4e0-98c9e4f12f48) | The edit mode keeps the same row grid. Only checkboxes and grabbers fade in, and "Done" is a single glass circle with a check. | Mode change without layout change |
| A6 | [Apple Notes · Notes list](https://mobbin.com/screens/1ae408b2-703f-412b-b97b-2172d45f0751) | The grouped background is `systemGroupedBackground` grey. White cards have **continuous corners**. The bottom search field is a glass capsule, and compose is a separate glass circle. | Grouped inset list · bottom search capsule |
| A7 | [Apple Notes · Folders](https://mobbin.com/screens/3d0fa8db-7794-492b-b84b-ad9d2625dce5) | Section titles are **bold sentence case**, not uppercase. Counts are plain grey numerals with chevrons, never badges. | Plain counts, no badges |
| A8 | [Apple Notes · Context menu](https://mobbin.com/screens/8ce20c03-8f02-4bd3-b49e-79807e48e1a4) | The glass menu has 44 pt rows, icons left in the label colour, destructive items in red, and a separator before the group. | Glass context menu |
| A9 | [Apple Notes · Drag reorder](https://mobbin.com/screens/957d9308-1dbd-4c9b-80bd-fb53bf54f7b3) | The lifted row gets a **light shadow and lifts slightly**. The rest of the list dims. | Lift by light |
| A10 | [Apple Notes · Select mode](https://mobbin.com/screens/e827fba5-67a2-4a5c-9915-52b1c0a5dea6) | Bulk actions are **two floating glass capsules** at the bottom corners, "Move All" and "Delete All". | Floating bulk actions |
| A11 | [Apple Maps · Search capsule](https://mobbin.com/screens/edf0fec0-9d0f-4ce8-b206-86becffb51f4) | The glass sits over very busy content (a map) and stays readable because the material **tints and blurs heavily** and the text is bold black. The map controls are a vertical glass capsule. | Thick glass over content · vertical control capsule |
| A12 | [Apple Maps · Expanded sheet](https://mobbin.com/screens/93f4e585-88f7-436c-a881-b3263f657856) | The sheet **floats inset from the screen edges** with large continuous corners, so it is not glued to the bottom. It has a grabber and coloured circular icon tiles. | Inset floating sheet |
| A13 | [Weather · Precipitation sheet](https://mobbin.com/screens/7463e436-f040-46e2-aac0-c3335f8d0e56) | The list rows inside the sheet sit in a **slightly darker inset well**: glass on glass, done by a tone step rather than a border. | Inset well inside glass |
| A14 | [Weather · Layer menu](https://mobbin.com/screens/890bece5-a923-4a91-a371-41e37dc91d4a) | The menu has a single check for the selection and SF Symbols at a medium weight. Its edge comes from a specular rim, not a border. | Specular rim |
| A15 | [Weather · Forecast scrubber](https://mobbin.com/screens/e7b4fbe4-c40f-4798-b2b4-2b1745dd077a) | A glass toolbar holds a play/pause control, a title, a **small segmented control (1h · 12h)** with a white thumb, and a timeline. | Segmented with lit thumb inside a toolbar |
| A16 | [Apple Store · Upcoming](https://mobbin.com/screens/f793066c-c8d8-487c-b3ed-4ed2977f3522) | A week strip whose selected day is a solid black circle. Back and Filter are glass capsules. The large title "Today" sits in the content, not in a header bar. | Content-anchored titles |

## 2. Handcrafted third-party apps

| # | Screen | What makes it feel handcrafted (not template) | Pattern |
|---|---|---|---|
| H1 | [Things 3 · Today](https://mobbin.com/screens/724087de-2e95-47ec-926c-efbdab249a23) | **Type does the hierarchy.** The title is big and bold, rows are a regular 17 pt, metadata is a small grey line *under* the title, and the only colour is the red "today" flag. Checkboxes are square, never circles. The single FAB is the only saturated element. | Type-led hierarchy · one saturated element |
| H2 | [Things 3 · Dark](https://mobbin.com/screens/3055273e-f993-4d94-a3cb-13c1bb281726) | Dark mode uses blue-grey surfaces, not pure black, and keeps the same weights. The calendar block is an **inset well** in a lighter tone. | Designed dark, not inverted |
| H3 | [Things 3 · Multi-select bar](https://mobbin.com/screens/5bc4a73d-af7d-4e63-aca2-27d13a2b1ed1) | Bulk actions dock in a bottom bar with icon + word pairs (When · Move · Delete · …). | Bulk action toolbar |
| H4 | [Linear · Issues + filter menu](https://mobbin.com/screens/ed670cda-0527-4716-a1a6-0159f12c4f42) | 32 px rows, a monochrome status glyph, and labels as **dot + text chips**. The filter menu is dense with a search field on top. The sidebar has quiet 11 px section labels. | Dot-chip labels · dense filter popover |
| H5 | [Linear · Projects empty](https://mobbin.com/screens/5273571d-4f58-410a-97a0-f6018dc8b80f) | The empty state is **left of centre and small**: a line illustration, one paragraph, a primary button **with its keyboard shortcut inside**, and a quiet "Documentation" link. | Shortcut-in-button · small empty state |
| H6 | [Vercel · Deployments](https://mobbin.com/screens/b9d9cc23-34a1-434c-a4ed-52a2a4f49bb7) | **Status is a 8 px dot + word**, never a filled badge. Rows have no zebra stripes. The filter popover uses real checkboxes with coloured dots. Hairlines everywhere, no shadows. | Dot + word status |
| H7 | [Vercel · Deployment detail](https://mobbin.com/screens/bcd88c7b-6a42-4e01-b9ea-01fac8247bd2) | Key-value grid with 11 px grey labels over 13 px values. Collapsible rows end in a single blue check. | Quiet key-value grid |
| H8 | [Vercel · Overview cards](https://mobbin.com/screens/2d216618-1a78-48ed-8279-01c025c60423) | Cards differ in **size and content** (checklist, sparkline, number), not just colour. | Heterogeneous cards |
| H9 | [Amie · Week grid](https://mobbin.com/screens/3eb89cf5-9ce8-449e-841e-6bd17ea2ade0) | Events have a **3 px left stripe + 15 % tint**. The red now-line has a time label in the gutter. The AI composer floats as a capsule at the bottom of the grid. The calendar colour set is shown as a row of dots in the toolbar. | Stripe + tint events · floating composer |
| H10 | [Amie · Event popover](https://mobbin.com/screens/6a43b486-6bcb-40af-bedb-720fbcb44496) | A pending event uses **diagonal hatching**, which matches our `preoccupied` hatch. The popover is a compact form with a footer icon row. | Hatch for "not yours" |
| H11 | [Amie iOS · Split calendar](https://mobbin.com/screens/18d0ae58-327f-4eed-9e90-de3dd079b250) | A calendar on top and lists below, joined by a grabber. Events are rounded tint blocks with the duration right-aligned. | Split view with grabber |
| H12 | [Notion · Database calendar](https://mobbin.com/screens/5b3dd0a5-2981-487b-9510-c7d46f221c53) | Today is a small red circled numeral. Cards inside cells are white with a hairline, and property chips are pastel. | Today marker |
| H13 | [Notion · Timeline](https://mobbin.com/screens/6d9641f2-a575-4695-92ef-aea771018018) | Weekend columns are tinted, a red today line runs through, and rows are inline (name · date · chips). | Timeline row grammar |
| H14 | [Craft · Format inspector](https://mobbin.com/screens/7bc7bdc7-a309-45df-ad25-b45e0d3c6e83) | The inspector is built from **segmented tiles** (Title/Subtitle/Heading), a swatch grid and toggle tiles. Section labels are small grey text. | Tile-segmented inspector |
| H15 | [Craft · Translucent popover over image](https://mobbin.com/screens/0670d603-b651-426e-b757-0f35de0ac97c) | A real **frosted glass panel on the web**: heavy blur, bright tint and a soft edge, legible over a photo. | Web glass done right |
| H16 | [Craft · Edit field dialog](https://mobbin.com/screens/ca94c6fe-5935-494c-92a3-b2b611aa1f7c) | Small dialogs anchored to their context, not centred over the page. Cancel is a grey fill and Apply is blue. | Anchored dialog |
| H17 | [Craft iOS · Today](https://mobbin.com/screens/d171ec4b-4c44-4657-8332-5b2ab1e22132) | Bottom tools sit in **two separate glass capsules** (attach · pen | brush · AI). The top bar is a glass capsule group. | Capsule groups split by role |
| H18 | [Arcade · Command palette](https://mobbin.com/screens/3db6503f-635e-4a6b-9eef-bce8acb87610) | The page behind is **blurred and dimmed** (backdrop). The palette has a borderless input, quiet section headers, and a footer with keycaps ("↩ to view"). | Spotlight-style palette |
| H19 | [Arcade · Inspector segmented](https://mobbin.com/screens/86dff979-bdae-45b6-87a2-3b31ae0caaf6) | Small segmented controls (Buttons/Form/Embed, Light/Dark/Custom, Blur Off/S/M) with a white lit thumb on a grey track. | Lit-thumb segmented |
| H20 | [Fey · Settings + dock + shortcuts](https://mobbin.com/screens/8b9c1ba1-2c38-4313-8831-f95469c3db47) | **The web dock as a floating glass capsule** at the bottom centre, with search as a separate circle. The shortcut sheet shows keycaps in rounded grey caps. | Web floating dock · keycaps |
| H21 | [Perplexity · Settings modal](https://mobbin.com/screens/9931ff5d-3715-428e-bff4-6e543e1e9944) | Appearance is shown as **preview tiles**. Settings rows have the label + description on the left and the control on the right, with selects as small capsules. | Settings row grammar |
| H22 | [Frame.io · Keyboard shortcuts](https://mobbin.com/screens/7bf0c9af-dd42-4511-a35e-15e097df461b) | Keycaps are square-ish caps with an inner bottom edge, grouped per section. | Keycap style |
| H23 | [Superlist · Empty list](https://mobbin.com/screens/d9ea2799-1057-48ab-aef6-efc79275c844) | The content panel floats on a tinted background (panel-on-scene). The empty state is a line drawing, two short sentences and a grey capsule action. | Panel on scene |
| H24 | [Moonlitt · Settings sheet](https://mobbin.com/screens/ac883a70-c3ff-45e1-a625-2e2a7bdd788b) | A grouped glass list over a deep gradient, showing that the scene colour bleeds through the material. | Scene bleed-through |
| H25 | [Revolut Business · Menu](https://mobbin.com/screens/306687c3-03e3-4ed3-9ab7-fc9c179b4705) | Grouped glass sections over a blurred app, with white icons at a consistent weight. | Grouped glass sections |
| H26 | [Structured · Timeline](https://mobbin.com/screens/297aa3fc-85b4-4fc6-b9c2-8ba935f089e5) | A floating tab bar plus a floating detail card. Events sit as capsules on a vertical track. | Floating detail card |

### Flows

| # | Flow | What we take |
|---|---|---|
| F1 | [Revolut · Switching views](https://mobbin.com/flows/e216d8bd-537c-4f75-903c-fd9ff3af7866) | A segmented icon control (line / bar / ring) swaps the chart, and the period segmented control (1W/1M/6M/1Y) keeps its state. The content changes, the controls do not move. |
| F2 | [MD Vinyl · Switching view](https://mobbin.com/flows/bc16c3bc-c68d-43d2-b41f-4167329d4193) | A glass segmented control ("Albums / Playlists") with a **white thumb that slides**, plus a floating bottom capsule of three icons. |
| F3 | [Public · Switching view](https://mobbin.com/flows/636c5960-ce52-4dbc-9050-c1b6ac412044) | A small "Chart / Data" segmented control at top-left, and a metric selector as text tabs with an outlined active state. |

### Anti-references (what "AI-generated" looks like, avoid)

| Screen | Tell |
|---|---|
| [Apollo · Lists empty](https://mobbin.com/screens/4ce08bdb-e301-44bb-9f68-a1a2293baab6) | Centred stock illustration, two equal buttons, and a "learn more" link: a generic empty state |
| [HubSpot · Unnamed list](https://mobbin.com/screens/1f61dd9a-ad64-47ed-bdef-f840c67cdfbc) | Centred isometric illustration with the headline under it, used for a one-line instruction |
| [Asana · Project list](https://mobbin.com/screens/bca47125-14ae-4413-a719-927c75a679fe) | A saturated pill in every row (priority) that competes with the content (over-badging) |

## 3. What we take into SmartSched (summary)

1. **Material by position, not by component.** Floating chrome (toolbar, palette, sheets, popovers) uses
   thick or chrome glass. Content cards use regular glass on the scene. Lists inside glass use hairlines
   or inset wells (A11, A13, H15).
2. **Capsules for controls, continuous corners for containers** (A1, A3, A6, H17, H20).
3. **One tint.** It appears on the active glyph, the primary action and links, nowhere else (A2, H1).
4. **Status = glyph + word, quiet fill** (H6, A7). The amount of badging drops by half compared with v1.
5. **Type hierarchy first.** Large titles in the content, 11 px quiet section labels, grey metadata
   under the title (H1, A16, H4).
6. **Motion that morphs from the source.** Segmented thumbs glide, menus grow from their trigger and sheets
   arrive inset (A4, F2, A12).
7. **Keyboard is visible.** Keycaps sit in buttons, palettes and sidebars (H5, H18, H20, H22).
8. **Left-aligned, small empty states** with one action (H5, H23), never the centred stock illustration.

## 4. Component sources (actually imported in this branch)

The licence was verified for each source by fetching the actual licence text on 2026-10-08. Every
imported file carries a `// Source: … — Licence: …` header, and `src/components/ui/SOURCES.md` has
one row per file.

| Source | What we imported | How | Licence (quoted) |
|---|---|---|---|
| **beUI** · beui.dev · github.com/starc007/ui-components | `tabs`, `number-ticker`, `animated-toast-stack`, `file-upload`, `status-bar` (+ its tooltip, hooks), `expandable-action-bar`, `dock`, shared `lib/{ease,touch,utils}` → `src/components/ui/beui/**` | `npx shadcn add @beui/<name>` with `"@beui": "https://beui.dev/r/{name}.json"` in `components.json`. The CLI ran in a scratch copy of the project because a direct add would **overwrite `src/lib/utils.ts`** and write to `src/lib`. The files were then moved under `ui/beui` with their import paths re-pointed. | LICENSE: *"MIT License — Copyright (c) 2026 Saurabh Chauhan — Permission is hereby granted, free of charge, to any person obtaining a copy of this software … to deal in the Software without restriction …"* (raw.githubusercontent.com/starc007/ui-components/main/LICENSE). Copy: `src/components/ui/LICENSES/beui-MIT.txt` |
| **evilcharts** · evilcharts.com · github.com/legions-developer/evilcharts | `recharts-bar-chart`, `recharts-area-chart`, `recharts-radial-chart` + `ui/recharts-{chart,tooltip,legend,dot,brush,background}` → `src/components/ui/evilcharts/**` | `npx shadcn add @evilcharts/recharts-…` (`"@evilcharts": "https://evilcharts.com/r/{name}.json"`). Adds the `recharts@3.10` dependency | LICENSE: *"MIT License — Copyright (c) 2026 Gurbinder — Permission is hereby granted, free of charge …"* (raw.githubusercontent.com/legions-developer/evilcharts/main/LICENSE). Copy: `LICENSES/evilcharts-MIT.txt` |
| **beautifului.dev** (© Shane Levine) | Ports of **Diff Table**, **Task Rows** and the **Chat Composer** composer → `src/components/ui/beautifului/{diff-table,task-rows,prompt-composer}.tsx` | Source pulled from the registry JSON `https://www.beautifului.dev/r/<name>.json`. The demos (setTimeout scripts, ice-cream data) were removed, the components made data-driven, and the tokens re-mapped. A direct install would also add its own 17 kB `foundation.css` token system, which we do not want. | https://beautifului.dev/license: *"Yes, you can use it for free. MIT License … Copyright (c) 2026 Shane Levine … The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software."* Copy: `LICENSES/beautifului-MIT.txt` |
| **transitions.dev** (Jakub Antalik) | Free transitions **Modal open / close**, **Panel reveal**, **Error state shake** (CSS) → `src/components/ui/transitions/transitions-dev.css`, imported by `globals.css`. Used by Dialog (`.t-modal`), Popover/Select/Menu/Tooltip (`.t-panel-slide`) and Input (`.t-input` + `useShake`) | Copied from `transitions.dev/transitions/<slug>/`. Durations retuned to ≤ 300 ms and a Base UI `data-starting-style` mapping added. The **"Transitions.dev — <name>" comment is kept**. | Repo LICENSE: *"you … may use the transitions … in unlimited personal and commercial projects, modify them freely, and ship them to your users … The one restriction is that you may not redistribute the transitions library itself as a competing product."* Terms page: *"Every transition — free or Pro — is a snippet of CSS … you may use it in unlimited personal and commercial projects."* Copy: `LICENSES/transitions-dev-LICENSE.txt` |
| **Astryx** · astryx.atmeta.com · github.com/facebook/astryx | **Nothing imported.** StyleX would add a second styling runtime next to Tailwind 4. We use its idea of semantic token naming (label/fill/hairline) and its status-with-glyph pattern only. | n/a | LICENSE: *"MIT License — Copyright (c) 2026 Meta Platforms, Inc."* (permits use, but impractical here) |
| **Kinetics** · kinetics.colorion.co · github.com/ckissi/kinetics | **Nothing imported.** We reviewed its "Tab Pill Glide", "Liquid Glass Press", "Toast Overshoot" and "Choice Chips" for feel. Our spring presets in `motion-presets.ts` and the CSS `linear()` curves are our own parameters (ζ, ω chosen for ≤ 300 ms settle). | n/a | **No licence**: `LICENSE`, `LICENSE.md` → 404, and README / `package.json` have no licence field (checked 2026-10-08). So: reference only. |
| **kobra.systems** | **Nothing**: paid | n/a | Pricing page: Free tier *"Personal use only"*; Individual *"199USD"* *"Unlimited commercial projects"* (one-time); Teams *"599USD"*, *"2–25 seats on one license"* |
| **reverseui.com** | **Nothing**: paid (free tier has no OSS licence text) | n/a | Pricing page: Free *"$0.00"* *"19 free components, full source"*, *"Commercial use"*; Essential *"$39.00"* *"one-time payment"*, *"1 developer license"*; Team *"$175.00"*, *"20 developer license"* |

### 4.1 Purchase recommendations (not bought, not copied)

| Vendor | Component | Why it would help SmartSched | Where it would replace our code | Price (2026-10-08) |
|---|---|---|---|---|
| kobra.systems | **Magnetic Dropzone** | A better drop affordance for the import wizard (the file "snaps" toward the target) | `beui/file-upload` in `/import` | Individual **$199** one-time (Teams $599, 2–25 seats) |
| kobra.systems | **Grouped Table** / **CRM Table** | Grouped headers, sticky group rows and inline editing for the requests inbox and the rooms list | `common/data-table.tsx` | (same licence) |
| kobra.systems | **Calendar** | Reference for month and range picking in the term and exam scope | studio scope step | (same licence) |
| reverseui.com | **Timeline Progress** | Solver run progress as a timeline (phases: presolve → search → polish) | `/runs/[id]` header | Essential **$39** one-time (1 dev) · Team $175 (20 devs) |
| reverseui.com | **Logs Explorer** | Solver and import logs with filters and level chips | run report "Logs" tab | (same licence) |
| transitions.dev | **Pro set** (e.g. *Dropdown menu morph*, *Spinner to check morph*) | Native-feeling morphs for menus and the solve button | Popover/menus, generate button | Prices shown only at checkout. A company needs the **Business** plan ("Required when the Pro transitions … are used by or on behalf of a company") |

Recommendation: buy **reverseui Essential ($39)** first, for Timeline Progress and Logs Explorer, which close
two run-report gaps. Then **kobra Individual ($199)** if the import wizard and inbox get a v3. Neither is
needed for v2.
