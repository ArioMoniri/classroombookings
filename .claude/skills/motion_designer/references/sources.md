# References and licences

Mobbin shows static frames, and flows are frame sequences. The motion each one "teaches" below is inferred from consecutive frames plus the platform behaviour it is known for, and is labelled as such. Apple Calendar, Fantastical and Arc are not indexed on Mobbin (searched 2026-10-08). The closest indexed substitutes are listed and marked *substitute*. For Apple's own motion, the primary sources are the WWDC25 sessions and the HIG (section C).

## A. Interaction references (Mobbin)

| # | Reference | What it shows | Motion it teaches us |
|---|---|---|---|
| 1 | [Microsoft Outlook iOS: Scheduling an event (drag & drop)](https://mobbin.com/flows/0150a4f9-7bed-4e79-8a7d-ed34936ea058) (*substitute for Apple Calendar*) | event block with two round handles on opposite corners. The label "10:00 AM → 10:30 AM (30 min)" updates live and snaps to 15 min | resize by handle with a live value readout. The value snaps in steps, never per pixel (pattern 8) |
| 2 | [Notion web: Moving a database entry (calendar)](https://mobbin.com/flows/87ab717f-d6e4-4285-a389-eeefde3bde52) | origin entry fades, target day cell tints blue, entry lands in the new week | faded origin plus a single target highlight. The drop settles into place (pattern 7) |
| 3 | [Notion web: Editing entry duration (timeline)](https://mobbin.com/flows/574bca25-653e-4b19-b02d-b0d8e69e1bf9) | edge handle on a timeline bar shows an end-date chip ("Mar 2") while dragging | the resize affordance appears on hover/focus only, with a value chip that follows the edge (pattern 8) |
| 4 | [Things 3 iOS: Reordering area](https://mobbin.com/flows/34d52d4c-81e2-4ee5-b884-1b0587ad74d2) | lifted row gains a tint and a shadow, and the neighbours slide into the gap | lift = tint + shadow + slight scale, and siblings reflow with a spring (patterns 6, 7) |
| 5 | [Things 3 iOS: Editing a to-do list](https://mobbin.com/flows/759e30bf-a470-4c6b-9a36-415ccd28476d) | a row expands into a card in place, the rest dims, and a floating dark Move/Delete bar appears | in-place expand (same object grows, no navigation) plus a floating action bar that slides up (patterns 19, 6) |
| 6 | [Waymo iOS: floating capsule tab bar](https://mobbin.com/screens/209d586d-c74b-476b-883f-50b5d26c6a78) | iOS 26-style floating bar with a selected pill | a floating glass tab bar whose pill moves between tabs (pattern 3) |
| 7 | [Waymo iOS: Dynamic Island live activity](https://mobbin.com/screens/4efe7527-be42-43db-b5b0-88f9673179d4) | compact island "21 min" | a compact live-status pill that expands into detail, which becomes our run island (pattern 19) |
| 8 | [Hypelist iOS: Place detail](https://mobbin.com/flows/78e0a6b8-fd4d-47ed-ac5d-38f2b6c6f620) | a card over the map grows into a sheet and the image stays continuous | shared-element continuity (card → sheet, `layoutId`) |
| 9 | [Wanderlog iOS: Switching to map view](https://mobbin.com/flows/593294c6-d415-4271-9644-4cf16b81f139) | sheet with grabber at a medium detent over a map, expands | detents with a visible grabber (pattern 4) |
| 10 | [Opendoor iOS: Sorting map](https://mobbin.com/flows/25233fc5-3e4f-41a1-8c38-405b7088df8b) | a floating pill opens a short sheet over a dim backdrop and returns to a pill with the new label | pill → sheet → pill: origin-aware open and return (patterns 1, 4) |
| 11 | [Linear web: Searching shortcuts](https://mobbin.com/flows/7f061cb3-54c7-48de-a070-6c6cde5f443f) | the right panel filters results as you type, with no list animation | **don't animate filtering**: results swap instantly (stagger rules) |
| 12 | [Linear web: Filtering issues](https://mobbin.com/flows/f7e892c1-7f23-4267-a950-ed9c4bb904dc) | cascading menus, a chip appears in the filter bar, "14 issues hidden by filters" | chip insert with layout reflow, and cascade menus that open from their row (patterns 1, 6) |
| 13 | [Linear web: New issue composer](https://mobbin.com/screens/ffa2e456-85c7-4005-b361-de79dc6b6dc7) | a composer anchored in the top third over a dimmed page | palette and composer anchoring, scale-from-top (pattern 18) |
| 14 | [Arcade web: search palette over heavy blur](https://mobbin.com/screens/f8819696-8bc2-4192-8e62-70e1190d6fef) (*substitute for Arc*) | glass command palette, page blurred behind | glass palette over a blurred scrim, and legibility of "No results" on glass (pattern 18) |
| 15 | [Structured iOS: timeline with floating tab bar](https://mobbin.com/screens/79c1499b-7d1f-443c-89ef-55791669fbbc) (*substitute for Fantastical*) | translucent floating tab bar plus FAB over a dense timeline | scroll-edge treatment where glass chrome sits over moving schedule content (patterns 3, 15) |
| 16 | [Rodeo iOS: frosted input over calendar](https://mobbin.com/screens/06a0a6b4-f911-410b-898d-6d42d14b42be) (*substitute for Fantastical NL input*) | a natural-language input bar in frosted glass above the keyboard | NL input as a glass accessory that rises with the keyboard (chat composer) |
| 17 | [Copilot iOS: segmented pill tabs](https://mobbin.com/screens/39d3efee-7a8a-4fa5-ae15-1065a33dfae1), [Stardust iOS: Day/Month/Year](https://mobbin.com/screens/3e4e004e-47a7-4343-a1d4-eba972fb4905) | capsule segmented controls | the segmented pill morph (pattern 2) |
| 18 | [Replit: agent "Thinking"](https://mobbin.com/screens/de74cd60-7862-49e9-b805-3c427e4c44a5), [Unify: "Waiting for your answer 8s"](https://mobbin.com/screens/3fe27a24-cdf7-4e3d-aa59-57dff9cecb75), [Square: "Thinking…"](https://mobbin.com/screens/ba9fcbfc-11b2-491a-81d8-71b3e853c407) | AI waiting states, one with an elapsed counter | the thinking shimmer plus an elapsed counter after 5 s (pattern 17) |
| 19 | [Delphi: notifications growing from the avatar](https://mobbin.com/screens/11350c17-180f-437c-a48d-384f653b477e), [Klaviyo: toast with side drawer](https://mobbin.com/screens/7e468229-0914-4474-9c94-f4fd4ba2c362) | a panel that grows from its trigger, and a top toast | origin-aware panel growth (pattern 1) and toast placement (pattern 5) |

## B. Motion sources and licence decisions

| Source | What we use | Licence (checked 2026-10-08) | Decision |
|---|---|---|---|
| [motion.dev](https://motion.dev/docs/react-transitions) (`motion` 14.0.0) | the API itself: springs, `layout`, `layoutId`, `AnimatePresence`, `Reorder`, gestures, `useScroll`, `useReducedMotion`, `MotionConfig reducedMotion` | MIT (`node_modules/motion/LICENSE.md`) | installed dependency. Docs consulted: transitions, layout animations, AnimatePresence, gestures, scroll, MotionConfig, useReducedMotion |
| [beUI](https://beui.dev) ([repo](https://github.com/starc007/ui-components)) | Animated Toast Stack, Bottom Sheet, Dynamic Island, Command Palette, Morphing Modal, Sortable List as references. Their `lib/ease.ts` spring families (press 500/30/0.6, panel 420/40/0.5, layout 360/32/0.6, glide 700/50/0.5) informed ours | **MIT**, "Copyright (c) 2026 Saurabh Chauhan" (LICENSE fetched from the repo) | import allowed with the licence header and a `components/ui/SOURCES.md` row. **Retime to our tokens**: beUI's sheet uses `duration 0.5`, and Dynamic Island uses `duration 0.8, bounce 0.2–0.35`, both over our 300 ms ceiling |
| [transitions.dev](https://transitions.dev) | ideas from the free set: Tabs sliding, Spinner to check morph, Error state shake, Skeleton loader and reveal, Thinking states, Streaming text, Toast open/close | [terms](https://transitions.dev/terms.html): "you may use it in unlimited personal and commercial projects, modify it freely". "The one thing you may not do is redistribute the library itself". MIT covers only their tooling (Refine, CLI), not the transitions. The terms carry no attribution clause for free transitions | the patterns here are **re-implemented, not copied**. If a transition is ever pasted, keep a `/* transitions.dev: <name> */` header (house rule, not a licence requirement), list it in SOURCES.md, and never vendor the collection |
| [Kinetics](https://kinetics.colorion.co) ([repo](https://github.com/ckissi/kinetics)) | spring **parameter ideas** only (see springs.md §6) | no LICENSE file in the repo, and `package.json` is `"private": true` with no `license` field. The site footer says "MIT licensed", but there is no licence text | **ideas only, no code**. Treat as all rights reserved until a LICENSE file appears |
| Apple HIG [Motion](https://developer.apple.com/design/human-interface-guidelines/motion), [Materials](https://developer.apple.com/design/human-interface-guidelines/materials) and WWDC25 [Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/) | principles, quoted below | guidance, no assets | quote and follow. Never copy Apple assets or SF Symbols into the web app |

## C. Apple quotes the principles rest on

From the HIG *Motion* page (fetched as JSON from `developer.apple.com/tutorials/data/design/human-interface-guidelines/motion.json`):
- "Add motion purposefully, supporting the experience without overshadowing it. Don't add motion for the sake of adding motion."
- "Make motion optional. … avoid using it as the only way to communicate important information."
- "Aim for brevity and precision in feedback animations."
- "In apps, generally avoid adding motion to UI interactions that occur frequently."
- "Let people cancel motion. As much as possible, don't make people wait for an animation to complete before they can do anything."
- "Avoid showing objects that oscillate in a sustained way … around 0.2 Hz" (visionOS, but it applies to our loops: the shimmer runs at about 0.6 Hz with low amplitude).

From the HIG *Materials* page:
- "Liquid Glass forms a distinct functional layer for controls and navigation elements … that floats above the content layer."
- "Don't use Liquid Glass in the content layer." / "Use Liquid Glass effects sparingly."
- Regular vs clear variants. A clear variant over bright content needs "a dark dimming layer of 35% opacity".

From WWDC25 *Meet Liquid Glass* (session 219 transcript):
- "Liquid Glass responds to interaction by instantly flexing and energizing with light." / "the material illuminates from within as a form of feedback."
- "Liquid Glass dynamically morphs between the controls in each context … a singular floating plane."
- "Instead of fading, Liquid Glass objects materialize in and out by gradually modulating the light bending and lensing."
- "When glass flexes and morphs to larger sizes … its material characteristics change to simulate a thicker, more substantial material."
- Scroll edge: "gently dissolves the content into the background". With pinned accessory views such as column headers, "a 'hard style' effect" is used instead.
- "Reduced Transparency makes Liquid Glass frostier … Increased contrast makes elements predominantly black or white … Reduced Motion decreases the intensity of some effects and disables any elastic properties for the material."

Platform support facts used:
- `prefers-reduced-transparency`: Chromium 118+, Firefox behind a flag, Safari not supported ([Chrome blog](https://developer.chrome.com/blog/css-prefers-reduced-transparency)). Hence the in-app `data-transparency="reduced"` switch.
- Next.js `experimental.viewTransition` is still experimental in v16 ([docs](https://nextjs.org/docs/app/api-reference/config/next-config-js/viewTransition)). Hence enter-only route transitions.
- Backdrop root: an ancestor with `opacity` < 1, `filter`, `mask`, `clip-path`, `backdrop-filter`, `mix-blend-mode` or a `will-change` on one of these makes `backdrop-filter` inside it sample only that ancestor's content. Verified in Chromium 141 (see patterns.md §13).
