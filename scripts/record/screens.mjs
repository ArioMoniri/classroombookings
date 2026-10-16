#!/usr/bin/env node
// README screenshots from the running recording stack (scripts/record/stack.sh up + runs): real data only.
//
//   node scripts/record/screens.mjs [--out docs/images/screens] [--themes light,dark] [--only a,b] [--png]
//
// Every shot is taken at 1440×900 (CSS px, device scale 1) unless it says otherwise; phone shots are
// 390×844 at device scale 2. Files: <name>-<theme>.webp (quality 82; --png keeps PNG). Shots marked
// `as: "staff"` sign in as the academic staff account the approval-flow recording creates (record-all.sh runs
// first and keeps the stack up). Private calendar-feed links are blurred; instructor names are initials (KVKK).
// Env: REC_BASE_URL (default http://127.0.0.1:3610), REC_EMAIL / REC_PASSWORD, REC_TERM_CODE (2026-GUZ).
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { FIXTURES, api, dayGrid, profileLanguage, freeRun, maskBeforeShowing, nextTeachingDay, slotKey } from "./journeys/_shared.mjs";
import { STAFF } from "./journeys/approval-flow.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../..");
const env = process.env;
const { values: args } = parseArgs({
  options: {
    out: { type: "string", default: join(REPO, "docs/images/screens") },
    themes: { type: "string", default: "light,dark" },
    only: { type: "string" },
    png: { type: "boolean", default: false },
  },
});
if (!env.PLAYWRIGHT_BROWSERS_PATH) env.PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers";
const require = createRequire(join(REPO, "smartsched/frontend/package.json"));
const { chromium } = require("playwright");
const BASE = env.REC_BASE_URL ?? "http://127.0.0.1:3610";
const CREDS = { email: env.REC_EMAIL ?? "admin@smartsched.local", password: env.REC_PASSWORD ?? "Admin-2026!" };
const TERM = env.REC_TERM_CODE ?? "2026-GUZ";
const WEEK = 3;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const out = resolve(args.out);
mkdirSync(out, { recursive: true });
const only = args.only ? new Set(args.only.split(",")) : null;

const settle = async (page, ms = 1200) => {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(ms);
};
const visible = (page, id, timeout = 30_000) => page.getByTestId(id).first().waitFor({ timeout });
/** scroll an element to the top of the scrolling content, leaving `gap` px above it */
const scrollTo = async (page, locator, gap = 96) => {
  await locator.first().evaluate((el, g) => {
    let p = el.parentElement;
    while (p && !(p.scrollHeight > p.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(p).overflowY))) p = p.parentElement;
    const top = el.getBoundingClientRect().top;
    if (p) p.scrollBy({ top: top - p.getBoundingClientRect().top - g, behavior: "instant" });
    else window.scrollBy({ top: top - g, behavior: "instant" });
  }, gap);
  await page.waitForTimeout(500);
};

/** Data the shots need, resolved once through the API (never typed in). */
async function context(page) {
  const terms = (await api(page, "/terms")).data;
  const term = terms.find((t) => t.code === TERM);
  const runs = (await api(page, `/runs?term_id=${term.id}`)).data;
  const termRun = runs.find((r) => r.is_active && r.kind === "COURSE") ?? runs.find((r) => r.horizon === "TERM" && r.kind === "COURSE");
  const weekRun = runs.find((r) => r.horizon === "WEEK" && r.kind === "COURSE" && (r.diagnosis ?? []).length) ?? runs.find((r) => r.horizon === "WEEK");
  const idx = (await api(page, `/runs/${termRun.id}/calendar-index`)).data;
  const count = new Map();
  for (const a of idx.assignments) for (const r of a.rooms ?? []) count.set(r, (count.get(r) ?? 0) + 1);
  const busiest = [...count.entries()].sort((a, b) => b[1] - a[1])[0][0];
  const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
  const a101 = rooms.find((r) => r.code === "A101");
  const groupA = a101?.room_group_id ?? rooms.find((r) => r.room_group_id)?.room_group_id;
  const nextDay = await nextTeachingDay(page);
  const grid = await dayGrid(page, nextDay, groupA);
  const free = freeRun(grid, 1, { maxPeriod: 5 })[0];
  const features = (await api(page, "/room-admin/features")).data ?? [];
  const pc = features.find((f) => f.solver_tag === "PC");
  // the Term lens needs a term with all its calendar weeks: the Güz grid workbook holds two weeks only,
  // so that shot uses the planner's imported Bahar 2026 board (15 weeks)
  const bahar = terms.find((t) => t.code === "2026-BAHAR");
  const baharRuns = bahar ? (await api(page, `/runs?term_id=${bahar.id}`)).data : [];
  const baharBoard = baharRuns.find((r) => r.kind === "COURSE" && r.params?.source === "GRID_IMPORT")?.id ?? termRun.id;
  return { termRun: termRun.id, weekRun: weekRun.id, busiest, groupA, a101: a101?.id, nextDay, free, pc, baharBoard };
}

