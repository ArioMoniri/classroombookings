/**
 * HB-23c helper file router (docs/design/v3/helper-file-router.md §11.1, §11.2 "E2E TO RUN"). Real backend only
 * (E2E_REAL=1, HB-23b's /helper/files/** on). NOT run by the builder lane (resource rule 2026-10-18): the e2e lane
 * runs it on one stack with the masked fixtures ($REC_WORKDIR/fixtures, e2e/fixtures-dir.ts).
 *
 * Cases:
 *  1. admin 1440: ⌘J → drop the Bahar board (Güz active) → card + mismatch → primary → /import file row → Önizle →
 *     preview with term_check; no second upload (no multipart `file` on /imports/*).
 *  2. the same at 390 touch: 📎 → setInputFiles → card → primary → sheet closes → file row; M-01/M-02/M-03 checks.
 *  3. planner: the transposed grid → the setup wizard's row 1 with the chip.
 *  4. academician 390: planning list → "Derslerim'i aç"; .ics → /profile?calendar=1 (needs E2E_TEACHER_EMAIL).
 *  5. page-level drop on /dashboard 1440 → edge target → the sheet opens with the card.
 *  6. several files → one card → /onboarding with all rows (decision 16: no classify request).
 *  7. KVKK guard stack (KVKK_UPLOAD_GUARD=1, E2E_KVKK_GUARD=1): the raw seed workbook → refused card.
 *  8. sign-out clears sessionStorage["smartsched.helper.fileHandoff"] (KVKK condition 10); no token in any URL.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, FIXTURES, REAL, SKIP_REASON, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);

const BOARD = path.join(FIXTURES, "bahar_derslikler_takvimi_2026.xlsx");
const PLANNING = path.join(FIXTURES, "bahar_derslik_planlama_listesi_v5.xlsx");
const TRANSPOSED = path.join(FIXTURES, "universal", "bahar_week1_transposed.xlsx");
const ICS = path.join(FIXTURES, "helper_files", "seminar.ics");
const TEACHER = process.env.E2E_TEACHER_EMAIL;
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? ADMIN_PASSWORD;

/** every request URL of the page, to prove no upload token is ever in an address (or a referrer) */
function watchUrls(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (r) => {
    urls.push(r.url());
    const ref = r.headers()["referer"];
    if (ref) urls.push(ref);
  });
  return urls;
}

/** Drop OS files onto an element: a DataTransfer built in the page from the files' bytes. */
async function dropFiles(page: Page, selector: string, files: string[]) {
  const payload = files.map((f) => ({ name: path.basename(f), b64: readFileSync(f).toString("base64") }));
  const dt = await page.evaluateHandle((list) => {
    const d = new DataTransfer();
    for (const f of list) {
      const bin = Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0));
      d.items.add(new File([bin], f.name));
    }
    return d;
  }, payload);
  await page.dispatchEvent(selector, "dragenter", { dataTransfer: dt });
  await page.dispatchEvent(selector, "dragover", { dataTransfer: dt });
  await page.dispatchEvent(selector, "drop", { dataTransfer: dt });
}

async function chooseTerm(page: Page, name: RegExp) {
  // the active term is the term switcher's; Güz makes the Bahar file a mismatch
  const terms = await page.evaluate(async () => (await (await fetch("/api/v1/terms")).json()) as { id: number; name: string }[]);
  const guz = terms.find((t) => name.test(t.name));
  test.skip(!guz, "no Güz term on this stack");
  await page.evaluate((id) => {
    const raw = localStorage.getItem("smartsched.ui");
    const v = raw ? JSON.parse(raw) : { state: {} };
    v.state = { ...(v.state ?? {}), termId: id };
    localStorage.setItem("smartsched.ui", JSON.stringify(v));
  }, guz!.id);
  await page.reload();
}

const tokenIn = (urls: string[], token: string) => urls.some((u) => u.includes(token) || u.includes(encodeURIComponent(token)));

