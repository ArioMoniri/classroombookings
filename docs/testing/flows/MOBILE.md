# Mobile acceptance criteria (390×844 and 768×1024)

Owner decision (ROADMAP "Standing flow loop"): mobile is part of the definition of done for **every screen**. A screen passes when it meets M-01 … M-16 at **390×844** (phone, portrait) and **768×1024** (tablet, portrait), plus M-13 in landscape (844×390). The builders work against this file, and the testers check it.

How to run:
- Contexts as in README §3: `isMobile: true`, `hasTouch: true`, `locale: "tr-TR"`, `timezoneId: "Europe/Istanbul"`, built with `scripts/record/lib/touch.mjs` (`newFlowPage`). Call `assertTouch(page)` before every M-02, M-03 and M-05 run, and take full-page screenshots only with its `shot()`: a plain `page.screenshot({ fullPage: true })` switches touch emulation off for the rest of the page, so every later measurement reads the mouse sizes (32 px controls, 13–14 px inputs). That is what round 1 measured (T-R1-45).
- Run every criterion on every route of the matrix (§3) that the flow reaches. Also run it with the screen's main **sheet or dialog open**, and with the **filters open** where a screen has filters.
- Report one row per criterion × route × viewport (`step` = `M-02@/find-room`). Attach the JSON the assertion returns.
- The snippets below run in `page.evaluate` (Playwright library). `expect` is any assertion of your choice: the test runner's `expect` or `node:assert`.
- **Zoom pre-check, first on every route.** With `isMobile: true`, Chromium zooms the page out when content is wider than the screen. `innerWidth` and `innerHeight` then grow (a 600 px element at 390 gave `innerHeight` 1316 in the dry run of these snippets), and every later measurement is skewed. Check `await page.evaluate(() => [innerWidth, document.documentElement.clientWidth])`. If the two differ, M-01 has already failed: report it and take the other numbers with care. The snippets use `document.documentElement.clientWidth / clientHeight` (the layout viewport) for this reason.
- The snippets were dry-run on Chromium 141 (`chromium-1194`) against a synthetic page on 2026-10-15. `Emulation.setSafeAreaInsetsOverride` is supported there. `hasTouch` is what makes `(pointer: coarse)` and `(hover: none)` match. `Emulation.setEmulatedMedia` with `pointer` / `hover` features has no effect in this build (re-measured on 2026-10-16), so it is not a fallback.

Sources: the UI/UX visual review (§2 control heights, §3 per-screen, §5 acceptance checks), persona reports U-16, A-27, M-43, the phase19 specs (§6 mobile layouts) and the motion audit (§1 probe).

---

## 1. Criteria

### M-01 · No horizontal page scroll

The page never scrolls sideways, and nothing pokes out of the viewport unless it sits inside its own horizontal scroller.

```js
const m01 = await page.evaluate(() => {
  const vw = document.documentElement.clientWidth, off = [];
  window.scrollTo(10000, window.scrollY);
  const scrolledX = window.scrollX; window.scrollTo(0, window.scrollY);
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || cs.position === "fixed") continue;
    if (r.right <= vw + 1 && r.left >= -1) continue;
    let p = el.parentElement, contained = false;
    while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o !== "visible") { contained = true; break; } p = p.parentElement; }
    if (!contained) off.push(`${el.tagName}${el.dataset.testid ? `[${el.dataset.testid}]` : ""} ${Math.round(r.left)}→${Math.round(r.right)}`);
  }
  return { scrollWidth: document.scrollingElement.scrollWidth, vw, scrolledX, offenders: off.slice(0, 15) };
});
// PASS: m01.scrollWidth <= m01.vw && m01.scrolledX === 0 && m01.offenders.length === 0
```
- `overflow-x: hidden` on `html` or `body` does not hide a failure: the offender list still catches clipped content.
- Seen before: M-43 (admin screens), `/admin/rooms` overflow (UI review).

### M-02 · Touch targets ≥ 44 × 44 px

Every visible interactive element is at least 44 × 44 CSS px, or has a hit area that large.