/** The approvals inbox needs an open request: the academic staff account asks for the approval room (no note). */
async function pendingRequest(page) {
  const rules = (await api(page, "/approval-rules")).data ?? [];
  const roomId = rules.find((r) => r.entity_type === "room")?.entity_id;
  if (!roomId) return null;
  const inbox = (await api(page, "/approvals/inbox")).data;
  const items = Array.isArray(inbox) ? inbox : (inbox?.items ?? inbox?.requests ?? []);
  if (items.some((r) => r.status === "PENDING")) return null;
  const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
  const room = rooms.find((r) => r.id === roomId);
  const date = await nextTeachingDay(page);
  const grid = await dayGrid(page, date, room.room_group_id);
  const slot = freeRun(grid, 1, { exclude: grid.rooms.filter((r) => r.id !== roomId).map((r) => r.id), maxPeriod: 10, from: 4 })[0];
  const terms = (await api(page, "/terms")).data;
  return { slot, termId: terms.find((t) => t.code === TERM).id };
}

const blurFeeds = (page) =>
  page.addStyleTag({ content: "[data-testid^=sync-url]{filter:blur(5px)!important}" });

// name → async (page, ctx) that leaves the page ready for the screenshot. `as: "staff"` signs in as the academic
// staff account the approval-flow recording uses (a role, not a person); the rest is the seeded administrator.
const SHOTS = {
  login: { auth: false, go: async (page) => { await page.goto("/login"); await visible(page, "login-submit"); await settle(page, 1500); } },
  dashboard: { go: async (page) => { await page.goto("/dashboard"); await visible(page, "dashboard-hero"); await settle(page, 2500); } },
  // bookings (staff)
  "bookings-day": { go: async (page, c) => { await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}&lens=grid`); await visible(page, "booking-grid"); await settle(page, 2000); } },
  "bookings-room": { go: async (page, c) => { await page.goto(`/bookings?display=room&room=${c.a101}&date=${c.nextDay}&lens=grid`); await visible(page, "booking-grid"); await settle(page, 2000); } },
  "reserve-sheet": {
    go: async (page, c) => {
      await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}&lens=grid`);
      await visible(page, "booking-grid");
      await page.locator(`button[data-slot-key="${slotKey(c.free)}"]`).click();
      await visible(page, "book-sheet");
      await settle(page, 1200);
    },
  },
  "free-slots": { go: async (page, c) => { await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}&lens=free`); await visible(page, "free-slots"); await settle(page, 2000); } },
  "room-details": {
    go: async (page, c) => {
      await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}&lens=grid`);
      await visible(page, "booking-grid");
      await page.getByTestId("room-info-A101").click();
      await visible(page, "room-info");
      await page.getByTestId("room-alternatives").locator('[data-testid^="alt-reserve-"]').first().waitFor({ timeout: 20_000 }).catch(() => undefined);
      await settle(page, 1200);
    },
  },
  "calendar-sync": {
    go: async (page, c) => {
      await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}&lens=grid`);
      await visible(page, "booking-grid");
      await page.getByTestId("sync-open").click();
      await visible(page, "sync-sheet");
      const create = page.getByTestId("sync-create");
      if (await create.isVisible().catch(() => false)) await create.click();
      await page.getByTestId("sync-url-mine").waitFor({ timeout: 20_000 }).catch(() => undefined);
      await blurFeeds(page);
      await settle(page, 1200);
    },
  },
  "my-bookings": { go: async (page) => { await page.goto("/my-bookings"); await visible(page, "mine-totals"); await blurFeeds(page); await settle(page, 2000); } },
  "find-room": {
    go: async (page, c) => {
      await page.goto("/find-room");
      const view = page.getByTestId("find-room");
      await view.waitFor({ timeout: 30_000 });
      await view.getByTestId("fr-date").fill(c.nextDay);
      await view.getByTestId("fr-start").fill("10:10");
      await view.getByTestId("fr-end").fill("12:30");
      await view.getByTestId("fr-headcount").fill("40");
      if (c.pc) await view.getByTestId(`fr-feature-${c.pc.id}`).click();
      await view.getByTestId("fr-search").click();
      await view.getByTestId("fr-summary").waitFor({ timeout: 30_000 });
      await settle(page, 1500);
    },
  },
  notifications: {
    as: "staff",
    go: async (page) => {
      await page.goto("/my-bookings");
      await visible(page, "mine-totals");
      await page.locator('[data-testid="notification-bell"]:visible').click();
      await visible(page, "notification-panel");
      await settle(page, 1200);
    },
  },
  "my-requests": { as: "staff", go: async (page) => { await page.goto("/my-bookings"); await visible(page, "my-requests"); await scrollTo(page, page.getByTestId("my-requests"), 120); await blurFeeds(page); await settle(page, 1500); } },
  // approvals and administration
  approvals: {
    go: async (page) => {
      const pending = await pendingRequest(page);
      if (pending) await staffRequest(pending);
      await page.goto("/approvals");
      await visible(page, "approvals-list");
      const first = page.getByTestId("approvals-list").locator('[data-testid^="approval-"]').first();
      await first.click();
      await visible(page, "approval-drawer");
      await page.getByTestId("approval-room-day").waitFor({ timeout: 20_000 }).catch(() => undefined);
      await settle(page, 1500);
    },
  },
  "approval-rules": { go: async (page) => { await page.goto("/admin/approval-rules"); await visible(page, "approval-rules"); await settle(page, 1500); } },
  audit: {
    go: async (page) => {
      await page.goto("/admin/audit");
      await visible(page, "audit-list");
      const ev = page.locator('[data-action="booking.update"], [data-action="booking.create"]').first();
      await ev.locator("button[aria-expanded]").first().click();
      await ev.getByTestId("audit-diff").waitFor({ timeout: 20_000 }).catch(() => undefined);
      await settle(page, 1200);
    },
  },
  "room-features": { go: async (page) => { await page.goto("/admin/rooms?tab=features"); await visible(page, "features-tab"); await settle(page, 1800); } },
  "admin-users": { go: async (page) => { await page.goto("/admin/users"); await visible(page, "users-table"); await settle(page, 1500); } },
  "admin-roles": { go: async (page) => { await page.goto("/admin/roles"); await visible(page, "role-editor"); await settle(page, 1500); } },
  "settings-ai": { go: async (page) => { await page.goto("/settings"); await page.getByTestId("tab-ai").click(); await visible(page, "ai-policy"); await settle(page, 1500); } },
  // planning (coordinator)
  "studio-scope": { go: async (page) => studio(page, "scope") },
  "studio-rules": {
    go: async (page) => {
      await studio(page, "rules");
      await scrollTo(page, page.getByTestId("rule-group-must").or(page.getByTestId("rule-group-try")), 220);
    },
  },
  "studio-precheck": {
    go: async (page) => {
      await studio(page, "check");
      const done = page.locator("[data-testid=check-step] [data-testid=readiness]:not([data-readiness=checking]):not([data-readiness=unknown])");
      if (!(await done.waitFor({ timeout: 5_000 }).then(() => true, () => false))) {
        await page.getByTestId("recheck").click();
        await done.waitFor({ timeout: 180_000 });
      }
      await settle(page, 800);
    },
  },
  "run-report": { go: async (page, c) => { await page.goto(`/runs/${c.weekRun}`); await visible(page, "run-hero"); await settle(page, 2000); } },
  "run-diagnoses": {
    go: async (page, c) => {
      await page.goto(`/runs/${c.weekRun}`);
      await visible(page, "diagnosis-card");
      await scrollTo(page, page.getByTestId("unplaced-section"), 24);
      await settle(page, 800);
    },
  },
  "run-data-issues": {
    go: async (page, c) => {
      await page.goto(`/runs/${c.weekRun}`);
      await visible(page, "run-hero");
      const group = page.locator("[data-testid^=issue-group-]").first();
      await group.waitFor({ timeout: 30_000 });
      await scrollTo(page, group, 140);
      await settle(page, 800);
    },
  },
  import: { go: async (page) => { await page.goto("/import"); await visible(page, "import"); await settle(page, 1500); } },
  "onboarding-review": {
    go: async (page) => {
      await maskBeforeShowing(page, "**/api/v1/council/jobs/*/review", () => true);
      await page.goto("/onboarding");
      await visible(page, "onboarding-drop");
      await page.getByTestId("onboarding-input").setInputFiles(`${FIXTURES}/final_planlama_listesi_2026_v2.xlsx`);
      const ai = page.getByTestId("onboarding-drop").locator('input[type="checkbox"]').first();
      // a styled checkbox: the label takes the click
      if (await ai.isChecked()) await page.getByTestId("onboarding-drop").getByText(/Use the AI model|yapay zek/i).first().click();
      await page.getByTestId("onboarding-start").click();
      await visible(page, "onboarding-review", 300_000);
      await scrollTo(page, page.getByTestId("onboarding-review"), 120);
      await settle(page, 1500);
    },
  },
  "calendar-board": { go: async (page, c) => { await page.goto(`/timetable?run=${c.termRun}&week=${WEEK}&lens=board`); await visible(page, "calendar-event"); await settle(page, 2000); } },
  "calendar-week": { go: async (page, c) => { await page.goto(`/timetable?run=${c.termRun}&week=${WEEK}&lens=week&subject=room:${c.busiest}`); await visible(page, "calendar-event"); await settle(page, 2000); } },
  "calendar-term": { go: async (page, c) => { await page.goto(`/timetable?run=${c.baharBoard}&week=${WEEK}&lens=term`); await visible(page, "term-heat"); await settle(page, 2500); } },
  "calendar-inspector": {
    go: async (page, c) => {
      await page.goto(`/timetable?run=${c.termRun}&week=${WEEK}&lens=week&subject=room:${c.busiest}`);
      await visible(page, "calendar-event");
      await page.getByTestId("calendar-event").nth(2).click();
      await visible(page, "class-inspector");
      await settle(page, 1500);
    },
  },
  classes: { go: async (page) => { await page.goto("/classes"); await visible(page, "classes-row"); await settle(page, 2000); } },
  "classes-inspector": {
    go: async (page) => {
      await page.goto("/classes");
      await visible(page, "classes-row");
      await page.getByTestId("classes-row").nth(1).click();
      await visible(page, "class-inspector");
      await settle(page, 1500);
    },
  },
  rooms: { go: async (page) => { await page.goto("/rooms"); await page.getByTestId("rooms-table").or(page.getByTestId("room-card")).first().waitFor({ timeout: 30_000 }); await settle(page, 2000); } },
  // phone
  "mobile-bookings": { viewport: PHONE, go: async (page, c) => { await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}`); await visible(page, "free-slots"); await settle(page, 2500); } },
  "mobile-timetable": { viewport: PHONE, go: async (page, c) => { await page.goto(`/timetable?run=${c.termRun}&week=${WEEK}&lens=day&subject=room:${c.busiest}`); await visible(page, "calendar"); await settle(page, 2500); } },
};

