import { inflateRawSync } from "node:zlib";
import { readFileSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * Calendar, all classes and rooms against the REAL backend (no mock): FastAPI with the Bahar workbooks
 * imported (docs/testing/2026-10-08-real-backend-e2e.md), run #1 = the imported weekly board, run #5 = a
 * solver run for the whole term. Start the frontend with NEXT_PUBLIC_API_MOCK=0 and NEXT_PUBLIC_API_URL
 * pointing at the backend, then:
 *
 *   E2E_CALENDAR=1 PW_PORT=3700 npx playwright test e2e/calendar.spec.ts
 *
 * (E2E_REAL=1 also enables it once playwright.config.ts includes this file in its real-backend testMatch.)
 * Covers: the shell's URL contract (/timetable?run&week, ?subject=instructor:<id>, /requests?q=,
 * /requests?program_id=), the six lenses, inspector + explain, move dialog with the free-room finder and
 * undo (restores the backend state), /classes export with the "SmartSched Derslik" column, rooms list and
 * detail, and the motion audit for the calendar (.claude/skills/motion_designer/references/audit.md).
 */
const ON = process.env.E2E_CALENDAR === "1" || process.env.E2E_REAL === "1";
test.skip(!ON, "real-backend spec: set E2E_CALENDAR=1 and start the backend + a non-mock frontend");

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!";
const BOARD_RUN = Number(process.env.E2E_BOARD_RUN ?? 1);
const SOLVER_RUN = Number(process.env.E2E_SOLVER_RUN ?? 5);
const ROOM_CODE = process.env.E2E_ROOM ?? "A 204";

type Index = {
  run: { id: number; term_id: number };
  rooms: { id: number; name: string; capacity: number }[];
  assignments: { id: number; mr?: number | null; code?: string | null; label: string; prog_id?: number | null; instr_ids: number[]; weeks: number[]; rooms: number[]; day: number; sp: number; ep: number }[];
};

test.use({ locale: "en-GB", timezoneId: "Europe/Istanbul", viewport: { width: 1440, height: 900 } });

async function login(page: Page) {
  const base = test.info().project.use.baseURL ?? "http://127.0.0.1:3100";
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: "en", url: base }]);
  await page.goto("/login");
  await page.fill("#identifier", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

/** Same-origin API call through the Next proxy (the httpOnly cookie carries the JWT). */
async function api<T>(page: Page, path: string): Promise<T> {
  const res = await page.evaluate(async (url) => {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    return { status: r.status, body: (await r.json()) as unknown };
  }, `/api/v1${path}`);
  expect(res.status, `${path} → ${res.status}`).toBe(200);
  return res.body as T;
}

/** Header cells of the first sheet of an .xlsx (tiny zip reader: central directory + inflateRaw). */
function xlsxHeader(file: string): string[] {
  const buf = readFileSync(file);
  const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  const count = buf.readUInt16LE(eocd + 10);
  let p = buf.readUInt32LE(eocd + 16);
  const files = new Map<string, string>();
  for (let i = 0; i < count; i++) {
    const method = buf.readUInt16LE(p + 10);
    const size = buf.readUInt32LE(p + 20);
    const nameLen = buf.readUInt16LE(p + 28);
    const extra = buf.readUInt16LE(p + 30);
    const comment = buf.readUInt16LE(p + 32);
    const local = buf.readUInt32LE(p + 42);
    const name = buf.toString("utf8", p + 46, p + 46 + nameLen);
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const raw = buf.subarray(start, start + size);
    files.set(name, (method === 8 ? inflateRawSync(raw) : raw).toString("utf8"));
    p += 46 + nameLen + extra + comment;
  }
  const shared = [...(files.get("xl/sharedStrings.xml") ?? "").matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => [...m[1].matchAll(/<t[^>]*>([^<]*)<\/t>/g)].map((t) => t[1]).join(""));
  const sheet = files.get("xl/worksheets/sheet1.xml") ?? "";
  const row1 = /<row[^>]*r="1"[^>]*>([\s\S]*?)<\/row>/.exec(sheet)?.[1] ?? "";
  return [...row1.matchAll(/<c([^>]*)>([\s\S]*?)<\/c>/g)].map(([, attrs, body]) => {
    const v = /<v>([^<]*)<\/v>/.exec(body)?.[1] ?? /<t[^>]*>([^<]*)<\/t>/.exec(body)?.[1] ?? "";
    return /t="s"/.test(attrs) ? (shared[Number(v)] ?? "") : v;
  });
}

const lensTab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true });