```js
const m02 = await page.evaluate(() => {
  const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
  const hits = (el, x, y) => { const t = document.elementFromPoint(x, y); return t && (t === el || el.contains(t)); };
  const bad = [];
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
    if (el.checkVisibility && !el.checkVisibility()) continue;                 // inside a closed <details> or display:none ancestor: not drawn (lane A, round 1)
    if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;   // sr-only until focused: the "İçeriğe atla" skip link (1×1)
    if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue; // links inside running text
    let w = r.width, h = r.height;
    const lab = el.labels?.[0]; if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
    if (w >= 44 && h >= 44) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;               // a pseudo-element may extend the hit area
    const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
    const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
    if (inView && [[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x, y))) continue;
    bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
  }
  return bad;
});
// PASS: m02.length === 0
```
- The hit-area probe only works for elements in the viewport. Scroll each screen in steps of `0.8 × clientHeight` and repeat.
- The skip link "İçeriğe atla" is `sr-only` (1 × 1 px) until it gets focus, so the snippet skips 1 × 1 elements that are not focused (round 1 listed it on every route, R1-A-02). It is a keyboard control, not a touch target: check it once by keyboard instead (F-13), where the first Tab from the top of the page focuses it and it becomes visible.
- Run `assertTouch(page)` (README §3, `scripts/record/lib/touch.mjs`) before the snippet. A reading taken with touch emulation off shows the mouse sizes (32 px controls), not what a phone gets.
- Seen before: U-16 (28 px toolbar), UI review §2 "85–97 % of admin controls under 44 px at 390".

### M-03 · Text ≥ 11 px (inputs ≥ 16 px on phone)

No visible text is under 11 px. On phone, text inputs use ≥ 16 px, so focusing them does not zoom the page (iOS).

```js
const m03 = await page.evaluate(() => {
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue.trim() ? 1 : 2) });
  const small = new Map();
  while (tw.nextNode()) {
    const el = tw.currentNode.parentElement, cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (!r.width || r.width <= 1 || cs.visibility === "hidden" || el.closest(".sr-only,[data-allow-small-text]")) continue;
    const px = parseFloat(cs.fontSize); if (px < 11) small.set(el, px);
  }
  const inputs = [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea')]
    .filter((i) => i.getBoundingClientRect().width > 1 && !i.closest(".sr-only") && (!i.checkVisibility || i.checkVisibility()) && parseFloat(getComputedStyle(i).fontSize) < 16) // a visually hidden file input behind a styled button is not typed into
    .map((i) => i.name || i.id || i.dataset.testid);
  return { small: [...small].slice(0, 20).map(([el, px]) => ({ text: el.textContent.trim().slice(0, 30), px })), inputsUnder16: inputs };
});
// PASS: m03.small.length === 0  (both viewports)  &&  m03.inputsUnder16.length === 0  (phone)
```
- The UI review allows **one** exception: `text-2xs` (10 px) in the week-zoom timetable on desktop only. Mark it with `data-allow-small-text`.

### M-04 · Dialogs and filters are bottom sheets on phone

On phone, every dialog, sheet, popover form and filter panel opens anchored to the bottom, full width, no taller than the screen, scrolling inside itself. It can be dismissed (a ≥ 44 px close button, Escape, or a drag down where offered).

```js
const vp = page.viewportSize();
const sheet = page.locator('[role="dialog"]:visible, [role="alertdialog"]:visible').last();
const b = await sheet.boundingBox();
// the content fits, or the sheet itself or an element inside it scrolls (a phone Dialog scrolls itself: overflow-y on the popup)
const inner = await sheet.evaluate((el) => ({ scrollable: el.scrollHeight <= el.clientHeight + 1 || [el, ...el.querySelectorAll("*")].some((c) => /(auto|scroll)/.test(getComputedStyle(c).overflowY) && c.scrollHeight > c.clientHeight + 1) }));
// PASS on phone: Math.abs(b.y + b.height - vp.height) <= 2 && b.width >= vp.width - 2 && b.height <= vp.height && inner.scrollable
// PASS on tablet: as phone, OR a centred dialog/side sheet with width between 360 and 640 and height <= vp.height
await page.keyboard.press("Escape");  // closes it; focus returns to the trigger (README §4.7)
```
- **Filters** count too. A screen with filters (Find a room, the booking toolbar, Moderasyon chips, Classes, Audit) shows one trigger such as "Filtreler · 2" that opens such a sheet. The phone page never starts with ~300 px of controls before the content (UI review: Bookings 390).
- Seen before: UI review "Bookings 390", phase19 specs §6.

### M-05 · The primary action is sticky and within thumb reach

The screen's primary action (named per route in §3) stays visible while the content scrolls, inside the **bottom 40 %** of the viewport, and is not covered.

