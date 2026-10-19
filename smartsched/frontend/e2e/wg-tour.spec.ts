/**
 * WG-05 guided tour against the REAL backend (E2E_REAL=1).
 *
 * - Desktop, keyboard only: a new academician starts the tour from the sheet and finishes every step with Enter; the
 *   card is a modal dialog with "Adım n / N", the ring follows the target, Tab stays in the card, the shortcuts are
 *   paused (⌘K does nothing) and come back afterwards; "Bitir" → toast and focus on the page heading.
 * - Esc at step 2 ends the tour (`dismissed`), focus goes to the step's target or the heading, never to <body>.
 * - Phone, touch: the step card is docked at the bottom, 48 px buttons, M-01/M-02 inside the card.
 * - Approver: a staff member granted `approvals.decide` gets the approver steps (Onaylar) after Help › restart.
 * - Bundle: react-joyride is not loaded on /reserve until a tour starts.
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, focusNotBody, m01, m02, makeAcademician, makeTeacher, signIn, unlink, type Api } from "./wg-helpers";

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

let api: Api;
const linked: { id: number; instructorId: number | null }[] = [];
let approverRole: number | null = null;
test.beforeAll(async () => {
  api = await adminApi();
});
test.afterAll(async () => {
  for (const p of linked) await unlink(api, p);
  if (approverRole) await api.call("DELETE", `/roles/${approverRole}`);
  await api.ctx.dispose();
});

async function openSheet(page: Page) {
  await page.goto("/reserve");
  await expect(page.getByTestId("welcome-sheet")).toBeVisible({ timeout: 20_000 });
}

/** Total steps from the counter "Adım n / N". */
async function counter(page: Page): Promise<[number, number]> {
  const text = (await page.getByTestId("tour-counter").textContent()) ?? "";
  const m = /Adım (\d+) \/ (\d+)/.exec(text);
  return [Number(m?.[1]), Number(m?.[2])];
}

test("bundle: the tour library is not loaded on /reserve until a tour starts", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.tour.b");
  const { context, page } = await signIn(browser, p, DESKTOP);
  const scripts: { url: string; joyride: boolean }[] = [];
  page.on("response", async (r) => {
    if (r.request().resourceType() !== "script") return;
    const body = await r.text().catch(() => "");
    scripts.push({ url: r.url(), joyride: body.includes("react-joyride-portal") });
  });
  await openSheet(page);
  await page.waitForLoadState("networkidle");
  expect(scripts.filter((s) => s.joyride), "react-joyride in the first load of /reserve").toEqual([]);
  await page.getByTestId("welcome-start-tour").click();
  await expect(page.getByTestId("tour-card")).toBeVisible({ timeout: 15_000 });
  expect(scripts.some((s) => s.joyride)).toBe(true);
  await page.keyboard.press("Escape");
  await context.close();
});

test("desktop keyboard only: the academician's tour from the sheet to 'Bitir'", async ({ browser }) => {
  const ayse = await makeAcademician(api, "wg.tour.ac");
  linked.push(ayse);
  const { context, page } = await signIn(browser, ayse, DESKTOP);
  await openSheet(page);
  // reach "Kısa turu başlat" with Tab and press Enter
  for (let i = 0; i < 20; i++) {
    if (await page.getByTestId("welcome-start-tour").evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Enter");
  const card = page.getByTestId("tour-card");
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card).toHaveAttribute("role", "dialog");
  await expect(page.getByTestId("tour-ring")).toBeVisible();
  const [, total] = await counter(page);
  expect(total).toBeGreaterThanOrEqual(4);
  expect(total).toBeLessThanOrEqual(5);
  await expect(page.getByTestId("tour-live")).toHaveText(/^Adım 1 \/ \d: /);
  // the shortcuts are paused
  await page.keyboard.press("Control+k");
  await expect(page.getByPlaceholder(/Ara|Search/).first()).toBeHidden();
  // Tab stays in the card (non-interactive step)
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="tour-card"]'))).toBe(true);
  }
  let guard = 0;
  while (guard++ < 10) {
    const next = page.getByTestId("tour-next");
    await next.focus();
    const last = (await next.textContent())?.includes("Bitir");
    await page.keyboard.press("Enter");
    if (last) break;
    await expect(card).toBeVisible({ timeout: 10_000 });
  }
  await expect(card).toBeHidden({ timeout: 10_000 });
  await expect(page.getByText("Tur bitti. Başlarken listesi kenar çubuğunda.")).toBeVisible();
  await focusNotBody(page);
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog").filter({ has: page.locator("input") }).first()).toBeVisible();
  await context.close();
});

