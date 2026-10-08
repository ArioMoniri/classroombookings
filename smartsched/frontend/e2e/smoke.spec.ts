import { expect, test } from "@playwright/test";
import { FINISHED, PLANNING_LIST, REAL, SKIP_REASON, api, boardRun, login, solverRun, type Run } from "./helpers";

/**
 * Smoke flows on the REAL backend with the Bahar 2026 fixtures (E2E_REAL=1; no mock API, no AI key):
 * signed-out guard + public pages → import the real planning list → classes → calendar → run report →
 * settings; the Generator Studio end to end; the phone layouts. The e2e stack is
 * smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh (see playwright.config.ts).
 */
test.skip(!REAL, SKIP_REASON);

test.describe("SmartSched smoke (real backend)", () => {
  test("signed out: app routes go to /login; /reset-password and /setup stay public", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/rooms");
    await expect(page).toHaveURL(/\/login\?next=%2Frooms/);

    // the login page: organisation notices (when set) and the forgot-password link to the public reset page
    await expect(page.getByTestId("login-submit")).toBeVisible();
    await expect(page.getByTestId("login-identifier")).toHaveValue("");
    await expect(page.getByText(/demo/i)).toHaveCount(0);
    await page.getByTestId("forgot-password").click();
    await expect(page).toHaveURL(/\/reset-password$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    await page.goto("/reset-password");
    await expect(page).toHaveURL(/\/reset-password$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.goto("/setup");
    await expect(page).toHaveURL(/\/setup$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // the change-password page needs the session (it calls the authenticated POST /auth/change-password)
    await page.goto("/login/change-password");
    await expect(page).toHaveURL(/\/login\?next=%2Flogin%2Fchange-password/);
  });

  test("login → import (real planning list) → classes → calendar → run report → settings", async ({ page }) => {
    test.setTimeout(240_000);
    await login(page);
    await expect(page.getByTestId("dashboard")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Özet|Dashboard/);

    // Import wizard: the Bahar planning list again (the import is idempotent: unchanged rows are not rewritten)
    await page.getByTestId("nav-import").click();
    await expect(page.getByTestId("import")).toBeVisible();
    await page.getByTestId("import-kind-planning-list").click();
    await page.getByTestId("file-input").setInputFiles(PLANNING_LIST);
    await page.getByTestId("import-start").click();
    await expect(page.getByTestId("import-report")).toBeVisible({ timeout: 120_000 });
    await expect(page.getByTestId("import-report")).toContainText("bahar_derslik_planlama_listesi_v5.xlsx");
    await expect(page.getByTestId("parse-warnings")).toBeVisible();
    const total = await page.locator("[data-severity]").count();
    expect(total, "the real workbook has parse warnings").toBeGreaterThan(0);

    // Requests → the classes review view; a row opens the inspector
    await page.getByTestId("nav-requests").click();
    await expect(page).toHaveURL(/\/classes/);
    const rows = page.getByTestId("classes-row");
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await rows.first().click();
    await expect(page.getByTestId("class-inspector")).toBeVisible();
    await page.keyboard.press("Escape");

    // Calendar: the imported board (Board lens: every room of a day), then A 204's week and the week switcher
    await page.goto(`/timetable?run=${boardRun()}&week=3`);
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("week-label")).toContainText("3");
    const index = await api<{ rooms: { id: number; name: string }[] }>(page, `/runs/${boardRun()}/calendar-index`);
    const a204 = index.rooms.find((r) => r.name === "A 204");
    expect(a204, "A 204 is in the board").toBeTruthy();
    await page.goto(`/timetable?run=${boardRun()}&week=3&lens=week&subject=room:${a204?.id}`);
    await expect(page.getByTestId("time-grid")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("calendar-event").first()).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("week-next").click();
    await expect(page.getByTestId("week-label")).toContainText("4");
    await expect(page).toHaveURL(/week=4/);

    // Run report of the full-term solver run: verdict, issue groups, diagnoses with fixes
    const run = await api<Run>(page, `/runs/${solverRun()}`);
    await page.goto(`/runs/${run.id}`);
    await expect(page.getByTestId("run-view")).toBeVisible();
    await expect(page.getByTestId("run-verdict")).toBeVisible({ timeout: 30_000 });
    if (run.status !== "FEASIBLE" && run.status !== "OPTIMAL") {
      await expect(page.getByTestId("diagnosis-card").first()).toBeVisible({ timeout: 30_000 });
      await expect(page.locator("[data-testid^=issue-group-]").first()).toBeVisible();
    }
    await expect(page.getByTestId("chat-panel")).toBeVisible();

    // Settings: AI tab without a key says so (no fake masked key), solver tab, users tab
    await page.getByTestId("nav-settings").click();
    await expect(page.getByTestId("settings")).toBeVisible();
    await page.getByTestId("tab-ai").click();
    await expect(page.getByTestId("api-key-masked")).toHaveCount(0);
    await page.getByTestId("tab-solver").click();
    await expect(page.getByTestId("save-solver")).toBeVisible();
  });

  test("generator studio: scope → leave a class out → template rule → upload mapping → pre-check fix → generate → run page", async ({ page }) => {
    test.setTimeout(360_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page);
    await page.goto("/generate?step=scope");
    await expect(page.getByTestId("scope-step")).toBeVisible();

    // 1. Scope: one week (W3); the scope sentence updates live and the draft saves
    await page.getByTestId("horizon-WEEK").click();
    const saved = page.getByTestId("save-status");
    await expect(saved).toHaveAttribute("data-state", "saved", { timeout: 15_000 });
    // the chip shows the server's draft summary: pick W3 once the horizon change is saved, again if a save raced it
    const w3 = page.getByTestId("week-3");
    await expect(async () => {
      if ((await w3.getAttribute("aria-pressed")) !== "true") await w3.click();
      await expect(w3).toHaveAttribute("aria-pressed", "true", { timeout: 5_000 });
    }).toPass({ timeout: 30_000 });
    await expect(page.getByTestId("scope-sentence")).toContainText(/\d/);
    await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 15_000 });

    // 2. Classes: leave one class out (draft only); the "left out" chip counts it
    await page.getByTestId("rail-step-classes").click();
    await expect(page.getByTestId("classes-step")).toBeVisible();
    const candidate = page.locator("[data-testid='class-row'][data-included='true']").first();
    await expect(candidate).toBeVisible({ timeout: 30_000 });
    const classId = await candidate.getAttribute("data-class-id");
    const leftOut = page.getByTestId("quick-leftOut");
    const leftOutBefore = Number((await leftOut.textContent())?.replace(/\D/g, "") || "0");
    const row = page.locator(`[data-testid='class-row'][data-class-id='${classId}']`);
    await row.getByTestId("in-plan").click();
    await expect(row).toHaveAttribute("data-included", "false");
    await expect(leftOut).toContainText(String(leftOutBefore + 1));

    // 3. Rules: without an AI key the sentence reader says so; a template rule works without AI
    await page.getByTestId("rail-step-rules").click();
    await expect(page.getByTestId("rules-step")).toBeVisible();
    await expect(page.getByTestId("no-key")).toBeVisible();
    await expect(page.getByTestId("nl-analyse")).toBeDisabled();
    const tryBefore = Number((await page.getByTestId("stat-try").first().textContent())?.replace(/\D/g, "") || "0");
    await page.getByTestId("add-template").click();
    await page.getByTestId("template-no_small_in_big").click();
    await page.getByTestId("builder-add").click();
    await expect(page.getByTestId("stat-try").first()).toHaveText(String(tryBefore + 1), { timeout: 15_000 });

    // 4. Upload the real planning list: no AI key → the column mapping step (the backend answers 409)
    if (!(await page.getByTestId("upload-panel").isVisible())) await page.getByTestId("add-upload").click();
    await page.getByTestId("upload-input").setInputFiles(PLANNING_LIST);
    await expect(page.getByTestId("mapping-step")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("mapping-row").nth(5)).toBeVisible({ timeout: 30_000 });

    // 5. Pre-check: a one-click fix on a hard-impossible class changes the draft (one more class left out)
    await page.getByTestId("rail-step-check").click();
    await expect(page.getByTestId("check-step")).toBeVisible();
    await expect(page.getByTestId("check-tab-impossible")).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("check-tab-impossible").click();
    const groups = page.getByTestId("issue-group").locator("> button[aria-expanded='false']");
    for (let i = await groups.count(); i > 0; i--) await groups.first().click(); // open every impossible group
    // the backend's one-click fix that leaves the class out of this plan ("… bu planın dışında kalsın")
    const leaveOut = page.locator("[data-testid='issue-card'][data-severity='error'] [data-testid='fix-button']").filter({ hasText: /dışında kalsın|out of (this|the) plan/i }).first();
    await expect(leaveOut).toBeVisible({ timeout: 60_000 });
    const outBefore = Number((await page.getByTestId("stat-out").first().textContent())?.replace(/\D/g, "") || "0");
    await leaveOut.click();
    await expect(page.getByTestId("stat-out").first()).toHaveText(String(outBefore + 1), { timeout: 20_000 });

    // 6. Generate (the real data still has impossible classes: generate anyway) → result card → run page
    await page.getByTestId("rail-step-run").click();
    await expect(page.getByTestId("generate-step")).toBeVisible();
    await page.getByTestId("studio-generate").click();
    const blocked = page.getByTestId("blocked-confirm");
    await expect(page.getByTestId("run-card").or(blocked).first()).toBeVisible({ timeout: 60_000 });
    if (await blocked.isVisible()) await page.getByTestId("blocked-confirm-cancel").click();
    const card = page.getByTestId("run-card").first();
    await expect(card).toHaveAttribute("data-status", FINISHED, { timeout: 240_000 });
    await expect(card.getByTestId("run-open-report")).toBeVisible();
    await card.getByTestId("run-open-report").click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
    await expect(page.getByTestId("run-view")).toBeVisible();
    await expect(page.getByTestId("tab-grid")).toBeVisible();
  });

  test("phone: calendar day list, drawer and the command palette finds A 204", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await login(page);
    await page.goto(`/timetable?run=${boardRun()}&week=3`);
    await expect(page.getByTestId("calendar-mobile").or(page.getByTestId("agenda")).first()).toBeVisible({ timeout: 30_000 });
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(scrollW).toBeLessThanOrEqual(1);
    await page.getByTestId("open-drawer").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+k");
    const palette = page.locator("[data-slot='command-input']");
    await expect(palette).toBeVisible();
    await palette.fill("A 204");
    await expect(page.getByRole("dialog").getByText(/156/).first()).toBeVisible({ timeout: 15_000 });
  });

  test("generator studio on a phone: one step per screen", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 760 });
    await login(page);
    await page.goto("/generate?step=scope");
    await expect(page.getByTestId("mobile-progress")).toContainText("1/5");
    await page.getByTestId("step-next").click();
    await expect(page.getByTestId("mobile-progress")).toContainText("2/5");
    await expect(page.getByTestId("class-cards")).toBeVisible({ timeout: 30_000 });
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(scrollW).toBeLessThanOrEqual(1);
    await page.getByTestId("summary-pill").click();
    await expect(page.getByRole("dialog").getByTestId("summary-panel")).toBeVisible();
  });
});