/** An open approval request for the inbox shot: the staff account books the approval room (202, PENDING). */
async function staffRequest({ slot, termId }) {
  const ctx = await newContext(browser, { theme: "light", lang: "en", viewport: DESKTOP });
  const page = await ctx.newPage();
  await login(page, STAFF);
  const res = await api(page, "/bookings", { method: "POST", body: { room_id: slot.room_id, date: slot.date, period_id: slot.period_id, term_id: termId } });
  if (res.status !== 202) console.log(`note: the staff request answered ${res.status}`);
  await ctx.close();
}

async function studio(page, step) {
  if (!page.url().includes("/generate")) {
    await page.goto("/generate");
    await visible(page, "generate");
  }
  await page.getByTestId(`rail-step-${step}`).click();
  await visible(page, step === "check" ? "check-step" : `${step}-step`);
  await settle(page, 1500);
}

async function newContext(browser, { theme, lang, viewport }) {
  const phone = viewport === PHONE;
  const ctx = await browser.newContext({
    baseURL: BASE,
    viewport,
    deviceScaleFactor: phone ? 2 : 1,
    isMobile: phone,
    hasTouch: phone,
    colorScheme: theme,
    locale: lang === "tr" ? "tr-TR" : "en-GB",
    timezoneId: "Europe/Istanbul",
  });
  await ctx.addCookies([{ name: "NEXT_LOCALE", value: lang, url: BASE }]);
  await ctx.addInitScript(({ theme }) => {
    try {
      localStorage.setItem("theme", theme);
      // keep the cookie's language: the booking pages otherwise apply the profile language once per session
      sessionStorage.setItem("crbs.profile-language", "1");
    } catch {
      /* ignore */
    }
    document.addEventListener("DOMContentLoaded", () => {
      const s = document.createElement("style");
      s.textContent = "::-webkit-scrollbar{width:0!important;height:0!important} *{caret-color:transparent!important}";
      document.head.appendChild(s);
    });
  }, { theme });
  return ctx;
}

