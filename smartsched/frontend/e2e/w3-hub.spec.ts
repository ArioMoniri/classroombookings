/**
 * Wave 3b, lane W3-HUB: the integrations gallery (/admin/integrations) on a real stack.
 *
 *  1. Admin, desktop 1440: reached from the admin navigation ("Entegrasyonlar"); Tümü shows six areas with one of the
 *     five Turkish status words per card and the summary line; the tabs are keyboard-operable and live in the URL; the
 *     guided Zapier setup saves a webhook (secret shown once, Kopyala → Kopyalandı in place), sends a test event and
 *     reports the outcome; Escape returns the focus to the card; the card then carries "Son değişiklik: <ad>"; the
 *     switch asks before switching off and calls the webhook's own endpoint.
 *  2. Organisation-wide: a second administrator reads the same status with the first one's name (IN-01); a teacher
 *     gets 403 from the API and no gallery.
 *  3. Phone 390 × 844 touch (tr-TR, Europe/Istanbul): MOBILE M-01 / M-02 / M-03 on the gallery and in the setup sheet,
 *     M-05 for the sheet's primary action, 64 px rows without switches (the switch is in the sheet).
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:19730 PW_PORT=19731 npx playwright test w3-hub
 */
import { expect, request as pwRequest, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const ADMIN2 = { email: `hub.admin2.${STAMP}@smartsched.local`, password: "Hub-2026!pw-admin2", full_name: "İkinci Yönetici" };
const TEACHER = { email: `hub.teacher.${STAMP}@smartsched.local`, password: "Hub-2026!pw-teacher" };
const ZAPIER = `https://hooks.zapier.com/hooks/catch/123456/${STAMP}/`;
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const WORDS = /^(Bağlı|Yapılandırılmadı|Hata|Kapalı|Bilinmiyor)$/;

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);

async function token(email: string, password: string): Promise<string> {
  const ctx = await pwRequest.newContext();
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const t = ((await r.json()) as { access_token: string }).access_token;
  await ctx.dispose();
  return t;
}

async function asUser(email: string, password: string) {
  return pwRequest.newContext({ extraHTTPHeaders: { Authorization: `Bearer ${await token(email, password)}` } });
}

test.beforeAll(async () => {
  const admin = await asUser(ADMIN_EMAIL, ADMIN_PASSWORD);
  for (const u of [
    { ...ADMIN2, role: "ADMIN" },
    { ...TEACHER, role: "TEACHER", full_name: "Hub Öğretmen" },
  ]) {
    const r = await admin.post(`${API}/users`, { data: u });
    expect(r.status(), await r.text()).toBe(201);
  }
  await admin.dispose();
});

type Card = { key: string; status: string; changed_by?: string | null; enabled?: boolean | null };
async function statusCards(email: string, password: string): Promise<Map<string, Card>> {
  const ctx = await asUser(email, password);
  const r = await ctx.get(`${API}/integrations/status`);
  expect(r.status(), await r.text()).toBe(200);
  const body = (await r.json()) as { areas: { cards: Card[] }[] };
  await ctx.dispose();
  return new Map(body.areas.flatMap((a) => a.cards).map((c) => [c.key, c]));
}