test("Esc at step 2 ends the tour and focus goes to the step's target or the heading", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.tour.esc");
  const { context, page } = await signIn(browser, p, DESKTOP);
  await openSheet(page);
  await page.getByTestId("welcome-start-tour").click();
  await expect(page.getByTestId("tour-card")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("tour-next").click();
  await expect.poll(async () => (await counter(page))[0]).toBe(2);
  const target = await page.getByTestId("tour-card").getAttribute("data-step");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tour-card")).toBeHidden();
  await expect(page.getByText("Tur kapatıldı. Yardım › Turu yeniden başlat ile dönebilirsiniz.")).toBeVisible();
  await focusNotBody(page);
  const focused = await page.evaluate(() => ({ tour: document.activeElement?.getAttribute("data-tour"), tag: document.activeElement?.tagName }));
  expect(focused.tour === target || focused.tag === "H1", JSON.stringify({ focused, target })).toBe(true);
  await context.close();
});

test("phone touch: the step card is docked at the bottom with 48 px buttons", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.tour.ph");
  const { context, page } = await signIn(browser, p, PHONE);
  await openSheet(page);
  await page.getByTestId("welcome-start-tour").tap();
  const card = page.getByTestId("tour-card");
  await expect(card).toBeVisible({ timeout: 15_000 });
  const box = (await card.boundingBox())!;
  expect(box.width).toBeGreaterThan(360);
  expect(box.y + box.height).toBeGreaterThan(844 * 0.5);
  expect(box.height).toBeLessThanOrEqual(844 * 0.45 + 2);
  expect((await page.getByTestId("tour-next").boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const one = await m01(page);
  expect(one.scrollWidth, JSON.stringify(one)).toBeLessThanOrEqual(one.vw);
  expect(await m02(page, '[data-testid="tour-card"]')).toEqual([]);
  for (let i = 0; i < 8; i++) {
    const next = page.getByTestId("tour-next");
    if (!(await next.isVisible().catch(() => false))) break;
    const last = (await next.textContent())?.includes("Bitir");
    await next.tap();
    if (last) break;
    await page.waitForTimeout(400);
  }
  await expect(card).toBeHidden({ timeout: 10_000 });
  await expect(page.getByText("Tur bitti. Başlarken listesi Diğer sekmesinde.")).toBeVisible();
  await context.close();
});

test("approver: after the grant, the delta sheet has only the approver card and the tour has the Onaylar steps", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.tour.ap", "İsmail");
  // the person sees the first sheet and closes it
  const first = await signIn(browser, p, DESKTOP);
  await openSheet(first.page);
  await first.page.getByTestId("welcome-start-tour").click();
  await expect(first.page.getByTestId("tour-card")).toBeVisible({ timeout: 15_000 });
  await first.page.keyboard.press("Escape");
  await first.context.close();
  // grant approvals.decide through a custom role (the TEACHER rights + approvals.decide)
  const roles = await api.json<{ id: number; code: string | null; permissions: string[] }[]>("GET", "/roles");
  const teacher = roles.find((r) => r.code === "TEACHER")!;
  const role = await api.json<{ id: number }>("POST", "/roles", { name: `WG onaylayıcı ${Date.now()}`, permissions: [...new Set([...teacher.permissions, "approvals.decide"])] });
  approverRole = role.id;
  await api.json("PUT", `/users/${p.id}`, { role_id: role.id });
  const { context, page } = await signIn(browser, p, DESKTOP);
  await openSheet(page);
  await expect(page.getByTestId("welcome-sheet-title")).toHaveText("Yeni yetkileriniz var");
  await expect(page.locator('[data-testid^="welcome-card-"]')).toHaveCount(1);
  await expect(page.getByTestId("welcome-card-approvals_inbox")).toBeVisible();
  await page.getByTestId("welcome-start-tour").click();
  const anchors: string[] = [];
  for (let i = 0; i < 6; i++) {
    const card = page.getByTestId("tour-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    anchors.push((await card.getAttribute("data-step")) ?? "");
    const next = page.getByTestId("tour-next");
    const last = (await next.textContent())?.includes("Bitir");
    await next.click();
    if (last) break;
    await page.waitForTimeout(300);
  }
  expect(anchors).toContain("nav-approvals");
  await context.close();
  await api.json("PUT", `/users/${p.id}`, { role: "TEACHER" }).catch(() => undefined);
});