async function login(page, creds) {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(creds.email);
  await page.getByTestId("login-password").fill(creds.password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

const browser = await chromium.launch();
const themes = args.themes.split(",");
let c = null;
const written = [];
const failed = [];
// group by (theme, lang, viewport, auth) so each group signs in once
for (const theme of themes) {
  for (const [name, shot] of Object.entries(SHOTS)) {
    if (only && !only.has(name)) continue;
    if (shot.themes && !shot.themes.includes(theme)) continue;
    const lang = shot.lang ?? "en";
    const viewport = shot.viewport ?? DESKTOP;
    const ctx = await newContext(browser, { theme, lang, viewport });
    const page = await ctx.newPage();
    try {
      if (shot.auth !== false) {
        if (!c) {
          await login(page, CREDS);
          c = await context(page);
          if (shot.as === "staff") {
            await page.context().clearCookies();
            await page.context().addCookies([{ name: "NEXT_LOCALE", value: lang, url: BASE }]);
          }
        }
        if (shot.as === "staff") await login(page, STAFF);
        else if (page.url() === "about:blank") await login(page, CREDS);
        await profileLanguage(page, lang); // the app follows the signed-in user's profile language
      }
      await shot.go(page, c);
      const base = join(out, `${name}-${theme}`);
      await page.screenshot({ path: `${base}.png` });
      if (!args.png) {
        execFileSync("convert", [`${base}.png`, "-quality", "82", "-define", "webp:method=6", `${base}.webp`]);
        rmSync(`${base}.png`);
      }
      const file = `${base}.${args.png ? "png" : "webp"}`;
      written.push(`${file} ${(statSync(file).size / 1024).toFixed(0)} KB`);
      console.log(`ok   ${name}-${theme}`);
    } catch (e) {
      failed.push(`${name}-${theme}: ${String(e.message).split("\n")[0]}`);
      console.log(`FAIL ${name}-${theme}: ${String(e.message).split("\n")[0]}`);
      await page.screenshot({ path: join(out, `${name}-${theme}.failure.png`) }).catch(() => undefined);
    } finally {
      await ctx.close();
    }
  }
}
await browser.close();
console.log(`\n${written.length} written, ${failed.length} failed`);
if (failed.length) process.exit(2);
