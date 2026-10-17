/**
 * Flow loop round 2, lane D (moderation console, learning, re-solve preview; docs/ROADMAP.md "Flow loop tickets —
 * round 2", T-R2-23) against the REAL backend (E2E_REAL=1) with a published 2026-GUZ run:
 *
 * 1. "Önizleme oluştur" from the re-solve sheet: the "Yeniden çözüm #n başladı" toast must not sit over the sticky
 *    footer's "Onayla ve yayınla" while the pointer rests where the sheet's button was (Sonner pauses a hovered
 *    toast forever; the e2e gate burned 17 min on it twice). The toast is gone once the preview renders, and
 *    `preview-publish` is clickable right away.
 * 2. T-R2-23 (R2-M-02): publishing the preview shows "Yayınlandı: #N artık geçerli plan", the state "✓ Yayında" and
 *    no English schema text, although the server's activate body carries nested stats; afterwards focus is on the
 *    "✓ Yayında" status, never on <body> (round 3, R3-M-06). The published run G0 is restored at the end.
 * 3. Round 3 R3-M-06: a SECTION priority saved from the matching inspector (`p` on an Eşleşmeler row, "Tüm şube")
 *    returns focus to that row, never to <body>.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19340 NEXT_PUBLIC_API_URL=http://127.0.0.1:19340 PW_PORT=19341 \
 *     npx playwright test e2e/loop-r2-laneD.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const RESOLVE_WAIT = 12 * 60_000; // a shared, loaded host: the 60 s solve plus its diff can take minutes

test.describe.configure({ mode: "serial", timeout: 20 * 60_000 });
test.skip(!REAL, SKIP_REASON);
test.use({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

const ctx = {} as { api: APIRequestContext; token: string; g0: number };
type Run = { id: number; term_code: string; kind: string; is_active: boolean };

async function api<T>(method: "GET" | "POST", p: string, body?: unknown): Promise<T> {
  const res = await ctx.api.fetch(`${API}${p}`, { method, data: body, headers: { Authorization: `Bearer ${ctx.token}` } });
  expect(res.ok(), `${method} ${p} → ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  expect(res.ok()).toBeTruthy();
  ctx.token = ((await res.json()) as { access_token: string }).access_token;
  const runs = await api<Run[]>("GET", "/runs");
  const g0 = runs.find((r) => r.term_code === "2026-GUZ" && r.kind === "COURSE" && r.is_active);
  test.skip(!g0, "needs a published 2026-GUZ course run (scripts/record/stack.sh runs)");
  ctx.g0 = g0!.id;
});
test.afterAll(async () => {
  if (ctx.g0) await ctx.api.post(`${API}/runs/${ctx.g0}/activate`, { data: { confirm_scope_reduction: true, notify_people: false }, headers: { Authorization: `Bearer ${ctx.token}` } });
  await ctx.api?.dispose();
});

test("the started toast never covers 'Onayla ve yayınla'; the preview publishes with the real activate body (T-R2-23)", async ({ page }) => {
  await login(page);
  await page.goto("/moderation?tab=matchings");
  await page.getByTestId("recreate-open").click();
  const sheet = page.getByTestId("recreate-sheet");
  await sheet.getByRole("radio", { name: /60 sn/ }).or(sheet.getByText("60 sn")).first().click();
  await sheet.getByTestId("recreate-start").click(); // the pointer stays here: bottom-right, where Sonner stacks its toasts
  await expect(page.getByText(/Yeniden çözüm #\d+ başladı/)).toBeVisible();
  await expect(page).toHaveURL(/\/moderation\/recreate\/\d+/);
  const runId = Number(page.url().match(/recreate\/(\d+)/)![1]);
  const publish = page.getByTestId("preview-publish");
  await expect(publish).toBeVisible({ timeout: RESOLVE_WAIT });
  // right after the preview renders: the toast is gone and the button is clickable where the pointer rests
  await expect(page.getByText(/Yeniden çözüm #\d+ başladı/)).toBeHidden({ timeout: 5_000 });
  await expect(publish).toBeEnabled({ timeout: 30_000 });
  await publish.click({ trial: true, timeout: 5_000 });
  await expect(page.getByTestId("preview-state")).toHaveText(/Yayında değil/);

  // T-R2-23: publish; the body's nested stats must not turn the success into "Invalid response …"
  await publish.click();
  const dialog = page.getByTestId("publish-dialog");
  if (await dialog.getByTestId("publish-losses").isVisible()) await dialog.getByTestId("publish-losses-ack").check();
  const notify = dialog.getByTestId("notify-toggle");
  if ((await notify.isVisible()) && (await notify.getAttribute("aria-checked")) === "true") await notify.click(); // no mail sink here
  await dialog.getByTestId("publish-confirm").click();
  await expect(page.getByText(new RegExp(`Yayınlandı: #${runId} artık geçerli plan`))).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("preview-state")).toHaveText(/✓ Yayında/, { timeout: 30_000 });
  await expect(page.getByText(/Invalid response|Invalid input|schema mismatch/)).toHaveCount(0);
  await expect(page.getByTestId("publish-refused")).toHaveCount(0);
  // R3-M-06: the publish button is gone with the dialog; focus is on the status, not on <body>
  await expect(page.getByTestId("preview-state")).toBeFocused({ timeout: 5_000 });
  const runs = await api<Run[]>("GET", "/runs");
  expect(runs.find((r) => r.id === runId)?.is_active).toBe(true);
});

test("a section priority saved in the inspector returns focus to its row (R3-M-06)", async ({ page }) => {
  await login(page);
  await page.goto("/moderation?tab=matchings");
  await page.getByTestId("chip-all").click();
  await page.getByTestId("moderation-search").fill("PSY 277");
  const row = page.getByTestId("matchings-table").getByTestId("mod-row").first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  const rowId = await row.getAttribute("data-row-id");
  await row.focus();
  await page.keyboard.press("p");
  const insp = page.getByTestId("matching-inspector");
  await insp.getByText("Tüm şube", { exact: true }).first().click();
  await insp.getByTestId("priority-save").click();
  await expect(page.getByText(/PSY 277.*öncelik kaydedildi/).first()).toBeVisible({ timeout: 15_000 });
  await expect(insp).toBeHidden();
  await expect.poll(() => page.evaluate(() => (document.activeElement as HTMLElement | null)?.closest("[data-row-id]")?.getAttribute("data-row-id") ?? document.activeElement?.tagName), { timeout: 5_000 }).toBe(rowId);
  // and after the toast is gone, too (the sheet's own focus return comes after its exit animation)
  await page.waitForTimeout(1_000);
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
});