test.describe("calendar on the real backend", () => {

  test("URL contract: run + week, six lenses, instructor subject", async ({ page }) => {
    test.setTimeout(180_000);
    await login(page);
    const idx = await api<Index>(page, `/runs/${BOARD_RUN}/calendar-index`);
    expect(idx.assignments.length, "the imported board has classes").toBeGreaterThan(1000);

    // run report "Çizelgede aç": /timetable?run=<id>&week=<n>
    await page.goto(`/timetable?run=${BOARD_RUN}&week=3`);
    await expect(page.getByTestId("calendar")).toBeVisible();
    await expect(page.getByTestId("week-label")).toContainText("3", { timeout: 30_000 });
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await expect(lensTab(page, "Board")).toHaveAttribute("aria-selected", "true");

    // the six lenses, each with its own canvas; the lens is URL state (Week/Day need a subject: a room here)
    const a204 = idx.rooms.find((r) => r.name === ROOM_CODE)?.id ?? idx.rooms[0].id;
    await page.goto(`/timetable?run=${BOARD_RUN}&week=3&subject=room:${a204}&lens=board`);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    const lenses: [string, string, string][] = [
      ["Week", "week", "time-grid"],
      ["Day", "day", "day-timeline"],
      ["Month", "month", "month-heat"],
      ["Term", "term", "term-heat"],
      ["Agenda", "agenda", "agenda"],
      ["Board", "board", "time-grid"],
    ];
    for (const [name, key, canvas] of lenses) {
      await lensTab(page, name).click();
      await expect(lensTab(page, name)).toHaveAttribute("aria-selected", "true");
      await expect(page.getByTestId(canvas).first()).toBeVisible({ timeout: 20_000 });
      if (key !== "board") await expect(page).toHaveURL(new RegExp(`lens=${key}`));
      await expect(page).toHaveURL(new RegExp(`run=${BOARD_RUN}(&|$)`));
      await expect(page).toHaveURL(/week=3(&|$)/);
    }
    // Term heat → a day cell drills down to Board · Day for that date
    await lensTab(page, "Term").click();
    await page.getByTestId("term-heat").locator('[role=gridcell][data-week="5"][data-day="2"]').click();
    await expect(lensTab(page, "Board")).toHaveAttribute("aria-selected", "true");
    await expect(page).toHaveURL(/week=5(&|$)/);
    await expect(page).toHaveURL(/day=2(&|$)/);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 20_000 });

    // ⌘K instructor result: /timetable?subject=instructor:<id> → that instructor's week
    const counts = new Map<number, number>();
    for (const a of idx.assignments) for (const i of a.instr_ids) counts.set(i, (counts.get(i) ?? 0) + 1);
    const [instructor] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    await page.goto(`/timetable?subject=instructor:${instructor}&run=${BOARD_RUN}`);
    await expect(lensTab(page, "Week")).toHaveAttribute("aria-selected", "true", { timeout: 30_000 });
    await expect(page.getByTestId("time-grid")).toBeVisible();
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
  });

  test("inspector, explain, move with the free-room finder, undo restores the backend", async ({ page }) => {
    test.setTimeout(180_000);
    await login(page);
    const before = await api<Index>(page, `/runs/${SOLVER_RUN}/calendar-index`);
    const room = before.rooms.find((r) => r.name === ROOM_CODE);
    expect(room, `${ROOM_CODE} exists`).toBeTruthy();
    const rid = room?.id ?? 0;

    await page.goto(`/timetable?run=${SOLVER_RUN}&week=3&lens=week&subject=room:${rid}`);
    const chips = page.locator(`[data-testid=calendar-event][data-room-id="${rid}"]`);
    await expect(chips.first()).toBeVisible({ timeout: 30_000 });
    const insp = page.getByTestId("class-inspector");
    const dialog = page.getByTestId("move-dialog");

    // the solver run keeps some real clashes (an instructor teaching two classes at once): those classes cannot
    // move without "force", so take the first class whose server dry run to a free room says it fits
    let aid = 0;
    let target = 0;
    const n = Math.min(8, await chips.count());
    for (let i = 0; i < n && !target; i++) {
      const chip = chips.nth(i);
      const id = Number(await chip.getAttribute("data-assignment-id"));
      await chip.click();
      await expect(insp).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`sel=${id}`));
      if (i === 0) {
        // inspector: when & where with the fit, status, why here, explain placement
        await expect(insp.getByTestId("inspector-room")).toContainText(ROOM_CODE);
        await expect(insp.getByTestId("inspector-fit")).toBeVisible();
        await expect(insp.getByTestId("inspector-status")).not.toBeEmpty();
        await insp.getByTestId("explain-placement").click();
        await expect(insp.getByTestId("explain-result")).toBeVisible({ timeout: 30_000 });
        await expect(insp.getByTestId("explain-result")).toContainText(/Source: (template|model)/);
      }
      await insp.getByTestId("inspector-move").click();
      await expect(dialog).toBeVisible();
      const free = dialog.locator(`[data-testid=free-room][data-status=free]:not([data-room-id="${rid}"])`).first();
      const found = await free.waitFor({ state: "visible", timeout: 15_000 }).then(() => true, () => false);
      if (!found) {
        await page.keyboard.press("Escape");
        continue;
      }
      const room2 = Number(await free.getAttribute("data-room-id"));
      const preview = page.waitForResponse((r) => r.url().includes(`/assignments/${id}/move-preview`) && (r.request().postData() ?? "").includes(`"room_ids":[${room2}]`), { timeout: 20_000 });
      await free.click();
      await expect(free).toHaveAttribute("aria-selected", "true");
      const body = (await (await preview).json()) as { items: { ok: boolean }[] };
      if (body.items[0]?.ok) {
        await expect(dialog.getByTestId("move-server-ok")).toBeVisible();
        aid = id;
        target = room2;
      } else {
        await expect(dialog.getByTestId("move-confirm")).toBeDisabled();
        await page.keyboard.press("Escape");
        await expect(dialog).toBeHidden();
      }
    }
    expect(target, "a class in this room that can move to a free room").toBeGreaterThan(0);
    const original = before.assignments.find((a) => a.id === aid);
    expect(original?.rooms).toContain(rid);
    await dialog.getByTestId("move-confirm").click();
    await expect(dialog).toBeHidden({ timeout: 20_000 });

    await expect
      .poll(async () => (await api<Index>(page, `/runs/${SOLVER_RUN}/calendar-index`)).assignments.find((a) => a.id === aid)?.rooms, { timeout: 20_000 })
      .toEqual([target]);
    // the class left this room's week
    await expect(page.locator(`[data-testid=calendar-event][data-assignment-id="${aid}"]`)).toHaveCount(0);

    // undo (toast action) puts it back on the server
    await page.locator("[data-sonner-toast]").getByRole("button", { name: "Undo" }).first().click();
    await expect
      .poll(async () => (await api<Index>(page, `/runs/${SOLVER_RUN}/calendar-index`)).assignments.find((a) => a.id === aid)?.rooms, { timeout: 20_000 })
      .toEqual(original?.rooms);
    await expect(page.locator(`[data-testid=calendar-event][data-assignment-id="${aid}"]`).first()).toBeVisible({ timeout: 20_000 });
  });

  test("all classes: /requests?q= and ?program_id= land on /classes, planning-list export has SmartSched Derslik", async ({ page }) => {
    test.setTimeout(180_000);
    await login(page);
    const idx = await api<Index>(page, `/runs/${BOARD_RUN}/calendar-index`);
    const sample = idx.assignments.find((a) => a.mr && a.code && a.prog_id);
    expect(sample).toBeTruthy();
    const code = sample?.code ?? "";

    // ⌘K course result
    await page.goto(`/requests?q=${encodeURIComponent(code)}`);
    await expect(page).toHaveURL(/\/classes\?.*q=/);
    await expect(page.getByTestId("classes")).toBeVisible();
    const rows = page.getByTestId("classes-row");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await expect(rows.first()).toContainText(code);

    // the inspector opens from a row and links back to the calendar (subject=room)
    await rows.first().click();
    const insp = page.getByTestId("class-inspector");
    await expect(insp).toBeVisible();
    const href = await insp.getByTestId("open-in-calendar").getAttribute("href");
    expect(href).toMatch(/^\/timetable\?lens=week/);

    // ⌘K programme result
    await page.goto(`/requests?program_id=${sample?.prog_id}`);
    await expect(page).toHaveURL(new RegExp(`/classes\\?.*program_id=${sample?.prog_id}`));
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });

    // planning-list export: the planner's own headers plus SmartSched Derslik right after Kesinleşen
    await page.goto("/classes?view=all");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("export-menu").click();
    const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60_000 }), page.getByTestId("export-planning-list").click()]);
    expect(download.suggestedFilename()).toMatch(/planlama-listesi\.xlsx$/);
    const path = await download.path();
    const header = xlsxHeader(path);
    const smart = header.indexOf("SmartSched Derslik");
    expect(smart, `header: ${header.join(" | ")}`).toBeGreaterThan(0);
    expect(header[smart - 1]).toMatch(/Kesinle/);
  });

  test("rooms: list with the week's occupancy, detail with grid, free slots and calendar link", async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    const rooms = await api<{ id: number; display_name: string }[]>(page, "/rooms");
    const room = rooms.find((r) => r.display_name === ROOM_CODE) ?? rooms[0];

    await page.goto("/rooms");
    await expect(page.getByTestId("rooms")).toBeVisible();
    await expect(page.getByTestId("room-card")).toHaveCount(rooms.length, { timeout: 30_000 });
    await expect(page.getByTestId("rooms-week")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("rooms-search").fill(ROOM_CODE);
    await expect(page.getByTestId("room-card").first()).toContainText(ROOM_CODE);

    await page.goto(`/rooms?layout=table`);
    await expect(page.getByTestId("room-row")).toHaveCount(rooms.length);

    await page.goto(`/rooms/${room.id}`);
    await expect(page.getByTestId("room-detail")).toBeVisible();
    await expect(page.getByTestId("room-week-grid")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("room-term-heat")).toBeVisible({ timeout: 30_000 });
    const href = await page.getByTestId("room-open-calendar").getAttribute("href");
    expect(href).toContain(`subject=room:${room.id}`);
    // the term strip picks the week
    const week = (await page.getByTestId("room-week").textContent()) ?? "";
    await page.getByTestId("room-term-heat").getByRole("button").nth(5).click();
    await expect(page.getByTestId("room-week")).not.toHaveText(week);
    await expect(page).toHaveURL(/week=\d+/);
  });
});

