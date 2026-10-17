/**
 * Flow loop round 1, lane D (KVKK / privacy; docs/ROADMAP.md "Flow loop tickets — round 1") against the REAL backend
 * (no mocked API), gated E2E_REAL=1, on the real Bahar 2026 data:
 *
 * 1. T-R1-27 (KVKK m.11): an academician linked to a real Bahar instructor sends two wishes; the coordinator (the admin)
 *    accepts one and rejects the other with a reason that names the coordinator's e-mail. Profil › Gizlilik ›
 *    "Verilerimi indir" → "İndirmemi hazırla" → "İndir": the zip has instructor.json, planning_requests.json (the
 *    rows of Taleplerim / `GET /moderation/people/{id}/history`), teacher_preferences.json (every wish with its status
 *    and reason) and a README naming every file; the coordinator's e-mail is nowhere in it.
 * 2. T-R1-28: a Turkish notice is published, then a newer English-only one. The Turkish reader's gate shows the
 *    Turkish text; after "Okudum" focus is on #main, never on <body>.
 * 3. T-R1-29: GET /learning/suggestions as the academician → 403 with `message_tr` naming "Planlama verilerini görme".
 * 4. Phone 390 × 844 (touch): the notice gate is a bottom sheet with "Okudum" in the bottom 40 % (M-05); Profil ›
 *    Gizlilik has no sideways scroll (M-01), its controls are ≥ 44 px (M-02) and its inputs ≥ 16 px (M-03).
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19114 NEXT_PUBLIC_API_URL=http://127.0.0.1:19114 PW_PORT=19115 \
 *     npx playwright test e2e/loop-r1-laneD.spec.ts
 */
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, TERM_CODE, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const PASSWORD = "Ogretmen-2026!";
const ACAD = { username: `kd.hoca.${STAMP}`, email: `kd.hoca.${STAMP}@uni.edu.tr` };
const PHONE_USER = { username: `kd.tel.${STAMP}`, email: `kd.tel.${STAMP}@uni.edu.tr` };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const TR_TITLE = `Aydınlatma metni ${STAMP}`;

test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