```js
const btn = page.locator(PRIMARY);              // from the route matrix
const vp = page.viewportSize();
const scrollers = async (y) => page.evaluate((y) => { window.scrollTo(0, y); document.querySelectorAll("main, [role=dialog] *").forEach((e) => { if (e.scrollHeight > e.clientHeight + 4) e.scrollTop = y; }); }, y);
const out = [];
for (const y of [0, 400, 1e6]) {
  await scrollers(y); await page.waitForTimeout(150);
  const b = await btn.boundingBox();
  const free = b && await btn.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === el || el.contains(t); });
  out.push({ y, top: b?.y, bottom: b && b.y + b.height, free });
}
// PASS: every row has top >= 0.6 * vp.height - 1, bottom <= vp.height, free === true
```
- A screen whose content fits without scrolling passes if the button is in the bottom 40 % and free.
- Inside a sheet, the primary action sits in the sheet's footer (e.g. "Talep et", "Kaydet", "Ara", "Onayla ve yayınla").
- A **disabled** primary reads as covered in the snippet (`elementFromPoint` passes through `pointer-events: none` to what lies under it). Check `getComputedStyle(el).pointerEvents` / `el.disabled` before calling it a cover (mobile-b 2026-10-17 §7).
- A primary that appears only once the form is dirty (`/admin/settings` `org-save`) is the intended pattern: make one change, then probe.

### M-06 · Safe-area insets

Content and bars respect the device notch and home indicator.

1. Static: `document.querySelector('meta[name=viewport]').content` contains **`viewport-fit=cover`**. Without it, `env(safe-area-inset-*)` is 0 on iOS and every inset rule is dead. On `b75047b` the Next `viewport` export has no `viewportFit`: expect a FAIL until it is added.
2. Dynamic, where this Chromium supports it:
   ```js
   const cdp = await page.context().newCDPSession(page);
   let emulated = true;
   try { await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets: { top: 47, topMax: 47, bottom: 34, bottomMax: 34, left: 0, leftMax: 0, right: 0, rightMax: 0 } }); }
   catch { emulated = false; }   // older Chromium: report the dynamic part SKIP, keep the static check
   await page.reload();
   const m06 = await page.evaluate(() => {
     const tab = document.querySelector('nav[aria-label="Sekmeler"]')?.getBoundingClientRect();
     const top = document.querySelector("header")?.getBoundingClientRect();
     const main = document.getElementById("main");
     return { tabBottomGap: tab ? document.documentElement.clientHeight - tab.bottom : null, headerContentTop: top ? top.top : null,
              mainPadBottom: main ? parseFloat(getComputedStyle(main).paddingBottom) : null, tabH: tab?.height };
   });
   // PASS (emulated): tabBottomGap >= 34 && mainPadBottom >= tabH + 34 + 16 (content clears the tab bar, UI review "Dashboard 390")
   ```
   Floating capsules (commit bar, "Onayla ve yayınla", Studio bottom bar, the undo toast) also end ≥ 34 px above the bottom edge.

### M-07 · Tables become card lists, or scroll horizontally with a pinned first column

At 390 every data table is either replaced by a card list, or sits in its own horizontal scroller with the first (identifying) column `position: sticky`. At 768 a table may stay a table if it fits without clipping.

```js
const m07 = await page.evaluate(() => [...document.querySelectorAll('table, [role="table"], [role="grid"]')].filter((t) => t.getBoundingClientRect().width).map((t) => {
  let p = t.parentElement, scroller = null;
  while (p && p !== document.body) { if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) { scroller = p; break; } p = p.parentElement; }
  const first = t.querySelector('tbody tr > :first-child, [role="row"]:nth-of-type(2) > :first-child');
  return { id: t.dataset.testid || t.getAttribute("aria-label") || t.tagName,
           fits: t.getBoundingClientRect().width <= document.documentElement.clientWidth + 1,
           scroller: !!scroller, stickyFirst: !!first && getComputedStyle(first).position === "sticky" };
}));
// PASS per table: fits (768 only) || (scroller && stickyFirst)   — and at 390 a card list is the preferred form
```
- Then scroll the scroller right by 200 px. The first column's `left` must not change.
- Card lists: one card per row, the identifying value on line 1 and the status (glyph + word) visible without expanding.
- The timetable and the booking grid are covered by M-08, not here.

### M-08 · The timetable switches to a day / agenda view; the booking grid to a slot list

- `/timetable` at 390 shows `[data-testid=calendar-mobile]`, `[data-testid=day-timeline]` or `[data-testid=agenda]`. `[data-testid=time-grid]` is not visible, or shows a single day.
- `/bookings` at 390 opens on the free-slot list (`[data-testid=free-slots]`), or on one room's day. Never the multi-room 18-period grid as the first view.
- At 768: a day or 3-day view, or one building's week, with chips ≥ 72 px wide.
```js
const m08 = await page.evaluate(() => ({
  mobileView: !!document.querySelector('[data-testid="calendar-mobile"],[data-testid="day-timeline"],[data-testid="agenda"],[data-testid="free-slots"]'),
  weekGridVisible: [...document.querySelectorAll('[data-testid="time-grid"],[data-testid="booking-grid"]')].some((g) => g.getBoundingClientRect().width > document.documentElement.clientWidth * 0.95 && g.querySelectorAll('[role="columnheader"]').length > 3),
  chipMin: Math.min(...[...document.querySelectorAll('[data-testid="calendar-event"]')].map((c) => c.getBoundingClientRect().width).filter(Boolean), 9999),
}));
// PASS 390: mobileView && !weekGridVisible ; PASS 768: chipMin >= 72
```
- Course codes in chips are never truncated (the name truncates first).