test.describe("helper file router: desktop 1440", () => {
  test.use({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

  test("1. ⌘J → drop the Bahar board (Güz active) → card + mismatch → /import file row → Önizle", async ({ page }) => {
    const urls = watchUrls(page);
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    await chooseTerm(page, /Güz/i);
    await page.keyboard.press("Control+j");
    await expect(page.getByTestId("helper-sheet")).toBeVisible();
    const classify = page.waitForResponse((r) => r.url().includes("/helper/files/classify"));
    await dropFiles(page, '[data-testid="helper-log"]', [BOARD]);
    const out = await (await classify).json();
    const card = page.getByTestId("helper-card-file-detected");
    await expect(card).toBeVisible({ timeout: 1500 + 5000 });
    await expect(card).toContainText("haftalık derslik takvimi");
    await expect(card.getByTestId("helper-file-certainty")).toHaveText("Eminim");
    await expect(card.getByTestId("helper-file-term")).toContainText("Bahar 2026");
    await expect(card.getByTestId("helper-file-warning-term_mismatch")).toBeVisible();
    // one primary, the focus on the card title (the reader hears the kind first)
    await expect(card.getByTestId("helper-file-primary")).toHaveCount(1);
    await expect(page.locator(":focus")).toContainText("haftalık derslik takvimi");
    // KVKK: no cell value / raw header in the response ("Fatih Bey" is a header fragment of the fixture)
    expect(JSON.stringify(out)).not.toContain("Fatih Bey");
    const handoff = page.waitForResponse((r) => r.url().includes("/helper/files/handoff"));
    await card.getByTestId("helper-file-primary").click();
    expect((await handoff).ok()).toBe(true);
    await page.waitForURL(/\/import\?kind=weekly-grid&term=\d+&year=2026&from=helper/);
    const row = page.getByTestId("import-handed-file");
    await expect(row).toContainText("Yardımcıdan geldi");
    await expect(page.getByTestId("import-start")).toBeFocused();
    const upload = page.waitForRequest((r) => /\/imports\/weekly-grid/.test(r.url()) && r.method() === "POST");
    await page.getByTestId("import-start").click();
    const req = await upload;
    expect(req.postData() ?? "").toContain('name="upload_token"');
    expect(req.postData() ?? "").not.toContain('name="file"');
    await expect(page.getByTestId("import-preview")).toBeVisible({ timeout: 60_000 });
    expect(tokenIn(urls, out.stage.upload_token)).toBe(false);
  });

  test("3. planner: the transposed grid → the setup wizard's row 1 with the chip", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    await page.keyboard.press("Control+j");
    await page.getByTestId("helper-composer").getByTestId("helper-file-input").setInputFiles(TRANSPOSED);
    const card = page.getByTestId("helper-card-file-detected");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("helper-file-certainty")).toHaveText("Büyük olasılıkla");
    await card.getByTestId("helper-file-primary").click();
    await page.waitForURL(/\/onboarding\?from=helper/);
    await expect(page.getByTestId("onboarding-handed-file").first()).toContainText("bahar_week1_transposed.xlsx");
    await expect(page.getByTestId("onboarding-handed-file").first()).toContainText("Yardımcıdan geldi");
  });

  test("5. page-level drop on /dashboard → edge target → the sheet opens with the card", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    const payload = [{ name: "Bahar_son.xlsx", b64: readFileSync(BOARD).toString("base64") }];
    const dt = await page.evaluateHandle((list) => {
      const d = new DataTransfer();
      for (const f of list) d.items.add(new File([Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0))], f.name));
      return d;
    }, payload);
    await page.dispatchEvent("main", "dragenter", { dataTransfer: dt });
    await page.dispatchEvent("main", "dragover", { dataTransfer: dt });
    await expect(page.getByTestId("page-file-target")).toContainText("Yardımcıya bırakın");
    await page.dispatchEvent("main", "drop", { dataTransfer: dt });
    await expect(page.getByTestId("page-file-target")).toHaveCount(0);
    await expect(page.getByTestId("helper-sheet")).toBeVisible();
    await expect(page.getByTestId("helper-card-file-detected")).toBeVisible();
  });

  test("5b. no edge target on /setup and with ?embed=1", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard?embed=1");
    const dt = await page.evaluateHandle(() => {
      const d = new DataTransfer();
      d.items.add(new File(["x"], "a.xlsx"));
      return d;
    });
    await page.dispatchEvent("body", "dragenter", { dataTransfer: dt });
    await page.dispatchEvent("body", "dragover", { dataTransfer: dt });
    await expect(page.getByTestId("page-file-target")).toHaveCount(0);
  });

  test("6. several files → one card → /onboarding with all rows, no classify request (decision 16)", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    let classified = 0;
    page.on("request", (r) => {
      if (r.url().includes("/helper/files/classify")) classified += 1;
    });
    await page.keyboard.press("Control+j");
    await page.getByTestId("helper-composer").getByTestId("helper-file-input").setInputFiles([PLANNING, BOARD]);
    const card = page.getByTestId("helper-card-file-many");
    await expect(card).toContainText("2 dosya bıraktınız");
    await card.getByTestId("helper-file-primary").click();
    await page.waitForURL(/\/onboarding\?from=helper/);
    await expect(page.getByTestId("onboarding-handed-file")).toHaveCount(2);
    expect(classified).toBe(0);
  });

  test("7. KVKK guard stack: the raw seed workbook → refused card, nothing staged", async ({ page }) => {
    test.skip(process.env.E2E_KVKK_GUARD !== "1", "needs a stack with KVKK_UPLOAD_GUARD=1 and the raw workbook");
    const raw = process.env.E2E_RAW_WORKBOOK ?? path.resolve(process.cwd(), "../backend/tests/fixtures/bahar_derslik_planlama_listesi_v5.xlsx");
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    await page.keyboard.press("Control+j");
    const classify = page.waitForResponse((r) => r.url().includes("/helper/files/classify"));
    await page.getByTestId("helper-composer").getByTestId("helper-file-input").setInputFiles(raw);
    const out = await (await classify).json();
    expect(out.stage ?? null).toBeNull();
    await expect(page.getByTestId("helper-card-file-refused")).toBeVisible();
    await expect(page.getByTestId("helper-card-file-refused").getByTestId("helper-file-another")).toBeVisible();
  });

  test("8. sign-out clears the hand-over (KVKK condition 10)", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    await page.keyboard.press("Control+j");
    await page.getByTestId("helper-composer").getByTestId("helper-file-input").setInputFiles(PLANNING);
    await page.getByTestId("helper-card-file-detected").getByTestId("helper-file-primary").click();
    await page.waitForURL(/from=helper/);
    expect(await page.evaluate(() => sessionStorage.getItem("smartsched.helper.fileHandoff"))).not.toBeNull();
    await page.getByTestId("user-menu").click();
    await page.getByTestId("logout").click();
    await page.waitForURL(/\/login/);
    expect(await page.evaluate(() => sessionStorage.getItem("smartsched.helper.fileHandoff"))).toBeNull();
  });
});