/** MOBILE.md M-01, M-02 (scrolled in 0.8 × viewport steps, inside `scope` when given), M-03. */
async function mobileChecks(page: Page, scope = "body") {
  return page.evaluate(async (scope) => {
    const root = document.querySelector(scope) ?? document.body;
    const vw = document.documentElement.clientWidth;
    window.scrollTo(10000, window.scrollY);
    const scrolledX = window.scrollX;
    window.scrollTo(0, window.scrollY);
    const off: string[] = [];
    for (const el of root.querySelectorAll("*")) {
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || cs.position === "fixed") continue;
      if (r.right <= vw + 1 && r.left >= -1) continue;
      let p = el.parentElement, contained = false;
      while (p && p !== document.body) {
        if (getComputedStyle(p).overflowX !== "visible") { contained = true; break; }
        p = p.parentElement;
      }
      if (!contained) off.push(`${el.tagName}${(el as HTMLElement).dataset.testid ? `[${(el as HTMLElement).dataset.testid}]` : ""}`);
    }
    const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[tabindex]:not([tabindex="-1"])';
    const hits = (el: Element, x: number, y: number) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
    const bad = new Set<string>();
    const scrollers = [document.scrollingElement!, ...root.querySelectorAll("*")].filter((e) => e.scrollHeight > e.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(e).overflowY) || e === document.scrollingElement);
    const VH = document.documentElement.clientHeight;
    const maxH = Math.max(...scrollers.map((s) => s.scrollHeight));
    for (let y = 0; y <= maxH; y += Math.floor(VH * 0.8)) {
      scrollers.forEach((s) => (s.scrollTop = y));
      await new Promise((r) => setTimeout(r, 60));
      for (const el of root.querySelectorAll(SEL)) {
        const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
        if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
        if ((el as HTMLElement).checkVisibility && !(el as HTMLElement).checkVisibility()) continue;
        if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
        if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
        let w = r.width, h = r.height;
        const lab = (el as HTMLInputElement).labels?.[0];
        if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
        if (w >= 44 && h >= 44) continue;
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        if (!(cy > 22 && cy < VH - 22 && cx > 22 && cx < vw - 22)) continue; // measured at another scroll step
        if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, yy]) => hits(el, x, yy))) continue;
        bad.add(`${((el as HTMLElement).dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40)} ${Math.round(w)}×${Math.round(h)}`);
      }
    }
    scrollers.forEach((s) => (s.scrollTop = 0));
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue!.trim() ? 1 : 2) });
    const small: string[] = [];
    while (tw.nextNode()) {
      const el = tw.currentNode.parentElement!, cs = getComputedStyle(el), r = el.getBoundingClientRect();
      if (!r.width || r.width <= 1 || cs.visibility === "hidden" || el.closest(".sr-only,[data-allow-small-text]")) continue;
      if (parseFloat(cs.fontSize) < 11) small.push(`${el.textContent!.trim().slice(0, 30)} ${cs.fontSize}`);
    }
    const inputs = [...root.querySelectorAll("input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea")]
      .filter((i) => i.getBoundingClientRect().width > 1 && !i.closest(".sr-only") && (!(i as HTMLElement).checkVisibility || (i as HTMLElement).checkVisibility()) && parseFloat(getComputedStyle(i).fontSize) < 16)
      .map((i) => (i as HTMLElement).dataset.testid || i.id);
    return { zoom: [innerWidth, vw], scrollWidth: document.scrollingElement!.scrollWidth, vw, scrolledX, offenders: off.slice(0, 15), small: small.slice(0, 15), touch: [...bad], inputsUnder16: inputs };
  }, scope);
}

test("1. admin desktop 1440: navigation, areas, keyboard tabs, guided Zapier setup, focus back, switch through the owner", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/dashboard");
  await page.getByRole("link", { name: "Entegrasyonlar" }).first().click();
  await expect(page).toHaveURL(/\/admin\/integrations$/);
  await expect(page.getByRole("heading", { name: "Entegrasyonlar", level: 1 })).toBeVisible();
  const gallery = page.getByTestId("integrations-gallery");
  await expect(page.getByTestId("integrations-summary")).toContainText(/\d+ bağlı · \d+ hata · \d+ yapılandırılmadı/);
  for (const area of ["Kimlik", "E-posta", "Takvim", "Kanallar", "Webhook ve otomasyon", "Yapay zekâ"]) {
    await expect(gallery.getByRole("heading", { name: area, level: 2 })).toBeVisible();
  }
  const words = await gallery.getByTestId("connector-status").allTextContents();
  expect(words.length).toBeGreaterThanOrEqual(12);
  for (const w of words) expect(w.trim()).toMatch(WORDS);
  await expect(gallery).not.toContainText(/integrations\.|not_configured|W3-|integration_status/);
  await expect(gallery.locator("article").first()).toContainText(/Son değişiklik|Henüz değişiklik yok/);

  // keyboard: the tab list moves with the arrow keys and opens with Enter; the URL follows
  await page.getByTestId("integrations-tab-all").focus();
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("integrations-tab-automation")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/area=automation/);
  await expect(page.getByTestId("connector-email.smtp")).toHaveCount(0);

  // guided setup: Zapier
  const zap = page.getByTestId("connector-automation.zapier");
  await zap.getByRole("button", { name: "Zapier: kur" }).click();
  const sheet = page.getByTestId("setup-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByTestId("setup-title")).toBeFocused();
  await expect(sheet).toContainText("Catch Raw Hook");
  await sheet.getByTestId("guided-url").fill(ZAPIER);
  await sheet.getByTestId("guided-save").click();
  const secret = sheet.getByTestId("guided-secret");
  await expect(secret.getByRole("textbox")).toHaveValue(/^whsec_/);
  await expect(sheet).toContainText("Bu anahtar yalnızca şimdi gösterilir.");
  await secret.getByTestId("guided-secret-copy").click();
  await expect(secret.getByTestId("guided-secret-copy")).toHaveText(/Kopyalandı/);
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^whsec_/);
  await sheet.getByTestId("guided-test").click();
  await expect(sheet.getByTestId("guided-result")).toHaveText(/Test olayı (ulaştı|ulaşmadı)/, { timeout: 60_000 });
  await expect(sheet.getByTestId("guided-result")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
  await expect(zap.getByTestId("connector-primary")).toBeFocused();
  await expect(zap.getByTestId("connector-status")).not.toHaveText("Yapılandırılmadı");
  await expect(zap).toContainText(/Son değişiklik: .+, /);
  await expect(zap).toContainText(/Son kontrol: /);

  // the switch: off asks first, then PUT /webhooks/{id} {active: false}
  const sw = zap.getByRole("switch", { name: "Zapier: Kullanımda" });
  await expect(sw).toBeChecked();
  const put = page.waitForRequest((r) => r.method() === "PUT" && /\/api\/v1\/webhooks\/\d+$/.test(r.url()));
  await sw.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("Zapier kapatılsın mı?");
  await dialog.getByRole("button", { name: "Kapat" }).first().click();
  expect((await put).postDataJSON()).toEqual({ active: false });
  await expect(zap.getByTestId("connector-status")).toHaveText("Kapalı");
  await expect(zap.getByTestId("connector-primary")).toBeFocused();
});