type HistItem = { request_id: number; term_code?: string };
type History = { instructor: { id: number; linked_user: boolean }; terms: { term_code: string; items: HistItem[] }[] };
const ctx = {} as { api: APIRequestContext; token: string; acadToken: string; acadId: number; instructorId: number; rows: number; wishes: number[]; trNotice: number };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown, token = ctx.token): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${p}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  let parsed: unknown = undefined;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  return { status: res.status(), body: parsed as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown, token = ctx.token): Promise<T> {
  const r = await call<T>(method, p, body, token);
  if (r.status >= 400) throw new Error(`${method} ${p} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function loginToken(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
async function publishNotice(language: "tr" | "en", title: string): Promise<{ id: number; version: number }> {
  const draft = await api<{ id: number }>("POST", "/admin/privacy-notices", { language, title, body_md: `${title}: kişisel verileriniz KVKK kapsamında işlenir.` });
  return api<{ id: number; version: number }>("POST", `/admin/privacy-notices/${draft.id}/publish`);
}
async function signInAs(page: Page, id: string, ackNotice = true): Promise<void> {
  await page.goto("about:blank");
  await page.context().clearCookies();
  await login(page, id, PASSWORD, { ackNotice });
}
async function noSideScroll(page: Page): Promise<void> {
  const m = await page.evaluate(() => ({ sw: document.scrollingElement!.scrollWidth, vw: document.documentElement.clientWidth }));
  expect(m.sw, `scrollWidth ${m.sw} > ${m.vw}`).toBeLessThanOrEqual(m.vw + 1);
}
/** MOBILE.md M-02 inside one container: each control is scrolled to the middle of the screen first, so the bottom tab
 *  bar or the top bar never sits over the hit-area probe */
async function smallTargets(page: Page, scope: string): Promise<{ el: string; w: number; h: number }[]> {
  return page.evaluate((sel) => {
    const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
    const hits = (el: Element, x: number, y: number) => {
      const t = document.elementFromPoint(x, y);
      return !!t && (t === el || el.contains(t));
    };
    const out: { el: string; w: number; h: number }[] = [];
    const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
    for (const el of [...(document.querySelector(sel)?.querySelectorAll<HTMLElement>(SEL) ?? [])]) {
      el.scrollIntoView({ block: "center", inline: "center" });
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
      if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
      let w = r.width, h = r.height;
      const lab = (el as HTMLInputElement).labels?.[0];
      if (lab) {
        const l = lab.getBoundingClientRect();
        w = Math.max(w, l.width);
        h = Math.max(h, l.height);
      }
      if (w >= 44 && h >= 44) continue;
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
      if (inView && [[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x!, y!))) continue;
      out.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
    }
    return out;
  }, scope);
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  const term = terms.find((t) => t.code === TERM_CODE)!;
  // a real Bahar instructor whose record no account holds yet
  const people = await api<{ items: { id: number }[] }>("GET", `/terms/${term.id}/moderation/people`, undefined);
  let picked: History | null = null;
  for (const p of people.items.slice(0, 40)) {
    const h = await api<History>("GET", `/moderation/people/${p.id}/history`);
    if (!h.instructor.linked_user && h.terms.some((g) => g.term_code === TERM_CODE && g.items.length)) {
      picked = h;
      break;
    }
  }
  expect(picked, "an unlinked Bahar instructor").not.toBeNull();
  ctx.instructorId = picked!.instructor.id;
  const acad = await api<{ id: number }>("POST", "/users", { username: ACAD.username, email: ACAD.email, firstname: "Kişisel", lastname: "Veri", role: "TEACHER", password: PASSWORD });
  ctx.acadId = acad.id;
  await api("PUT", `/auth/sso/admin/users/${acad.id}/instructor`, { instructor_id: ctx.instructorId });
  await api("POST", "/users", { username: PHONE_USER.username, email: PHONE_USER.email, firstname: "Telefon", lastname: "Okur", role: "TEACHER", password: PASSWORD });
  ctx.acadToken = await loginToken(ACAD.username, PASSWORD);
  const mine = await api<History>("GET", `/moderation/people/${ctx.instructorId}/history`, undefined, ctx.acadToken);
  ctx.rows = mine.terms.reduce((n, g) => n + g.items.length, 0);
  const rid = mine.terms.find((g) => g.term_code === TERM_CODE)!.items[0]!.request_id;
  // two wishes for that class: the admin accepts one and rejects the other with a reason naming the admin
  ctx.wishes = [];
  for (const body of [
    { kind: "building", request_ids: [rid], buildings: ["A"] },
    { kind: "building", request_ids: [rid], buildings: ["B"] },
    { kind: "building", request_ids: [rid], buildings: ["D"] },
  ]) {
    if (ctx.wishes.length === 2) break;
    const r = await call<{ items: { id: number }[] }>("POST", "/moderation/me/preferences", body, ctx.acadToken);
    if (r.status === 201) ctx.wishes.push(r.body.items[0]!.id);
  }
  expect(ctx.wishes.length, "two wishes sent").toBe(2);
  await api("POST", `/moderation/preferences/${ctx.wishes[0]}/decide`, { decision: "accept" });
  await api("POST", `/moderation/preferences/${ctx.wishes[1]}/decide`, { decision: "reject", reason: `Bu blokta uygun derslik yok; soru için ${ADMIN_EMAIL}`, reason_code: "capacity" });
  // T-R1-28: a Turkish notice, then a newer English-only one
  ctx.trNotice = (await publishNotice("tr", TR_TITLE)).id;
  await publishNotice("en", `Privacy notice ${STAMP}`);
});

test.afterAll(async () => {
  await ctx.api?.dispose();
});

test("1. T-R1-28: the Turkish reader gets the Turkish notice; after Okudum focus is on #main", async ({ page }) => {
  const me = await api<{ notice: { id: number; language: string }; needs_ack: boolean }>("GET", "/me/privacy", undefined, ctx.acadToken);
  expect(me.notice).toMatchObject({ id: ctx.trNotice, language: "tr" });
  expect(me.needs_ack).toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  await signInAs(page, ACAD.username, false);
  const gate = page.getByTestId("notice-gate");
  await expect(gate).toBeVisible();
  await expect(gate).toContainText(TR_TITLE);
  await gate.getByTestId("notice-gate-ack").click();
  await expect(gate).toBeHidden();
  await expect.poll(() => page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName)).toBe("main");
});

test("2. T-R1-27: Verilerimi indir holds the instructor record, Taleplerim's rows and the wishes, nobody else", async ({ page }) => {
  await signInAs(page, ACAD.username);
  await page.goto("/profile#privacy");
  const card = page.getByTestId("privacy-requests");
  await card.getByTestId("privacy-request-kind").selectOption("export");
  await expect(card).toContainText("öğretim elemanı kaydınız");
  await card.getByTestId("privacy-request-send").click();
  const btn = card.locator('[data-testid^="privacy-download-"]').first();
  await expect(btn).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), btn.click()]);
  const dir = mkdtempSync(path.join(tmpdir(), "laneD-"));
  try {
    const zip = path.join(dir, "export.zip");
    await download.saveAs(zip);
    const py = String.raw`
import json, sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
print(json.dumps({"names": names, "readme": z.read("README.txt").decode(), "data": json.loads(z.read("data.json")),
  "whole": "\n".join(z.read(n).decode("utf-8") for n in names)}))
`;
    const out = spawnSync("python3", ["-I", "-c", py, zip], { encoding: "utf-8", maxBuffer: 64 * 1024 * 1024 });
    expect(out.status, out.stderr).toBe(0);
    const { names, readme, data, whole } = JSON.parse(out.stdout) as { names: string[]; readme: string; data: Record<string, Record<string, unknown>[]>; whole: string };
    for (const sec of ["instructor", "instructor_sections", "planning_requests", "teacher_preferences", "priority_notes", "audit_as_subject", "profile", "consents"]) {
      expect(names).toContain(`${sec}.json`);
      expect(readme).toContain(`${sec}.csv`);
    }
    expect(data.instructor!.map((i) => i.id)).toEqual([ctx.instructorId]);
    expect(data.planning_requests!.length).toBe(ctx.rows);
    const wishes = new Map(data.teacher_preferences!.map((w) => [w.id as number, w]));
    expect(wishes.get(ctx.wishes[0]!)).toMatchObject({ status: "accepted", decided_by: "Yönetici / administrator" });
    expect(wishes.get(ctx.wishes[1]!)).toMatchObject({ status: "rejected", reason_code: "capacity" });
    expect(String(wishes.get(ctx.wishes[1]!)!.reason)).toContain("[Yönetici]");
    expect(whole.toLowerCase()).not.toContain(ADMIN_EMAIL.toLowerCase());
    expect(whole).not.toContain(PHONE_USER.email);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("3. T-R1-29: a missing permission answers in Turkish", async () => {
  const r = await call<{ detail: { code: string; permission: string; message_tr: string; message_en: string } }>("GET", "/learning/suggestions", undefined, ctx.acadToken);
  expect(r.status).toBe(403);
  expect(r.body.detail).toMatchObject({ code: "forbidden", permission: "planning.view", message_tr: 'Bu işlem için "Planlama verilerini görme" izni gerekiyor' });
});

test.describe("phone 390", () => {
  test.use(PHONE);
  test("4. the notice gate is a bottom sheet with Okudum in thumb reach; Gizlilik fits a phone", async ({ page }) => {
    await signInAs(page, PHONE_USER.username, false);
    const gate = page.getByTestId("notice-gate");
    await expect(gate).toBeVisible();
    await expect(gate).toContainText(TR_TITLE);
    const vp = page.viewportSize()!;
    const box = (await gate.boundingBox())!;
    expect(Math.abs(box.y + box.height - vp.height)).toBeLessThanOrEqual(2);
    expect(box.width).toBeGreaterThanOrEqual(vp.width - 2);
    const ok = gate.getByTestId("notice-gate-ack");
    const b = (await ok.boundingBox())!;
    expect(b.y).toBeGreaterThanOrEqual(0.6 * vp.height - 1);
    expect(b.y + b.height).toBeLessThanOrEqual(vp.height);
    expect(b.height).toBeGreaterThanOrEqual(44);
    await ok.tap();
    await expect(gate).toBeHidden();
    // T-R1-28 / T-R1-12: the gate hands focus to the page's `[data-focus-fallback]` landmark, else #main; on a phone
    // /bookings has one (the free-slots title), so focus lands there, never on <body>
    await expect.poll(() => page.evaluate(() => (document.activeElement?.id === "main" || document.activeElement?.hasAttribute("data-focus-fallback")) ? "page" : document.activeElement?.id || document.activeElement?.tagName)).toBe("page");

    await page.goto("/profile#privacy");
    const section = page.getByTestId("privacy-section");
    await expect(section).toBeVisible();
    await noSideScroll(page);
    expect(await smallTargets(page, '[data-testid="privacy-section"]')).toEqual([]);
    const m03 = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('[data-testid="privacy-section"] input:not([type=checkbox]):not([type=radio]):not([type=hidden]), [data-testid="privacy-section"] select, [data-testid="privacy-section"] textarea')]
        .filter((i) => i.getBoundingClientRect().width && parseFloat(getComputedStyle(i).fontSize) < 16)
        .map((i) => i.dataset.testid || i.id),
    );
    expect(m03).toEqual([]);
  });
});
