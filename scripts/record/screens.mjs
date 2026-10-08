#!/usr/bin/env node
// README screenshots from the running recording stack (scripts/record/stack.sh up + runs): real data only.
//
//   node scripts/record/screens.mjs [--out docs/images/screens] [--themes light,dark] [--only a,b] [--png]
//
// Every shot is taken at 1440×900 (CSS px, device scale 1) unless it says otherwise; phone shots are
// 390×844 at device scale 2. Files: <name>-<theme>.webp (quality 82); Turkish shots end in -tr.
// Env: REC_BASE_URL (default http://127.0.0.1:3610), REC_EMAIL / REC_PASSWORD, REC_TERM_CODE (2026-GUZ).
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { api } from "./journeys/_shared.mjs";

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
  const groupA = rooms.find((r) => r.code === "A203")?.room_group_id ?? rooms.find((r) => r.room_group_id)?.room_group_id;
  const mine = (await api(page, "/bookings/mine")).data ?? [];
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Istanbul" }));
  do d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6);
  const nextDay = mine[0]?.date ?? d.toISOString().slice(0, 10);
  // the Term lens needs a term with all its calendar weeks: the Güz grid workbook holds two weeks only,
  // so that shot uses the planner's imported Bahar 2026 board (15 weeks)
  const bahar = terms.find((t) => t.code === "2026-BAHAR");
  const baharRuns = bahar ? (await api(page, `/runs?term_id=${bahar.id}`)).data : [];
  const baharBoard = baharRuns.find((r) => r.kind === "COURSE" && r.params?.source === "GRID_IMPORT")?.id ?? termRun.id;
  return { termRun: termRun.id, weekRun: weekRun.id, busiest, groupA, nextDay, baharBoard };
}

// name → async (page, ctx) that leaves the page ready for the screenshot
const SHOTS = {
  login: { auth: false, go: async (page) => { await page.goto("/login"); await visible(page, "login-submit"); await settle(page, 1500); } },
  dashboard: { go: async (page) => { await page.goto("/dashboard"); await visible(page, "dashboard-hero"); await settle(page, 2500); } },
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
  rooms: { go: async (page) => { await page.goto("/rooms"); await visible(page, "room-card"); await settle(page, 2000); } },
  "room-detail": { go: async (page, c) => { await page.goto(`/rooms/${c.busiest}`); await visible(page, "room-week-grid"); await settle(page, 2000); } },
  bookings: { go: async (page, c) => { await page.goto(`/bookings?date=${c.nextDay}&group=${c.groupA}`); await visible(page, "booking-grid"); await settle(page, 2000); } },
  "my-bookings": { go: async (page) => { await page.goto("/my-bookings"); await visible(page, "mine-totals"); await settle(page, 2000); } },
  "admin-users": { go: async (page) => { await page.goto("/admin/users"); await visible(page, "users-table"); await settle(page, 1500); } },
  "admin-roles": { go: async (page) => { await page.goto("/admin/roles"); await visible(page, "role-editor"); await settle(page, 1500); } },
  "setup-requirements": {
    go: async (page) => {
      await page.goto("/admin");
      await visible(page, "setup-requirements");
      await settle(page, 1500);
    },
  },
  "settings-appearance": { go: async (page) => { await page.goto("/settings"); await page.getByTestId("tab-appearance").click(); await settle(page, 1500); } },
  // phone
  "mobile-dashboard": { viewport: PHONE, go: async (page) => { await page.goto("/dashboard"); await visible(page, "dashboard-hero"); await settle(page, 2500); } },
  "mobile-calendar": { viewport: PHONE, go: async (page, c) => { await page.goto(`/timetable?run=${c.termRun}&week=${WEEK}&lens=day&subject=room:${c.busiest}`); await visible(page, "calendar"); await settle(page, 2500); } },
  // Turkish (light only)
  "dashboard-tr": { lang: "tr", themes: ["light"], go: async (page) => SHOTS.dashboard.go(page) },
  "studio-rules-tr": { lang: "tr", themes: ["light"], go: async (page, c) => SHOTS["studio-rules"].go(page, c) },
};

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

async function login(page) {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(CREDS.email);
  await page.getByTestId("login-password").fill(CREDS.password);
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
      if (shot.auth !== false) await login(page);
      if (!c && shot.auth !== false) c = await context(page);
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
