/**
 * Wave 3, lane W3-OPS: the operations panel (/admin/ops) on a real stack. No Grafana / Prometheus / Loki is needed:
 * the reachability of those three is mocked by patching the `GET /api/v1/ops/status` and `/ops/dashboards` answers
 * in the browser (every other number comes from the real backend).
 *
 *  1. Admin, desktop 1440: the service cards in Turkish (API + DB "Çalışıyor"), Grafana mocked up -> its card and
 *     dashboard links enabled; a browser error report (POST /api/v1/ops/errors, PII in it) appears as one scrubbed
 *     group, twice -> "2 kez"; "Çözüldü" moves it out of "Yeni" and the focus lands on the list heading.
 *  2. Forward-auth for /grafana/ through the Next proxy: admin 204, teacher 403, signed out 401.
 *  3. Phone 390 × 844 touch: no sideways scroll, every control in the panel >= 44 px (or a 44 px hit area), inputs
 *     >= 16 px; a teacher gets the no-access text, not the panel.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test w3-ops
 */
import { expect, request as pwRequest, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { email: `ops.teacher.${STAMP}@smartsched.local`, password: "Ops-2026!pw-teacher" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

async function token(email: string, password: string): Promise<string> {
  const ctx = await pwRequest.newContext();
  const r = await ctx.post(`${API}/auth/login`, { data: { email, password } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const t = ((await r.json()) as { access_token: string }).access_token;
  await ctx.dispose();
  return t;
}

test.beforeAll(async () => {
  const admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  const ctx = await pwRequest.newContext({ extraHTTPHeaders: { Authorization: `Bearer ${admin}` } });
  const r = await ctx.post(`${API}/users`, { data: { email: TEACHER.email, role: "TEACHER", password: TEACHER.password, full_name: "Ops Öğretmen" } });
  expect(r.status(), await r.text()).toBe(201);
  await ctx.dispose();
});

/** Grafana, Prometheus and Loki "reachable" without running them (status + dashboards answers patched in the browser). */
async function mockReachability(page: Page): Promise<void> {
  const up = { configured: true, reachable: true, status: "ok", latency_ms: 3 };
  await page.route("**/api/v1/ops/status", async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { services: Record<string, unknown> };
    body.services = { grafana: up, prometheus: up, loki: up };
    await route.fulfill({ response: res, json: body });
  });
  await page.route("**/api/v1/ops/dashboards", async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { grafana: Record<string, unknown> };
    body.grafana = { ...up, path: "/grafana/" };
    await route.fulfill({ response: res, json: body });
  });
  // the embedded panels would load Grafana itself: an empty same-origin page stands in for it
  await page.route("**/grafana/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>grafana</title>" }));
}

/** one error group per run: the group key is the in-app frames (app.core.observability.fingerprint), so the frame
 *  carries the run's stamp (a retry or a second run on the same database is a new group, not the old one's count) */
async function report(page: Page, message: string): Promise<number> {
  return page.evaluate(async ([message, fn]) => {
    const r = await fetch("/api/v1/ops/errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, kind: "TypeError", stack: `TypeError: ${message}\n    at ${fn} (https://x/_next/static/chunks/app/page-1a2b3c4d.js:1:2)`, url: `${location.origin}/rooms/12?q=Ahmet`, origin: "window.onerror" }),
    });
    return r.status;
  }, [message, `OpsE2E_${STAMP}`] as const);
}

