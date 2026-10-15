import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, api, login, solverRun } from "./helpers";

/**
 * Frontend sweep 2026-10-15 (ledger frontend-sweep-studio-calendar-2026-10-15) against the REAL backend:
 * keyboard on class chips (M-16), focus after closing the inspector (T4), deferred week navigation (T2/T3),
 * the focus ring (U-01), the run report's verdict and publish dialog (M-03, M-06..M-08) and the Studio preset
 * menu (M-12). Start the e2e backend (playwright.config.ts), then:
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test e2e/studio-calendar-sweep.spec.ts
 */
test.skip(!REAL, SKIP_REASON);
test.use({ locale: "en-GB", timezoneId: "Europe/Istanbul", viewport: { width: 1440, height: 900 } });

async function english(page: Page) {
  const base = test.info().project.use.baseURL ?? "http://127.0.0.1:3100";
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: "en", url: base }]);
}

async function openTimetable(page: Page) {
  await english(page);
  await login(page);
  await page.goto(`/timetable?run=${solverRun()}&lens=board&board=day&week=3&day=2`);
  await expect(page.getByTestId("time-grid")).toBeVisible({ timeout: 30_000 });
}

test("a focused class chip: Enter opens its inspector, closing it returns focus to the chip (M-16, T4)", async ({ page }) => {
  await openTimetable(page);
  const chip = page.getByTestId("calendar-event").first();
  await chip.click();
  await chip.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("class-inspector")).toBeVisible();
  await expect(page.locator("[data-testid=quick-create]")).toHaveCount(0);
  const aid = await chip.getAttribute("data-assignment-id");
  await page.getByTestId("class-inspector").getByRole("button", { name: /close/i }).first().click();
  await expect(page.locator(":focus")).toHaveAttribute("data-assignment-id", aid ?? "");
});

test("week navigation: the title follows the click at once and the old grid is veiled while it renders (T2/T3)", async ({ page }) => {
  await english(page);
  await login(page);
  // the strip board steps by week (the day board steps by day inside the same week range)
  await page.goto(`/timetable?run=${solverRun()}&lens=board&board=strip&week=3`);
  await expect(page.getByTestId("calendar-title")).toBeVisible({ timeout: 30_000 });
  const title = page.getByTestId("calendar-title");
  const before = await title.textContent();
  // sample the title in the frame after the click: it must already show the next week
  const after = await page.evaluate(
    () =>
      new Promise<string>((resolve) => {
        (document.querySelector("[data-testid=week-next]") as HTMLButtonElement).click();
        requestAnimationFrame(() => resolve(document.querySelector("[data-testid=calendar-title]")?.textContent ?? ""));
      }),
  );
  expect(after).not.toBe(before);
  await expect(page.getByTestId("calendar-canvas")).not.toHaveAttribute("data-stale", "");
  await expect(page.getByTestId("stale-veil")).toHaveCount(1);
});

test("keyboard focus draws a visible ring (U-01)", async ({ page }) => {
  await openTimetable(page);
  await page.keyboard.press("Tab");
  const scrubber = page.getByRole("slider").first();
  await scrubber.focus();
  const style = await scrubber.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(style).not.toBe("none");
});

test("run report: an honest verdict, and Publish asks first with the scope (M-03, M-06..M-08)", async ({ page }) => {
  await english(page);
  await login(page);
  const id = solverRun();
  const run = await api<{ is_active: boolean; status: string }>(page, `/runs/${id}`);
  await page.goto(`/runs/${id}`);
  const verdict = page.getByTestId("run-verdict");
  await expect(verdict).toBeVisible({ timeout: 30_000 });
  const state = await verdict.getAttribute("data-state");
  if (state === "complete") await expect(verdict).toContainText("no rule is broken");
  else expect(state).toMatch(/partial|exceptions|failed/);
  if (run.is_active) {
    await expect(page.getByTestId("run-published")).toBeVisible();
    return;
  }
  if (!/^(FEASIBLE|OPTIMAL|FEASIBLE_PARTIAL)$/.test(run.status)) return;
  await page.getByTestId("run-publish").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/whole term|weeks/);
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
});

test("Studio: the preset menu opens without crashing the page (M-12)", async ({ page }) => {
  await english(page);
  await login(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/generate");
  await page.getByTestId("preset-menu").first().click({ timeout: 30_000 });
  await expect(page.getByRole("menu")).toBeVisible();
  expect(errors).toEqual([]);
});
