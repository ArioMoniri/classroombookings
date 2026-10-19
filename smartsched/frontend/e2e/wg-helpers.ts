/**
 * Shared helpers for the welcome-guide specs (e2e/wg-*.spec.ts, WG-04…WG-08) against the REAL backend (E2E_REAL=1).
 * Every spec makes its own accounts (a stamp per run), so a fresh first sign-in is real: the server's
 * `welcome_progress` has no row for them yet.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19780 NEXT_PUBLIC_API_URL=http://127.0.0.1:19780 PW_PORT=19781 \
 *     npx playwright test e2e/wg-*.spec.ts --output=<scratch>
 */
import { expect, request as pwRequest, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, login } from "./helpers";

export const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
export const DESKTOP = { viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
export const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
export const PASSWORD = "Rehber-2026!";
let seq = 0;
export const stamp = () => `${Date.now().toString(36)}${(seq++).toString(36)}`;

export interface Api {
  ctx: APIRequestContext;
  token: string;
  call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token?: string): Promise<{ status: number; body: T }>;
  json<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token?: string): Promise<T>;
  tokenFor(username: string, password?: string): Promise<string>;
}

export async function adminApi(): Promise<Api> {
  const ctx = await pwRequest.newContext();
  const tokenFor = async (identifier: string, password = PASSWORD) => {
    const res = await ctx.post(`${API}/auth/login`, { data: identifier.includes("@") ? { email: identifier, password } : { username: identifier, password } });
    expect(res.ok(), await res.text()).toBeTruthy();
    return ((await res.json()) as { access_token: string }).access_token;
  };
  const token = await tokenFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  const call = async <T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, tk = token) => {
    const res = await ctx.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${tk}` } });
    const text = await res.text();
    let parsed: unknown = text;
    try {
      parsed = text ? JSON.parse(text) : undefined;
    } catch {
      /* not JSON */
    }
    return { status: res.status(), body: parsed as T };
  };
  const json = async <T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, tk = token) => {
    const r = await call<T>(method, path, body, tk);
    if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
    return r.body;
  };
  return { ctx, token, call, json, tokenFor };
}

export interface Person {
  id: number;
  username: string;
  email: string;
  password: string;
}

/** A TEACHER account (staff unless linked to an instructor), Turkish profile. */
export async function makeTeacher(api: Api, prefix: string, first = "Pelin"): Promise<Person> {
  const s = stamp();
  const p = { username: `${prefix}.${s}`, email: `${prefix}.${s}@uni.edu.tr`, password: PASSWORD };
  const made = await api.json<{ id: number }>("POST", "/users", { ...p, firstname: first, lastname: "Test", role: "TEACHER" });
  await api.json("PUT", "/auth/profile", { language: "tr" }, await api.tokenFor(p.username));
  return { id: made.id, ...p };
}

/** An academician: a TEACHER linked to an instructor nobody is linked to yet (null when the term has none). */
export async function makeAcademician(api: Api, prefix: string, first = "Ayşe"): Promise<Person & { instructorId: number | null }> {
  const t = await makeTeacher(api, prefix, first);
  const me = await api.json<{ current_term: { id: number } | null }>("GET", "/moderation/me");
  let instructorId: number | null = null;
  if (me.current_term) {
    const people = await api.json<{ items: { id: number; linked_user: boolean }[] }>("GET", `/terms/${me.current_term.id}/moderation/people`);
    instructorId = people.items.find((x) => !x.linked_user)?.id ?? null;
    if (instructorId) await api.json("PUT", `/auth/sso/admin/users/${t.id}/instructor`, { instructor_id: instructorId });
  }
  return { ...t, instructorId };
}

export async function unlink(api: Api, p: { id: number; instructorId: number | null }) {
  if (p.instructorId) await api.call("PUT", `/auth/sso/admin/users/${p.id}/instructor`, { instructor_id: null });
}

export async function welcomeOf(api: Api, p: Person) {
  return api.json<{ audiences: string[]; primary: string; show: { kind: string; key?: string } | null; hints: { key: string }[]; checklist: { items: { key: string; done: boolean }[] } }>("GET", "/welcome?first_route=/reserve", undefined, await api.tokenFor(p.username));
}

export async function settings(api: Api, body: Record<string, unknown>) {
  return api.json("PUT", "/welcome/settings", body);
}

/** A fresh browser context signed in as `p` (the landing page is the role's home). */
export async function signIn(browser: Browser, p: Person | { username: string; password: string }, opts: Record<string, unknown> = DESKTOP): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext(opts);
  const page = await context.newPage();
  await login(page, p.username, p.password, { welcome: true });
  return { context, page };
}

/* ---------------------------------------------------------------- MOBILE.md checks (snippets verbatim in spirit) */

export async function m01(page: Page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const off: string[] = [];
    window.scrollTo(10000, window.scrollY);
    const scrolledX = window.scrollX;
    window.scrollTo(0, window.scrollY);
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || cs.position === "fixed") continue;
      if (r.right <= vw + 1 && r.left >= -1) continue;
      let p = el.parentElement;
      let contained = false;
      while (p && p !== document.body) {
        if (getComputedStyle(p).overflowX !== "visible") {
          contained = true;
          break;
        }
        p = p.parentElement;
      }
      if (!contained) off.push(`${el.tagName}${el.dataset.testid ? `[${el.dataset.testid}]` : ""} ${Math.round(r.left)}→${Math.round(r.right)}`);
    }
    return { scrollWidth: document.scrollingElement!.scrollWidth, vw, scrolledX, offenders: off.slice(0, 15) };
  });
}

/** M-02 inside `scope` (a dialog / the tour card) or the whole page. */
export async function m02(page: Page, scope = "body") {
  return page.evaluate((scopeSel) => {
    const root = document.querySelector(scopeSel) ?? document.body;
    const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
    const hits = (el: Element, x: number, y: number) => {
      const t = document.elementFromPoint(x, y);
      return !!t && (t === el || el.contains(t));
    };
    const bad: { el: string; w: number; h: number }[] = [];
    for (const el of root.querySelectorAll<HTMLElement>(SEL)) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
      if (el.checkVisibility && !el.checkVisibility()) continue;
      if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
      if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
      let w = r.width;
      let h = r.height;
      const lab = (el as HTMLInputElement).labels?.[0];
      if (lab) {
        const l = lab.getBoundingClientRect();
        w = Math.max(w, l.width);
        h = Math.max(h, l.height);
      }
      if (w >= 44 && h >= 44) continue;
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const VW = document.documentElement.clientWidth;
      const VH = document.documentElement.clientHeight;
      const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
      if (inView && [[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x!, y!))) continue;
      bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
    }
    return bad;
  }, scope);
}

export async function m03(page: Page) {
  return page.evaluate(() => {
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue?.trim() ? 1 : 2) });
    const small: { text: string; px: number }[] = [];
    while (tw.nextNode()) {
      const el = tw.currentNode.parentElement!;
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (!r.width || r.width <= 1 || cs.visibility === "hidden" || el.closest(".sr-only,[data-allow-small-text]")) continue;
      const px = parseFloat(cs.fontSize);
      if (px < 11) small.push({ text: (el.textContent ?? "").trim().slice(0, 30), px });
    }
    const inputs = [...document.querySelectorAll<HTMLElement>("input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea")]
      .filter((i) => i.getBoundingClientRect().width > 1 && !i.closest(".sr-only") && (!i.checkVisibility || i.checkVisibility()) && parseFloat(getComputedStyle(i).fontSize) < 16)
      .map((i) => (i as HTMLInputElement).name || i.id || i.dataset.testid || i.tagName);
    return { small: small.slice(0, 20), inputsUnder16: inputs };
  });
}

/** M-05 for a primary action that must sit in the bottom 40 % of the viewport and not be covered. */
export async function m05(page: Page, selector: string) {
  const btn = page.locator(selector).first();
  const vp = page.viewportSize()!;
  const b = await btn.boundingBox();
  const free = await btn.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return t === el || el.contains(t);
  });
  return { ok: !!b && b.y >= 0.6 * vp.height - 1 && b.y + b.height <= vp.height && free, top: b?.y, bottom: b ? b.y + b.height : null, free, vh: vp.height };
}

/** M-01, M-02 (in `scope`), M-03 at once; asserts and returns the readings. */
export async function mobileChecks(page: Page, scope = "body") {
  const [one, two, three] = [await m01(page), await m02(page, scope), await m03(page)];
  expect(one.scrollWidth, JSON.stringify(one)).toBeLessThanOrEqual(one.vw);
  expect(one.scrolledX).toBe(0);
  expect(two, JSON.stringify(two)).toEqual([]);
  expect(three.inputsUnder16, JSON.stringify(three)).toEqual([]);
  expect(three.small, JSON.stringify(three)).toEqual([]);
  return { m01: one, m02: two, m03: three };
}

/** Focus is never left on <body> after an action. */
export async function focusNotBody(page: Page) {
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName ?? "BODY")).not.toBe("BODY");
}