// ------------------------------------------------------------------------------------------------ motion audit
type FrameReport = { frames: number; dropped: number; p95: number; longFrames: number; worstLongFrame: number };

async function startFrameProbe(page: Page): Promise<void> {
  await page.evaluate(() => {
    type Probe = { deltas: number[]; loaf: number[]; stop: boolean; po?: PerformanceObserver };
    const w = window as unknown as { __mf?: Probe };
    if (w.__mf) w.__mf.stop = true;
    const st: Probe = { deltas: [], loaf: [], stop: false };
    w.__mf = st;
    let last = performance.now();
    const tick = (t: number) => {
      st.deltas.push(t - last);
      last = t;
      if (!st.stop) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    if (PerformanceObserver.supportedEntryTypes.includes("long-animation-frame")) {
      st.po = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) st.loaf.push(e.duration);
      });
      st.po.observe({ type: "long-animation-frame" });
    }
  });
}

async function stopFrameProbe(page: Page): Promise<FrameReport> {
  return page.evaluate(() => {
    const w = window as unknown as { __mf: { deltas: number[]; loaf: number[]; stop: boolean; po?: PerformanceObserver } };
    w.__mf.stop = true;
    w.__mf.po?.disconnect();
    const d = w.__mf.deltas.slice(1);
    const sorted = [...d].sort((a, b) => a - b);
    const budget = sorted[Math.floor(sorted.length / 2)] ?? 1000 / 60;
    const dropped = d.reduce((n, x) => n + Math.max(0, Math.round(x / budget) - 1), 0);
    return { frames: d.length, dropped, p95: sorted[Math.floor(sorted.length * 0.95)] ?? 0, longFrames: w.__mf.loaf.filter((x) => x > 50).length, worstLongFrame: Math.max(0, ...w.__mf.loaf) };
  });
}

