import { chromium } from "@playwright/test";
const base = "http://127.0.0.1:3300";
const out = process.argv[2];
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push("pageerror " + e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push("console " + m.text()); });
await page.goto(base + "/login");
await page.getByLabel(/E-posta|E-mail/).fill("fatih.demir@example.edu.tr");
await page.getByLabel(/Şifre|Password/).fill("admin");
await page.getByTestId("login-submit").click();
await page.getByTestId("dashboard").waitFor();
// English UI
await page.evaluate(() => { document.cookie = "NEXT_LOCALE=en; path=/"; });
await page.goto(base + "/generate?step=rules");
await page.getByTestId("rules-step").waitFor();
await page.getByTestId("nl-input").fill("TIP rooms only for Medicine. Keep Pharmacy in C block on Mondays. Nursing in A 20. NRS 450 last 7 weeks");
await page.getByTestId("nl-analyse").click();
await page.getByTestId("review-tray").waitFor();
await page.getByTestId("add-upload").click();
await page.getByTestId("upload-input").setInputFiles({ name: "Pharmacy_requests.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: Buffer.from("PK\u0003\u0004demo") });
await page.getByTestId("upload-review").waitFor();
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/rules-tray-1440.png`, fullPage: true });
await page.getByTestId("add-template").click();
await page.getByTestId("template-keep_in_building").click();
await page.getByTestId("rule-builder").waitFor();
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/builder-1440.png` });
await page.keyboard.press("Escape");
await page.goto(base + "/generate?step=classes");
await page.getByTestId("class-row").first().waitFor();
await page.getByTestId("class-row").first().locator("[data-edit='students']").click();
await page.getByTestId("students-input").fill("999");
await page.keyboard.press("Enter");
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/classes-edit-1440.png` });
for (const w of [360, 768, 1280]) {
  await page.setViewportSize({ width: w, height: 800 });
  for (const step of ["scope", "classes", "rules", "check"]) {
    await page.goto(base + "/generate?step=" + step);
    await page.getByTestId("generate").waitFor();
    await page.waitForTimeout(1200);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (sw > 1) errors.push(`horizontal scroll ${sw}px at ${w} ${step}`);
    if (w !== 1280 || step === "classes") await page.screenshot({ path: `${out}/${step}-${w}.png`, fullPage: w !== 360 });
  }
}
console.log(errors.slice(0, 30).join("\n") || "no errors");
await browser.close();