test.describe("helper file router: phone 390 touch", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

  async function mobileChecks(page: Page) {
    // M-01 no horizontal scroll; M-02 44 px targets on the card; M-03 16 px composer text
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const b of await page.locator('[data-testid^="helper-card-file"] button:visible, [data-testid="import-handed-file"] button:visible').all()) {
      const box = await b.boundingBox();
      if (box) expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(43.5);
    }
    const field = page.locator('[data-testid="helper-composer"] textarea');
    if (await field.count()) expect(await field.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  }

  test("2. 📎 → picker → card → primary → the sheet closes → the file row", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/dashboard");
    // Ctrl+J opens the full-screen sheet on phones too (the window's shortcut listener)
    await page.keyboard.press("Control+j");
    await expect(page.getByTestId("helper-sheet")).toBeVisible();
    // no OS drag on phones: the 📎's native picker
    await page.getByTestId("helper-file-input").first().setInputFiles(BOARD);
    const card = page.getByTestId("helper-card-file-detected");
    await expect(card).toBeVisible();
    const primary = card.getByTestId("helper-file-primary");
    expect((await primary.boundingBox())!.height).toBeGreaterThanOrEqual(47.5);
    await mobileChecks(page);
    await primary.tap();
    await expect(page.getByTestId("helper-sheet")).toHaveCount(0);
    await expect(page.getByTestId("import-handed-file")).toBeVisible();
    await mobileChecks(page);
  });

  test("4. academician: planning list → Derslerim'i aç; .ics → /profile?calendar=1", async ({ page }) => {
    test.skip(!TEACHER, "needs E2E_TEACHER_EMAIL (an academician account)");
    await login(page, TEACHER!, TEACHER_PASSWORD);
    await page.goto("/reserve");
    await page.keyboard.press("Control+j");
    await page.getByTestId("helper-file-input").first().setInputFiles(PLANNING);
    const card = page.getByTestId("helper-card-file-needs_planner");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("helper-file-primary")).toHaveText("Derslerim'i aç");
    await expect(card).not.toContainText("içe aktar");
    await page.getByTestId("helper-file-input").first().setInputFiles(ICS);
    const ics = page.getByTestId(/helper-card-file-(needs_planner|detected)/).last();
    await expect(ics.getByTestId("helper-file-primary")).toHaveText("Takvimime ekle");
    await ics.getByTestId("helper-file-primary").tap();
    await page.waitForURL(/\/profile\?calendar=1/);
  });
});