async function animationsOverCeiling(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    document
      .getAnimations()
      .map((a) => ({ a, t: a.effect?.getComputedTiming() }))
      .filter(({ t }) => t && t.iterations !== Infinity && Number(t.duration) + Number(t.delay ?? 0) > 300)
      .map(({ a, t }) => `${(a as CSSAnimation).animationName ?? a.id ?? "anim"} ${String(t?.duration)}ms`),
  );
}

async function traceLayouts(browser: Browser, page: Page, run: () => Promise<void>): Promise<number> {
  await browser.startTracing(page, { categories: ["devtools.timeline"] });
  await run();
  const buf = await browser.stopTracing();
  const json = JSON.parse(buf.toString()) as { traceEvents?: { name: string }[] } | { name: string }[];
  const events = Array.isArray(json) ? json : (json.traceEvents ?? []);
  return events.filter((e) => e.name === "Layout").length;
}

const settle = (page: Page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

/**
 * Motion audit: calendar (2026-10-08, production bundle, Chromium headless shell, software raster, 1× CPU,
 * shared 4-core box at load 8–9: frame numbers are ranges over 5 runs)
 * | Interaction          | dropped | LoAF > 50 ms | Layout events | over-ceiling | reduced motion | reduced transparency |
 * | week step ×2         | 1–72    | 10–16        | 16–17         | none         | no transform ✓ | n/a                  |
 * | inspector appear     | 18–47   | 6–8          | 1             | none         | no transform ✓ | opaque ✓, 14–18 drop |
 * | lens pill morph ×2   | 2–5     | 10–15        | 9–10          | none         | n/a            | n/a                  |
 * Inspector appear: the drops are the viz compositor drawing the page's backdrop-filter surfaces in software on
 * every animated frame (trace: SoftwareRenderer::DoDrawQuad ≈ 550 ms vs ≈ 190 ms on the main thread). The same
 * click with the panel kept still drops 23–29, with every blur off 6–15, so the slide itself costs ≈ 5 frames.
 * Fix applied: sticky day/room headers paint the thick tint over the opaque canvas instead of a backdrop blur
 * (10 → 8 blur surfaces with the inspector open; the shell owns 3 of them).
 * Hard gates (deterministic): no finite animation over 300 ms, Layout events ≤ baseline + 50 %, reduced motion
 * lands without transforms, reduced transparency is opaque. Frame budgets (≤ 3 dropped per interaction + the
 * input frame, LoAF) only with MOTION_STRICT=1 on a quiet machine; device check: MOTION_STRICT=1 MOTION_CPU=4 --headed.
 */
const STRICT = process.env.MOTION_STRICT === "1";
const LAYOUT_BASELINE: Record<string, number> = { "week step ×2": 17, "inspector appear": 2, "lens pill morph ×2": 10 };

test.describe("motion audit: calendar", () => {
  const rate = Number(process.env.MOTION_CPU ?? 1);

  test("lens switch, week step and inspector appear hold the frame budget under the 300 ms ceiling", async ({ page, browser }) => {
    test.setTimeout(180_000);
    await login(page);
    await page.goto(`/timetable?run=${SOLVER_RUN}&week=3&lens=week&subject=room:13`);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(800);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate });

    const report: Record<string, FrameReport & { layouts: number; over: string[]; interactions: number }> = {};
    const measure = async (name: string, interactions: number, run: () => Promise<void>) => {
      await startFrameProbe(page);
      let over: string[] = [];
      const layouts = await traceLayouts(browser, page, async () => {
        await run();
        over = await animationsOverCeiling(page);
        await page.waitForTimeout(450);
      });
      report[name] = { ...(await stopFrameProbe(page)), layouts, over, interactions } as (typeof report)[string];
    };

    await measure("week step ×2", 2, async () => {
      await page.getByTestId("week-next").click();
      await page.waitForTimeout(350);
      await page.getByTestId("week-prev").click();
    });
    await measure("inspector appear", 1, async () => {
      await page.getByTestId("calendar-event").first().click();
      await page.getByTestId("class-inspector").waitFor();
    });
    await measure("lens pill morph ×2", 2, async () => {
      await lensTab(page, "Agenda").click();
      await page.getByTestId("agenda").waitFor();
      await page.waitForTimeout(350);
      await lensTab(page, "Week").click();
      await page.getByTestId("time-grid").waitFor();
    });
    console.log("motion audit (calendar)", JSON.stringify({ rate, report }));
    for (const [name, r] of Object.entries(report)) {
      expect(r.over, `${name}: animations over 300 ms`).toEqual([]);
      expect(r.layouts, `${name}: Layout events`).toBeLessThanOrEqual(Math.ceil((LAYOUT_BASELINE[name] ?? 4) * 1.5));
      if (STRICT) {
        expect(r.dropped, `${name}: dropped frames`).toBeLessThanOrEqual(3 * r.interactions + 1);
        expect(r.worstLongFrame, `${name}: worst LoAF`).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
      }
    }
  });

  test("reduced motion: the inspector and the week canvas land without transforms", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page);
    await page.goto(`/timetable?run=${SOLVER_RUN}&week=3&lens=week&subject=room:13`);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("calendar-event").first().click();
    const insp = page.getByTestId("class-inspector");
    await insp.waitFor();
    await page.getByTestId("week-next").click();
    await settle(page);
    expect(["none", "matrix(1, 0, 0, 1, 0, 0)"]).toContain(await insp.evaluate((el) => getComputedStyle(el).transform));
    const moving = await page.evaluate(() =>
      document.getAnimations().filter((a) => {
        const kf = (a.effect as KeyframeEffect | null)?.getKeyframes() ?? [];
        return a.playState === "running" && kf.some((k) => "transform" in k || "translate" in k || "scale" in k);
      }).length,
    );
    expect(moving).toBe(0);
  });

  test("reduced transparency: the inspector and capsules are opaque", async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
    await login(page);
    await page.goto(`/timetable?run=${SOLVER_RUN}&week=3&lens=week&subject=room:13`);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(800);
    await startFrameProbe(page);
    await page.getByTestId("calendar-event").first().click();
    const insp = page.getByTestId("class-inspector");
    await insp.waitFor();
    await page.waitForTimeout(450);
    const frames = await stopFrameProbe(page);
    console.log("motion audit (calendar, reduced transparency) inspector appear", JSON.stringify(frames));
    if (STRICT) expect(frames.dropped, "inspector appear without glass: dropped frames").toBeLessThanOrEqual(4);
    // the glass utilities paint the tint as the last background-image layer (grain, sheen, tint)
    const style = await insp.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { backdrop: cs.backdropFilter, image: cs.backgroundImage, color: cs.backgroundColor };
    });
    expect(style.backdrop === "none" || style.backdrop === "").toBeTruthy();
    const colours = [...`${style.image} ${style.color}`.matchAll(/rgba?\(([^)]+)\)/g)].map((m) => m[1].split(",").map((x) => Number(x.trim())));
    const tint = colours.filter((c) => (c[3] ?? 1) > 0).at(-1);
    expect(tint, `inspector background ${style.image}`).toBeTruthy();
    expect(tint?.[3] ?? 1, `inspector tint ${JSON.stringify(tint)}`).toBeGreaterThanOrEqual(0.9);
  });
});
