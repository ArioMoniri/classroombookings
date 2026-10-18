// Helpers shared by the journeys. Selectors are the data-testids the real-backend e2e specs use
// (smartsched/frontend/e2e/*.spec.ts), so a journey breaks together with a spec, not silently.
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
// the workbooks a journey uploads: the masked copies stack.sh writes ($REC_WORKDIR/fixtures, E2E_FIXTURES_DIR) when
// set; a stack with the KVKK upload guard refuses the raw seed workbooks
export const FIXTURES = process.env.E2E_FIXTURES_DIR ? resolve(process.env.E2E_FIXTURES_DIR) : resolve(REPO, "smartsched/backend/tests/fixtures");

/** Caption in the requested language (REC_CAPTION_LANG / ctx.captionLang when it differs from the UI language). */
export const tr = (ctx, en, trText) => ((ctx.captionLang ?? ctx.lang) === "tr" ? trText : en);

/** Log in through the UI without recording it (used in setup(), before the sync flash). */
export async function login(page, { email, password }) {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(email);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
  await quietWelcome(page);
}

/** The welcome guide (components/welcome, 2026-10-18) opens a sheet on a user's first visit to a home page. A take
 * shows the feature, not the guide: tell the server this user dismissed it ("Don't show again"), as a person would.
 * Older builds have no /welcome: the call fails quietly. */
export async function quietWelcome(page) {
  await api(page, "/welcome/events", { method: "POST", body: { guide_key: "sheet", event: "dismissed" } }).catch(() => undefined);
}

/** Same-origin API call through the Next proxy (the httpOnly cookie carries the JWT). */
export async function api(page, path, { method = "GET", body } = {}) {
  const res = await page.evaluate(
    async ({ url, method, body }) => {
      const r = await fetch(url, {
        method,
        headers: { Accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
      let data = null;
      try {
        data = await r.json();
      } catch {
        /* empty */
      }
      return { status: r.status, data };
    },
    { url: `/api/v1${path}`, method, body },
  );
  return res;
}

export async function termId(page, code) {
  const { data } = await api(page, "/terms");
  const t = (data ?? []).find((x) => x.code === code) ?? (data ?? [])[0];
  if (!t) throw new Error("no term: run scripts/record/stack.sh up first");
  return t.id;
}

/** The newest run of a kind with a given status set (e.g. a FEASIBLE COURSE run for the grid). */
export async function findRun(page, tid, { kind = "COURSE", statuses = ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"], withDiagnoses = false } = {}) {
  const { data } = await api(page, `/runs?term_id=${tid}`);
  const runs = (data ?? []).filter((r) => r.kind === kind && statuses.includes(r.status));
  if (!withDiagnoses) return runs[0] ?? null;
  for (const r of runs) {
    const { data: full } = await api(page, `/runs/${r.id}`);
    if ((full?.diagnosis ?? full?.diagnoses ?? []).length) return full;
  }
  return null;
}

/** The `n`th open teaching day after the backend's "today" (the booking clock), as YYYY-MM-DD. Journeys that
 * clean up their own unnoted bookings use different days, so one journey's cleanup never touches another's. */
export async function nextTeachingDay(page, n = 1) {
  const { data } = await api(page, "/bookings/dates");
  const day = (data?.dates ?? []).filter((d) => d.date > data.today && d.open && d.weekday >= 1 && d.weekday <= 5 && !d.holiday)[n - 1];
  if (!day) throw new Error("no open teaching day: scripts/record/stack.sh up runs the booking setup");
  return day.date;
}

export const slotKey = (s) => `${s.date}|${s.period_id}|${s.room_id}`;
const reservable = (s) => !!s && s.status === "available" && !!s.allow_single;

/** The day grid of a room group (what the /bookings page shows). */
export async function dayGrid(page, date, groupId) {
  const { data } = await api(page, `/bookings/grid?display=day&date=${date}&room_group_id=${groupId}`);
  return data;
}

/** First room (grid order, skipping `exclude`) with `n` reservable periods in a row among the first `maxPeriod` periods. */
export function freeRun(grid, n, { exclude = [], maxPeriod = 6, from = 0 } = {}) {
  const idx = new Map(grid.slots.map((s) => [slotKey(s), s]));
  const date = grid.slots[0].date;
  const periods = grid.periods.slice(0, maxPeriod);
  for (const room of grid.rooms) {
    if (exclude.includes(room.id)) continue;
    const day = periods.map((p) => idx.get(slotKey({ date, period_id: p.id, room_id: room.id })));
    for (let i = from; i + n <= day.length; i++) {
      const part = day.slice(i, i + n);
      if (part.every(reservable)) return part;
    }
  }
  throw new Error(`no room with ${n} free periods in a row`);
}

/** Cancel the signed-in user's bookings whose note is one of `notes`, or (`unnoted`) that have no note on `date`
 * (a journey's own bookings from an earlier take). */
export async function cancelMine(page, notes, { unnoted = null } = {}) {
  const mine = (await api(page, "/bookings/mine")).data ?? [];
  for (const b of mine) {
    if (notes.includes(b.notes) || (unnoted && !b.notes && b.date === unnoted)) {
      await api(page, `/bookings/${b.id}/cancel`, { method: "POST", body: { scope: "one", reason: "recording retake" } });
    }
  }
}

/** The signed-in user's profile language = the take's language (after sign-in the app follows the profile). */
export async function profileLanguage(page, lang) {
  await api(page, "/auth/profile", { method: "PUT", body: { language: lang } });
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: lang, url: new URL(page.url()).origin }]);
}

/** Sign out and in as someone else, off camera (inside Recorder.cut or setup), in the take's language. */
export async function switchUser(page, creds) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: creds.lang ?? "en", url: page.url() }]);
  await login(page, creds);
  await profileLanguage(page, creds.lang ?? "en");
}

/**
 * KVKK on a fresh database (the journeys that import the workbooks during the take): when a GET matching
 * `pattern` answers with a finished job (`isDone(json)`), mask the stack's database first (stack.sh mask: instructor
 * names -> title + initials, kvkk_mask.py) and hand the page a fresh answer, read after the mask. The page never
 * receives a full name; nothing else in the answer changes. Runs inside Recorder.cut, so the wait is not shown.
 */
export async function maskBeforeShowing(page, pattern, isDone) {
  const { execFile } = await import("node:child_process");
  const masked = new Map();
  const runMask = () =>
    new Promise((resolveMask, reject) =>
      execFile(resolve(REPO, "scripts/record/stack.sh"), ["mask"], { env: process.env, timeout: 300_000 }, (err, out) =>
        err ? reject(new Error(`stack.sh mask failed: ${err.message}`)) : resolveMask(out),
      ),
    );
  await page.route(pattern, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const res = await route.fetch();
    let json = null;
    try {
      json = await res.json();
    } catch {
      return route.fulfill({ response: res });
    }
    if (!isDone(json)) return route.fulfill({ response: res });
    const key = new URL(route.request().url()).pathname;
    if (!masked.has(key)) masked.set(key, runMask());
    await masked.get(key);
    return route.fulfill({ response: await route.fetch() });
  });
}