test("1. admin desktop: cards, mocked Grafana, a scrubbed browser error group resolved with the focus kept", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await mockReachability(page);
  const marker = `w3ops-e2e-${STAMP}`;
  expect(await report(page, `${marker} for ayse.yilmaz@uni.edu.tr`)).toBe(202);
  expect(await report(page, `${marker} for ayse.yilmaz@uni.edu.tr`)).toBe(202);

  await page.goto("/admin/ops");
  await expect(page.getByRole("heading", { name: "Operasyon", level: 1 })).toBeVisible();
  await expect(page.getByTestId("ops-card-api")).toHaveAttribute("data-status", "ok");
  await expect(page.getByTestId("ops-card-api")).toContainText("Çalışıyor");
  await expect(page.getByTestId("ops-card-db")).toHaveAttribute("data-status", "ok");
  await expect(page.getByTestId("ops-card-grafana")).toHaveAttribute("data-status", "ok");
  await expect(page.getByTestId("ops-card-grafana")).toContainText("Ulaşılıyor");
  await expect(page.getByTestId("ops-dash-smartsched-health")).toHaveAttribute("href", /^\/grafana\/d\/smartsched-health\//);
  await expect(page.getByTestId("ops-dash-smartsched-health")).not.toHaveAttribute("aria-disabled", "true");
  await expect(page.getByTestId("ops-chart-summary")).toContainText("istek");

  // CH12-F04 / E2EA-F09: a group reads as one plain line; its class, message and stack wait behind "Ayrıntı", so the
  // group is found by its id (the API's own list) and opened
  const groupsOf = () => page.evaluate(async (m) => ((await (await fetch("/api/v1/ops/errors")).json()) as { items: { id: number | string; message: string }[] }).items.filter((g) => g.message.includes(m)), marker);
  await expect.poll(async () => (await groupsOf()).length).toBe(1);
  const group = await groupsOf();
  const row = page.getByTestId(`ops-error-${group[0]!.id}`);
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("2 kez");
  await row.getByTestId(`ops-error-toggle-${group[0]!.id}`).click();
  await expect(row.getByTestId(`ops-error-stack-${group[0]!.id}`)).toContainText(marker);
  await expect(row).toContainText("[email]");
  await expect(row).not.toContainText("ayse.yilmaz");
  await expect(row).toContainText("/rooms/:id");
  await row.getByRole("button", { name: "Çözüldü" }).click();
  await expect(page.getByText("Çözüldü olarak işaretlendi.")).toBeVisible();
  await expect(row).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Hata grupları" })).toBeFocused();
  // no raw keys or enum values on the Turkish page
  await expect(page.getByTestId("ops-panel")).not.toContainText(/ops\.|acknowledged|unmanaged|http_5/);
});

test("2. /grafana/ forward-auth through the Next proxy: admin 204, teacher 403, signed out 401", async ({ page, browser }) => {
  await login(page);
  const admin = await page.evaluate(async () => (await fetch("/api/v1/ops/grafana-auth")).status);
  expect(admin).toBe(204);
  const anon = await browser.newContext();
  const anonPage = await anon.newPage();
  await anonPage.goto("/login");
  expect(await anonPage.evaluate(async () => (await fetch("/api/v1/ops/grafana-auth")).status)).toBe(401);
  await anon.close();
  const t = await browser.newContext();
  const tp = await t.newPage();
  await login(tp, TEACHER.email, TEACHER.password);
  expect(await tp.evaluate(async () => (await fetch("/api/v1/ops/grafana-auth")).status)).toBe(403);
  await tp.goto("/admin/ops");
  await expect(tp.getByTestId("ops-panel")).toHaveCount(0);
  await t.close();
});

test("3. phone 390 touch: no sideways scroll, 44 px controls, 16 px inputs", async ({ browser }) => {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  await login(page);
  await mockReachability(page);
  await page.goto("/admin/ops");
  await expect(page.getByTestId("ops-card-api")).toHaveAttribute("data-status", "ok");
  await page.getByTestId("ops-logs-fetch").scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
  const result = await page.evaluate(async () => {
    const vw = document.documentElement.clientWidth;
    const sideways = document.scrollingElement!.scrollWidth > vw;
    const panel = document.querySelector('[data-testid="ops-panel"]')!;
    const SEL = "a[href],button,input,select,textarea,[role=tab]";
    const hits = (el: Element, x: number, y: number) => {
      const t = document.elementFromPoint(x, y);
      return !!t && (t === el || el.contains(t));
    };
    const small: string[] = [];
    const VH = document.documentElement.clientHeight;
    for (let y = 0; y < document.documentElement.scrollHeight; y += Math.floor(VH * 0.8)) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 80));
      for (const el of panel.querySelectorAll(SEL)) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height || (el as HTMLElement).checkVisibility?.() === false || el.closest('[aria-hidden="true"]')) continue;
        if (r.width >= 44 && r.height >= 44) continue;
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        if (cy < 22 || cy > VH - 22) continue; // measured on another scroll step
        if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, yy]) => hits(el, x, yy))) continue;
        small.push(`${(el as HTMLElement).dataset.testid ?? el.textContent?.trim().slice(0, 20)} ${Math.round(r.width)}×${Math.round(r.height)}`);
      }
    }
    const inputs = [...panel.querySelectorAll("input,select,textarea")].filter((i) => i.getBoundingClientRect().width > 1 && parseFloat(getComputedStyle(i).fontSize) < 16).map((i) => (i as HTMLElement).dataset.testid ?? i.tagName);
    return { sideways, small: [...new Set(small)], inputs };
  });
  expect(result.sideways).toBe(false);
  expect(result.small).toEqual([]);
  expect(result.inputs).toEqual([]);
  await ctx.close();
});