test("2. organisation-wide: a second admin sees the same card and who changed it; a teacher gets nothing", async ({ browser }) => {
  const mine = await statusCards(ADMIN_EMAIL, ADMIN_PASSWORD);
  const theirs = await statusCards(ADMIN2.email, ADMIN2.password);
  const a = mine.get("automation.zapier")!, b = theirs.get("automation.zapier")!;
  expect(b.status).toBe(a.status);
  expect(b.changed_by).toBeTruthy();
  expect(b.changed_by).toBe(a.changed_by);
  expect(b.enabled).toBe(false);
  // the gallery in the second admin's browser
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await login(p2, ADMIN2.email, ADMIN2.password);
  await p2.goto("/admin/integrations?area=automation");
  await expect(p2.getByTestId("connector-automation.zapier")).toContainText(`Son değişiklik: ${b.changed_by}`);
  await ctx.close();
  // teacher: 403 and no gallery
  const t = await asUser(TEACHER.email, TEACHER.password);
  expect((await t.get(`${API}/integrations/status`)).status()).toBe(403);
  await t.dispose();
  const tc = await browser.newContext();
  const tp = await tc.newPage();
  await login(tp, TEACHER.email, TEACHER.password);
  await tp.goto("/admin/integrations");
  await expect(tp.getByTestId("integrations-gallery")).toHaveCount(0);
  await tc.close();
});

test("3. phone 390 touch: M-01/02/03 on the gallery and the sheet, M-05 for the sheet's primary action, rows open the sheet", async ({ browser }) => {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  await login(page);
  await page.goto("/admin/integrations");
  await expect(page.getByTestId("integrations-summary")).toBeVisible();
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
  const g = await mobileChecks(page, '[data-testid="integrations-gallery"]');
  expect(g.zoom[0]).toBe(g.zoom[1]);
  expect({ M01: g.offenders, sw: g.scrollWidth <= g.vw, x: g.scrolledX }).toEqual({ M01: [], sw: true, x: 0 });
  expect(g.touch, "M-02").toEqual([]);
  expect(g.small, "M-03 text").toEqual([]);
  expect(g.inputsUnder16, "M-03 inputs").toEqual([]);
  // rows: 64 px, no switches on the gallery
  const row = page.getByTestId("connector-channels.telegram");
  expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(64);
  await expect(page.getByTestId("integrations-gallery").getByRole("switch")).toHaveCount(0);

  // the guided setup sheet: full screen, one step per screen, sticky primary in thumb reach
  await page.goto("/admin/integrations?area=automation&setup=automation.pipedream");
  const sheet = page.getByTestId("setup-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByTestId("guided-step")).toHaveText("Adım 1 / 4");
  const vp = page.viewportSize()!;
  const box = (await sheet.boundingBox())!;
  expect(Math.abs(box.y + box.height - vp.height)).toBeLessThanOrEqual(2);
  expect(box.width).toBeGreaterThanOrEqual(vp.width - 2);
  await sheet.getByTestId("guided-next").click();
  await expect(sheet.getByTestId("guided-step")).toHaveText("Adım 2 / 4");
  const s = await mobileChecks(page, '[data-testid="setup-sheet"]');
  expect({ M01: s.offenders, M02: s.touch, M03: s.small, inputs: s.inputsUnder16 }).toEqual({ M01: [], M02: [], M03: [], inputs: [] });
  const primary = sheet.getByTestId("guided-save");
  for (const y of [0, 400, 1e6]) {
    await page.evaluate((y) => document.querySelectorAll('[data-testid="setup-sheet-body"]').forEach((e) => (e.scrollTop = y)), y);
    await page.waitForTimeout(150);
    const b = (await primary.boundingBox())!;
    const free = await primary.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === el || el.contains(t); });
    expect({ y, top: b.y >= 0.6 * vp.height - 1, bottom: b.y + b.height <= vp.height, free }).toEqual({ y, top: true, bottom: true, free: true });
  }
  await sheet.getByTestId("setup-back").click();
  await expect(sheet).toHaveCount(0);

  // a row opens the connector's sheet; the "Kullanımda" switch lives there
  await page.getByTestId("integrations-tab-automation").click();
  await page.getByTestId("connector-automation.zapier").click();
  await expect(page.getByTestId("setup-sheet").getByRole("switch", { name: "Zapier: Kullanımda" })).toBeVisible();
  await ctx.close();
});