### M-09 · A tab bar with labels

On phone and tablet the primary navigation is a bottom tab bar (`nav[aria-label="Sekmeler"]`) with 3–5 items. Every item shows a **text label** (not only an icon). The active item has `aria-current="page"`. A count badge comes **after** the label in the accessible name. The set of items is the same before and after hydration, and fits the role.

```js
const tabs = page.locator('nav[aria-label="Sekmeler"] a, nav[aria-label="Sekmeler"] button');
const first = await tabs.evaluateAll((els) => els.map((e) => ({ text: e.innerText.trim(), name: e.getAttribute("aria-label") || e.innerText.trim(), current: e.getAttribute("aria-current"), h: e.getBoundingClientRect().height, fs: parseFloat(getComputedStyle(e).fontSize) })));
await page.waitForTimeout(2000);
const later = await tabs.evaluateAll((els) => els.map((e) => e.innerText.trim()));
// PASS: 3 <= first.length <= 5 (+ the search button), every text non-empty and fully visible (no ellipsis), every h >= 44, fs >= 11,
//       exactly one current === "page" on a top-level route, first.map(t => t.text) equals later
```
- The labels are not clipped in TR or EN. The badge is readable (UI review: an illegible "99+").
- **Role fit:** a teacher's tab bar has no "Çizelge" leading to a no-access page (persona-user Enh. #11, A-01).
- At 768 a labelled rail on the side is an acceptable alternative.

### M-10 · Forms in one column

At 390 the fields of a form or sheet stack in one column, with labels above the fields. At 768, at most two columns, each field ≥ 280 px.

```js
const m10 = await page.locator("form:visible, [role=dialog]:visible").first().evaluate((f) => {
  const fields = [...f.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea')].filter((i) => i.getBoundingClientRect().width);
  const fr = f.getBoundingClientRect();
  return { lefts: [...new Set(fields.map((i) => Math.round(i.getBoundingClientRect().left)))],
           narrow: fields.filter((i) => i.getBoundingClientRect().width < fr.width * 0.85).map((i) => i.name || i.id),
           labelsBeside: fields.filter((i) => { const l = i.labels?.[0]?.getBoundingClientRect(); return l && l.bottom > i.getBoundingClientRect().top + 2 && l.right <= i.getBoundingClientRect().left; }).length };
});
// PASS 390: (m10.lefts.length === 1 || m10.narrow.length === 0) && m10.labelsBeside === 0
```
- Short paired fields (start / end time, min / max) may share a row if each is ≥ 140 px. Record them as an exception.

### M-11 · No hover-only affordances

Nothing a touch user needs is reachable only by hovering: no actions revealed on hover, no information only in a `title` or hover tooltip.

```js
const m11 = await page.evaluate(() => ({
  hiddenControls: [...document.querySelectorAll('button,a[href],[role=button],[role=menuitem]')].filter((el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return r.width > 0 && (parseFloat(cs.opacity) < 0.1 || cs.visibility === "hidden") && !el.closest('[aria-hidden="true"],[inert],[hidden],[data-state="closed"]');
  }).map((el) => el.dataset.testid || el.getAttribute("aria-label") || el.textContent.trim().slice(0, 30)),
  titleOnly: [...document.querySelectorAll("[title]")].filter((el) => el.getAttribute("title").trim() && !el.textContent.includes(el.getAttribute("title").trim()) && !el.getAttribute("aria-label")).length,
}));
// PASS (touch viewports, with hover:none emulated): m11.hiddenControls.length === 0 && m11.titleOnly === 0
```
- **Runtime rule:** every flow step on touch viewports uses `tap()` only. A step that cannot be completed without `hover()` FAILs this criterion.
- Long-press and swipe gestures are allowed only as shortcuts. The same action must have a visible button.
- Seen before: the booking grid's "+ Rezerve et" hover label (U-17 print leak), find-room fit text in tooltips, the roles' permission keys in a tooltip (fine on desktop, but the disabled reason must be visible text on touch).

### M-12 · The on-screen keyboard does not cover the focused field

When a text field is focused, it stays visible and uncovered with the keyboard open. The sheet's primary action stays reachable.

