import { expect, test, type Page } from "@playwright/test";

/**
 * Smoke flow against the mock API (NEXT_PUBLIC_API_MOCK=1):
 * login → import → generate (studio) → run report → grid (events, move dialog + drag) → settings,
 * plus the Generator Studio flow (scope → classes → rules → upload → pre-check → generate).
 */

async function login(page: Page) {
  await page.goto("/login");
  await expect(page.getByTestId("login-submit")).toBeVisible();
  await page.getByLabel(/E-posta|E-mail/).fill("fatih.demir@example.edu.tr");
  await page.getByLabel(/Şifre|Password/).fill("admin");
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("dashboard")).toBeVisible();
}

test.describe("SmartSched smoke", () => {
  test("login → import → generate → run → grid → settings", async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);

    // Unauthenticated routes redirect to /login (route guard).
    await page.context().clearCookies();
    await page.goto("/rooms");
    await expect(page).toHaveURL(/\/login\?next=%2Frooms/);
    await login(page);

    // Dashboard shows the KPIs and last runs.
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Özet|Dashboard/);
    await expect(page.locator("a[href='/runs/1']").first()).toBeVisible();

    // Import wizard: choose kind, upload a file, see the parse report.
    await page.getByTestId("nav-import").click();
    await expect(page.getByTestId("import")).toBeVisible();
    await page.getByTestId("import-kind-planning-list").click();
    await page.getByTestId("file-input").setInputFiles({ name: "Bahar Derslik Planlama Listesi v5.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("PK\u0003\u0004demo") });
    await page.getByTestId("import-start").click();
    await expect(page.getByTestId("parse-warnings")).toBeVisible();
    await expect(page.locator("[data-severity='error']")).toHaveCount(3);
    await page.getByRole("button", { name: /^(Hata|Error)/ }).click();
    await expect(page.locator("[data-severity]")).toHaveCount(3);

    // Requests inbox: open a row drawer.
    await page.getByTestId("nav-requests").click();
    await expect(page.getByTestId("request-row").first()).toBeVisible();
    await page.getByTestId("request-row").first().click();
    await expect(page.getByTestId("request-drawer")).toBeVisible();
    await page.keyboard.press("Escape");

    // Generate (Generator Studio): one sentence and Generate from the summary panel → run page.
    await page.getByTestId("nav-generate").click();
    await expect(page.getByTestId("generate")).toBeVisible();
    await page.getByTestId("rail-step-run").click();
    await expect(page.getByTestId("generate-step")).toBeVisible();
    await page.getByTestId("studio-generate").click();
    const blocked = page.getByTestId("blocked-confirm");
    await expect(page.getByTestId("run-card").or(blocked).first()).toBeVisible({ timeout: 20_000 });
    if (await blocked.isVisible()) await page.getByTestId("blocked-confirm-cancel").click();
    await expect(page.getByTestId("run-card").first()).toBeVisible();
    await page.getByTestId("run-card").first().getByRole("link", { name: /Çalıştırmayı gör|View run/ }).click();
    await expect(page).toHaveURL(/\/runs\/\d+/);
    await expect(page.getByTestId("run-status")).toBeVisible();

    // Open the known feasible run #1 and its grid.
    await page.goto("/runs/1?tab=grid");
    await expect(page.getByTestId("day-grid")).toBeVisible();
    const events = page.locator("[data-testid='day-grid'] [data-assignment-id]");
    await expect(events.first()).toBeVisible();
    expect(await events.count()).toBeGreaterThan(5);
    await expect(page.getByTestId("issues-pill")).toContainText("0");

    // Week switcher and zoom.
    await page.getByTestId("week-next").click();
    await expect(page.getByTestId("week-label")).toHaveText("W2");
    await page.getByTestId("zoom-week").click();
    await expect(page.getByTestId("week-grid")).toBeVisible();
    await page.getByTestId("zoom-day").click();

    // Open an event sheet → move dialog → live validity preview → confirm.
    const movable = page.locator("[data-testid='day-grid'] [data-assignment-id][data-status='ok']").first();
    await movable.click();
    await expect(page.getByTestId("event-sheet")).toBeVisible();
    await page.getByTestId("sheet-move").click();
    await expect(page.getByTestId("move-dialog")).toBeVisible();
    await expect(page.getByTestId("move-preview")).toBeVisible();
    await page.getByLabel(/Yeni gün|New day/).selectOption("7");
    const confirm = page.getByTestId("move-confirm");
    if (await confirm.isEnabled()) {
      await confirm.click();
      await expect(page.getByTestId("move-dialog")).toBeHidden();
    } else {
      await page.keyboard.press("Escape");
    }

    // Drag an event one period down with the mouse (dnd-kit pointer sensor).
    const target = page.locator("[data-testid='day-grid'] [data-assignment-id][data-status='ok']").first();
    const box = await target.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + 8);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2, box.y + 20, { steps: 4 });
      await page.mouse.move(box.x + box.width / 2 + 128, box.y + 20, { steps: 8 });
      await page.mouse.up();
    }
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible();

    // Chat panel proposes a move.
    await page.getByTestId("chat-input").fill("BME 419'u A 204'e taşı");
    await page.getByTestId("chat-send").click();
    await expect(page.getByTestId("proposal-card").first()).toBeVisible();

    // Settings: masked key + test button, solver tab.
    await page.getByTestId("nav-settings").click();
    await expect(page.getByTestId("settings")).toBeVisible();
    await expect(page.getByTestId("api-key-masked")).toContainText("7Qx2");
    await page.getByTestId("test-key").click();
    await expect(page.getByTestId("test-result")).toContainText(/claude/);
    await page.getByTestId("tab-solver").click();
    await expect(page.getByTestId("save-solver")).toBeVisible();

    // Infeasible run shows diagnosis cards.
    await page.goto("/runs/2");
    await expect(page.getByTestId("diagnosis-card").first()).toBeVisible();
    await expect(page.getByTestId("apply-fix").first()).toBeVisible();
  });

  test("mobile agenda fallback and command palette", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await login(page);
    await page.goto("/runs/1?tab=grid");
    await expect(page.getByTestId("agenda")).toBeVisible();
    await page.getByTestId("open-drawer").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+k");
    const palette = page.locator("[data-slot='command-input']");
    await expect(palette).toBeVisible();
    await palette.fill("A 204");
    await expect(page.getByText(/156/).first()).toBeVisible();
  });
  test("generator studio: scope → exclude → NL rule → upload → pre-check fix → generate → run page", async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page);
    await page.goto("/generate?step=scope");
    await expect(page.getByTestId("scope-step")).toBeVisible();

    // 1. Scope: one week (W7); the scope sentence updates live.
    await page.getByTestId("horizon-WEEK").click();
    const w7 = page.getByTestId("week-7");
    if ((await w7.getAttribute("aria-pressed")) !== "true") await w7.click();
    await expect(w7).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("scope-sentence")).toContainText(/\d/);
    await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 10_000 });

    // 2. Classes: leave one class out (draft only), the footer and the quick chip count it.
    await page.getByTestId("rail-step-classes").click();
    await expect(page.getByTestId("classes-step")).toBeVisible();
    const candidate = page.locator("[data-testid='class-row'][data-included='true']").first();
    await expect(candidate).toBeVisible();
    const classId = await candidate.getAttribute("data-class-id");
    const leftOutBefore = Number((await page.getByTestId("quick-leftOut").textContent())?.replace(/\D/g, "") || "0");
    const row = page.locator(`[data-testid='class-row'][data-class-id='${classId}']`);
    await row.getByTestId("in-plan").click();
    await expect(row).toHaveAttribute("data-included", "false");
    await expect(page.getByTestId("quick-leftOut")).toContainText(String(leftOutBefore + 1));

    // 3. Rules: write a sentence → review tray → accept.
    await page.getByTestId("rail-step-rules").click();
    await expect(page.getByTestId("rules-step")).toBeVisible();
    const before = Number((await page.getByTestId("stat-must").textContent()) ?? "0");
    await page.getByTestId("rule-composer-input").fill("TIP derslikleri sadece Tıp için");
    await page.getByTestId("nl-analyse").click();
    await expect(page.getByTestId("review-tray")).toBeVisible();
    await page.getByTestId("tray-accept").first().click();
    await expect(page.getByTestId("review-tray")).toBeHidden();
    await expect(page.getByTestId("stat-must")).toHaveText(String(before + 1));

    // 4. Upload a small xlsx → review table with "from file · row N" → accept one row.
    await page.getByTestId("add-upload").click();
    await page.getByTestId("upload-input").setInputFiles({ name: "Eczacilik_talepler.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("PK\u0003\u0004demo") });
    await expect(page.getByTestId("upload-row").first()).toHaveAttribute("data-stage", "ready", { timeout: 15_000 });
    await expect(page.getByTestId("upload-review")).toBeVisible();
    await expect(page.getByTestId("review-from").first()).toContainText(/Eczacilik_talepler\.xlsx/);
    await page.locator("[data-testid='review-row'][data-bucket='ready']").first().getByTestId("review-accept").click();
    await expect(page.locator("[data-testid='review-row'][data-state='accepted']")).toHaveCount(1);

    // 5. Pre-check: the impossible class has one-click fixes that change the draft.
    await page.getByTestId("rail-step-check").click();
    await expect(page.getByTestId("check-step")).toBeVisible();
    const impossible = page.locator("[data-testid='issue-card'][data-severity='error']").filter({ hasText: "BME 419" });
    await expect(impossible).toBeVisible({ timeout: 15_000 });
    await impossible.getByTestId("fix-button").first().click();
    await expect(impossible).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId("check-step").getByTestId("readiness")).not.toHaveAttribute("data-readiness", "blocked");

    // 6. Generate → run progress → result card → run page.
    await page.getByTestId("rail-step-run").click();
    await page.getByTestId("studio-generate").click();
    await expect(page.getByTestId("run-card").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("[data-testid='run-card'][data-status='FEASIBLE']").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("run-result").first()).toBeVisible();
    await page.getByTestId("run-open-report").first().click();
    await expect(page).toHaveURL(/\/runs\/\d+$/);
    await expect(page.getByTestId("run-view")).toBeVisible();
    await expect(page.getByTestId("tab-grid")).toBeVisible();
  });

  test("generator studio on a phone: one step per screen", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 760 });
    await login(page);
    await page.goto("/generate?step=scope");
    await expect(page.getByTestId("mobile-progress")).toContainText("1/5");
    await page.getByTestId("step-next").click();
    await expect(page.getByTestId("mobile-progress")).toContainText("2/5");
    await expect(page.getByTestId("class-cards")).toBeVisible();
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(scrollW).toBeLessThanOrEqual(1);
    await page.getByTestId("summary-pill").click();
    await expect(page.getByRole("dialog").getByTestId("summary-panel")).toBeVisible();
  });
});