```js
const H = page.viewportSize().height, KB = 336;          // iOS portrait keyboard ≈ 336 px (tablet: use 400)
await field.tap();
await page.setViewportSize({ width: page.viewportSize().width, height: H - KB });   // proxy for resizes-content
await page.waitForTimeout(350);
const m12 = await field.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { top: r.top, bottom: r.bottom, vh: document.documentElement.clientHeight, uncovered: t === el || el.contains(t) }; });
const meta = await page.evaluate(() => document.querySelector("meta[name=viewport]")?.content ?? "");
await page.setViewportSize({ width: page.viewportSize().width, height: H });
// PASS: m12.top >= 0 && m12.bottom <= m12.vh && m12.uncovered — and the sheet's primary action is visible or one inner scroll away
```
- Shrinking the layout viewport imitates Android's `interactive-widget=resizes-content`. iOS resizes only the visual viewport, so also check that the app reacts to `visualViewport` (sheets use `dvh` or a `visualViewport` resize handler), or that the viewport meta sets `interactive-widget=resizes-content`. Report `meta` in the evidence.
- Test it on: the book sheet note, the reject reason text, the cancel "Gerekçe", the find-room headcount, the priority note, the reset reason, login and the password fields.

### M-13 · Landscape sanity (844×390)

Rotate the phone context (`viewport: { width: 844, height: 390 }`) on each route of the matrix, and re-check:
- M-01 (no horizontal scroll);
- M-04: a dialog's height is ≤ the viewport, and its body scrolls; header + footer take ≤ 50 % of the height;
- M-05: the primary action is visible;
- the tab bar and the top bar together take ≤ 25 % of the height (≤ 97 px), or hide while scrolling;
- the scrolling content area is ≥ 50 % of the height.
```js
const m13 = await page.evaluate(() => {
  // the tab bar's <nav> is static inside a fixed wrapper (shell/tab-bar.tsx): measure the positioned box that holds it,
  // from its top to the viewport bottom (the safe-area gap under the capsule counts too)
  const vh = document.documentElement.clientHeight;
  const fixedOf = (el) => { for (let p = el; p && p !== document.body; p = p.parentElement) if (/(fixed|sticky)/.test(getComputedStyle(p).position)) return p; return null; };
  const header = [...document.querySelectorAll("header")].map(fixedOf).find((h) => h && h.getBoundingClientRect().height);
  // tr "Sekmeler", en "Tabs"; a hidden bar (lg+, Studio / programme wizard) has an empty box and counts 0
  const nav = document.querySelector('nav[aria-label="Sekmeler"], nav[aria-label="Tabs"]');
  const navBox = nav?.getBoundingClientRect(); const tabs = nav && navBox.height > 0 && fixedOf(nav);
  const parts = { header: header ? Math.max(0, Math.round(header.getBoundingClientRect().bottom)) : 0, tabs: tabs ? Math.round(vh - navBox.top) : 0 };
  return { ...parts, vh, ratio: +((parts.header + parts.tabs) / vh).toFixed(2) };
});
// PASS: m13.ratio <= 0.25 (with the page at rest and again after scrolling 300 px: a bar that scrolls away counts 0),
//       plus M-01 / M-04 / M-05 at this size
```
- Expected after mobile-a phase 2: the top bar is static at ≤ 500 px tall (0 once scrolled) and the tab bar is a 44 px
  compact capsule 8 px above the edge, so `m13.tabs` ≈ 52 and the ratio ≈ 0.13 at rest, 0.13 after scrolling.
- The earlier snippet read the tab bar's box even when it was hidden (`display: none` at lg+ gives top 0, so `tabs`
  became the full height) and only matched the Turkish label; both are fixed above.
- Round 3 and earlier used a filter on `position !== "static"` that dropped the tab bar (its `nav` is static inside the
  fixed wrapper), so every route read ~0.12 when header + tab bar were really 104 / 390 = 0.27 (mobile audit A,
  docs/testing/mobile/2026-10-17-mobile-a.md §6).

### M-14 · Performance: no long task over 200 ms on a tap

Each tap a flow makes on a touch viewport produces no long animation frame (LoAF) over **200 ms**. The probe is the `measure.mjs` method of the motion audit (rAF frame counter + `long-animation-frame` observer), in-page:

```js
const probeStart = () => { const st = { deltas: [], loaf: [], stop: false }; window.__mf = st; let last = performance.now();
  const tick = (t) => { st.deltas.push(t - last); last = t; if (!st.stop) requestAnimationFrame(tick); }; requestAnimationFrame(tick);
  const type = PerformanceObserver.supportedEntryTypes.includes("long-animation-frame") ? "long-animation-frame" : "longtask";
  st.po = new PerformanceObserver((l) => { for (const e of l.getEntries()) st.loaf.push(Math.round(e.duration)); }); st.po.observe({ type, buffered: false }); };
const probeStop = () => { const s = window.__mf; s.stop = true; s.po.disconnect(); const d = s.deltas.slice(1), sorted = [...d].sort((a, b) => a - b);
  const budget = sorted[Math.floor(sorted.length / 2)] ?? 16.7;
  return { frames: d.length, dropped: d.reduce((n, x) => n + Math.max(0, Math.round(x / budget) - 1), 0), worstLoaf: Math.max(0, ...s.loaf), loafOver200: s.loaf.filter((x) => x > 200).length }; };
// in-page helpers from the motion audit, used by F-13 Part B
const overCeiling = () => document.getAnimations().map((a) => ({ a, t: a.effect?.getComputedTiming() })).filter(({ t }) => t && t.iterations !== Infinity && Number(t.duration) + Number(t.delay ?? 0) > 300).map(({ a, t }) => `${a.animationName ?? a.transitionProperty ?? "anim"}:${Math.round(Number(t.duration))}ms`);
const moving = () => document.getAnimations().filter((a) => (a.effect?.getKeyframes?.() ?? []).some((k) => "transform" in k || "translate" in k || "scale" in k)).map((a) => a.animationName ?? a.transitionProperty ?? "waapi");

// per tap:
await page.evaluate(probeStart);
await target.tap();
await page.waitForTimeout(700);
const m14 = await page.evaluate(probeStop);
// PASS: m14.worstLoaf <= 200   (report m14.dropped too; the CI gate is <= 3 dropped frames per interaction)
```
- **Baseline first:** 4 taps on the page `h1`, the same way. If the baseline drops more than 1 frame per tap, or the load average exceeds the cores, the timing rows are `INCONCLUSIVE` (README §8).
- Run at 1× CPU. Repeat at 4× (`cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 })`) as advisory information for phones. Only the 1× result decides PASS/FAIL on this shared host.
- The taps to measure, per flow, are the ones marked "probe" or listed in F-13 B04: open a sheet, submit, next day, search, approve, expand a row, open the bell.

### M-15 · Layout stability: CLS ≤ 0.1 on load

The page does not jump while it loads: a skeleton holds the space of what is coming (one line of spinner that gives way
to a 700 px form is the classic failure). Measured with a `layout-shift` observer installed **before** the page's own
scripts (`page.addInitScript`), then the web.dev session-window sum (gap < 1 s, window ≤ 5 s):

```js
await page.addInitScript(() => { window.__ls = []; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__ls.push({ v: e.value, t: e.startTime, src: (e.sources || []).map((s) => s.node?.nodeName) }); }).observe({ type: "layout-shift", buffered: true }); });
// … goto the route, wait for its main test id, then 1.5 s …
const m15 = await page.evaluate(() => { let best = 0, cur = 0, start = -1, prev = -1;
  for (const e of window.__ls) { if (prev >= 0 && e.t - prev < 1000 && e.t - start < 5000) cur += e.v; else { cur = e.v; start = e.t; } prev = e.t; best = Math.max(best, cur); }
  return { cls: +best.toFixed(3), shifts: window.__ls.length }; });
// PASS: m15.cls <= 0.1   (web.dev: good ≤ 0.1, poor > 0.25). Report the shifted nodes (e.sources) with a FAIL.
```
- Load-independent: CLS is a layout measure, so it decides PASS/FAIL even on a busy host.
- Seen before: /profile 0.45 (phone) / 0.73 (tablet), /public/buildings/A 0.77, /bookings at 768 0.28 (mobile audit A).

### M-16 · Responsiveness: INP ≤ 200 ms on the tap that opens a sheet

The tap that opens the screen's main sheet or dialog (book sheet, filters, bell, recurring) answers within 200 ms, from
the touch to the next paint (Interaction to Next Paint). Event-timing entries carry the interaction id; the longest
entry of the tap is its INP:

```js
await page.addInitScript(() => { window.__ev = []; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (e.interactionId) window.__ev.push({ id: e.interactionId, d: e.duration, delay: e.processingStart - e.startTime, proc: e.processingEnd - e.processingStart }); }).observe({ type: "event", durationThreshold: 16, buffered: true }); });
await page.evaluate(() => { window.__ev = []; });
await opener.tap();
await page.waitForTimeout(800);
const m16 = await page.evaluate(() => { const w = window.__ev.sort((a, b) => b.d - a.d)[0]; return w ? { inp: Math.round(w.d), inputDelay: Math.round(w.delay), processing: Math.round(w.proc), presentation: Math.round(w.d - w.delay - w.proc) } : { inp: 0 }; });
// PASS: m16.inp <= 200   (web.dev: good ≤ 200 ms, poor > 500 ms). The split says where the time goes: a large
//       `presentation` is paint (blur, big DOM), a large `processing` is the click handler.
```
- Timing row: run the M-14 baseline first; under load (README §8) the row is INCONCLUSIVE, not FAIL.

---

## 2. What changes between 390 and 768

| Criterion | 390×844 phone | 768×1024 tablet |
|---|---|---|
| M-01, M-02, M-03 (11 px), M-06, M-11, M-14, M-15, M-16 | required | required (touch) |
| M-03 inputs ≥ 16 px | required | recommended |
| M-04 dialogs | bottom sheet | bottom sheet, or a centred dialog / side sheet 360–640 px wide |
| M-05 primary action | sticky, bottom 40 % | sticky and visible; position free |
| M-07 tables | card list, or scroll + pinned first column | a table if nothing is clipped, else as phone |
| M-08 timetable / booking grid | day / agenda / slot list | day, 3-day or one building's week; chips ≥ 72 px |
| M-09 navigation | bottom tab bar with labels | tab bar or a labelled rail |
| M-10 forms | one column | ≤ 2 columns, each field ≥ 280 px |
| M-12 keyboard height | 336 px | 400 px |
| M-13 landscape | 844×390 | 1024×768 (sanity only: M-01, M-04) |

---

## 3. Route matrix (what "primary action" means per screen)

`PRIMARY` is the locator M-05 uses. "Cards" means the expected M-07 form at 390. Persona: who reaches the screen in the flows.

| Route | Persona | Primary action (`PRIMARY`) | Tables → expected at 390 | Flows |
|---|---|---|---|---|
| `/login` | all | `getByTestId("login-submit")`; with SSO on, open `login-disclosure` first. The card is shorter than the screen and the submit sits right under the password (y ≈ 355–403 at 390): M-05 passes when it is visible with the keyboard open (M-12); the bottom-40 % rule does not apply to this centred form (round 2 R2-S-20) | – | F-12 |
| `/login/change-password` | all | button "Kaydet ve devam et" | – | F-12 |
| `/reset-password` | all | the submit of the visible form | – | F-12 |
| `/bookings` | staff, academician, admin | in the open sheet: `getByTestId("book-submit")`; page: none (slot list) | grid → slot list (M-08) | F-01, F-02, F-13 |
| `/my-bookings` | staff, academician | selection mode: `getByTestId("cancel-selected")`; inline "Takvime eşitle" card (`calendar-sync`, no opener here): `sync-create`, then the consent step's "Rıza ver ve devam et" | rows → cards | F-01, F-04 |
| `/find-room` | staff, academician | `getByTestId("fr-search")`; results: `fr-reserve-<code>` | results → cards | F-03 |
| `/approvals` | admin | drawer: `approval-approve` / `approval-group-approve` | list → cards | F-01 |
| `/profile` | all | `getByTestId("profile-save")` | – | F-12, F-13 |
| `/settings` (`?tab=<name>`: `tab-<name>`) | all; admin for the AI policy and the solver tab | per tab, inside the open panel: integrations `calendar-confirm` (only while calendar sync is on; with `REC_CAL_SIGNOFF=0` there is none: NOT APPLICABLE) / `?tab=ai` (admin): `save-key` while a key is typed, else `save-model` (both in the page-actions capsule), the AI policy confirm `ai-policy-confirm` inside its dialog; `?tab=solver` (admin, T-R2-29): `save-solver`; appearance / profile tabs: the tab's save; `?tab=general` (admin, F-RF2-1 2026-10-18): the tab stacks cards that save on their own, so make one change in a card first, then probe that card's save (`mail-notices-save` after editing the hours, `security-contact-save` after editing a field): a changed card's save is the page-actions capsule above the tab bar (two changed cards stack). Open the tab before probing: the save lives inside the panel, not on the page (round 2's `M-05@/admin/settings` NOT RUN) | solver weights table → one column, inputs ≥ 16 px | F-11, F-13, F-04 S02 |
| `/dashboard` | admin | none (read) | KPI rows wrap; charts readable; odometer digits not in the accessible text (R2-S-14) | F-12, F-05 S15 |
| `/analytics/heatmap` | admin, planner | none (read); the controls (`heat-controls`: run / week / grouping selects) ≥ 44 px | heat grid scrolls inside itself (`rooms-heat`, `instructors-heat`), the page never scrolls sideways; legend readable | F-05 S15, T-R1-01 |
| `/runs/compare?a=&b=` | admin, planner | `getByTestId("compare-apply")` in the run pair picker (`compare-pick-a` / `compare-pick-b`); once a new pair is picked it floats in the page-actions capsule below lg (`[data-slot=page-actions][data-floating]`); with the pair applied: none (read) | metric tables → cards or a pinned first column; the changed-rooms list → cards | R1-M-10 (week vs term comparison), sanity pass once per round |
| `/timetable` | admin, planner | inspector: "Taşı…"; move sheet: `move-confirm`; Escape / close returns focus to the class chip (`calendar-event[data-assignment-id]`), never `<body>` | week grid → day / agenda (M-08); at 768 the M-08 ids include the board ("Pano") view | F-10 |
| `/classes`, `/requests` | admin | bulk bar action when selected | table → cards or pinned "Ders" column | F-09 |
| `/rooms`, `/rooms/[id]` | admin | none (read) | cards or table with pinned code | F-11 |
| `/runs`, `/runs/[id]` | admin | `getByTestId("run-publish")`: a capsule (`run-publish-row`) above the tab bar below `sm`, and below `lg` on a coarse pointer (768 tablet); an already published run has none (probe an unpublished one) | runs list → cards | F-09 |
| `/generate` | admin, planner | `studio-bottom-bar` primary ("Devam" / "Oluştur") | class table → cards | F-09, F-06 |
| `/onboarding` (+ job steps: `/onboarding?job=<id>` on `deb38315`; `/onboarding/<id>` once T-R2-20 lands, then both) | admin | drop zone button; job: `getByTestId("onboarding-commit-capsule-button")` (the commit capsule "Kaydet"; `onboarding-commit-button` is the in-flow one and fails M-05 by design) | files and review → cards | F-08 |
| `/moderation` | academician (Taleplerim), admin | coordinator: `recreate-open` (in the page-actions capsule below lg; only with a published run); academician: none | tabs' tables → cards | F-05 |
| `/moderation/people/[id]` | academician, admin | none; Öneriler: `suggestion-accept` | timeline → grouped list | F-05, F-06 |
| `/moderation/recreate/[id]` | admin | `getByTestId("preview-publish")` | diff → grouped list | F-05, F-07 |
| `/moderation/learning` | admin, planner (forbidden view) | `reset-confirm` in the open dialog | resets → cards | F-06 |
| `/programs/new` | admin | landing: `draft-resume` ("Son taslağa devam et", capsule) when drafts exist, else `wizard-start` (capsule); in a draft "Devam ›" in the floating capsule; last step "Oluştur ve çöz" | course / section grids → cards | F-07 |
| `/admin/users` | admin, limited admin | `users-new`; dialog: `user-save` | users table → cards | F-11 |
| `/admin/roles` | admin, limited admin | `role-save` | permission groups → sections | F-11 |
| `/admin/rooms` (+ Özellikler) | admin | opens on "Gruplar": `group-new` ("Yeni grup", in the capsule); "Salonlar" tab: `room-new`; dialog: `room-create` / `room-save`; features: `feature-save` | rooms, features → cards | F-11, F-03 |
| `/admin/approval-rules` | admin | `rule-new`; form: `rule-save` | rules → cards | F-01, F-11 |
| `/admin/audit` | admin | row "Geri al" | events → cards | F-02, F-11 |
| `/admin/settings`, `/admin/email`, `/admin/authentication` | admin | `org-save` (in the sticky capsule) / the form's save; `/admin/authentication`: "Bağlantıyı dene" is disabled until the test user and password are typed | – | F-01, F-11, F-12 |
| `/admin/holidays`, `/admin/sessions`, `/admin/weeks`, `/admin/schedules`, `/admin/departments`, `/admin/access`, `/admin/conflicts` | admin | the screen's "Yeni …" / save | lists → cards | sanity pass once per round |
| `/exams/invigilation` | planner, admin | `getByTestId("invig-new")` ("Yeni plan"); empty plan: `invig-pool-all` ("Tüm eğitmenlerle yeniden çalıştır") | posts → cards | R1-S-14 (T-R1-42) |
| `/setup` (fresh stack) | first admin | `setup-requirements-next` / the step's submit | – | F-12 (installer copy) |
| 404 (`/yok-boyle-sayfa`) | all | `not-found-home` | – | F-13 |

A route not in this table (a new screen) inherits M-01…M-14. Its builder adds a row here in the same commit (docs/testing/flows is test-planner territory; the builder proposes the row in its hand-off, and the suggester merges it).

---

## 4. Reporting

- One row per criterion × route × viewport (README §6). Example: `| F-03 | M-05@/find-room | staff | phone | FAIL | perf/… | FL-03-007 |`.
- Severity: a failed M-01, M-02, M-05 or M-12 on a flow's primary screen is **major**. M-03, M-06, M-07, M-09, M-10 and M-13 are **minor**, unless they make a step impossible (then major). A failed M-11 that blocks a step on touch is **major**. M-14 over 200 ms is **minor**, or **INCONCLUSIVE** under load. M-15 over 0.25 on a flow's primary screen is **major**, between 0.1 and 0.25 **minor**. M-16 over 200 ms is **minor** (over 500 ms **major**), or **INCONCLUSIVE** under load.
- Attach the snippet's JSON output. For M-02, the first 10 offenders with their sizes are enough.
