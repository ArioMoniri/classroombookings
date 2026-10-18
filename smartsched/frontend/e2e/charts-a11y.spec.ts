// CH-03 (docs/design/v3/charts.md §5.6, §6, §9): the ChartCard keyboard, colour-blind and print layer on a shell
// fixture (e2e/fixtures/charts), at 1440 mouse and 390 × 844 touch, tr-TR, Europe/Istanbul. Self-contained: the
// fixture is bundled with vite in beforeAll and served through page.route, so this spec needs neither the backend
// (E2E_REAL) nor the Next server, and the shell is never mounted on an app route.
import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Playwright runs specs as CommonJS here: the frontend root is the working directory (npx playwright test)
const FRONTEND = path.resolve(process.cwd());
const FIXTURE = path.join(FRONTEND, "e2e/fixtures/charts");
const OUT = path.join(FRONTEND, "test-results/charts-fixture");
const ORIGIN = "http://charts.fixture";
const TYPES: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

test.beforeAll(async () => {
  test.setTimeout(240_000);
  // vite is ESM-only: load it with a dynamic import from this CommonJS-compiled spec
  const { build } = await import("vite");
  await build({
    configFile: false,
    root: FIXTURE,
    base: "/",
    logLevel: "warn",
    resolve: {
      alias: [
        { find: /^@\//, replacement: `${path.join(FRONTEND, "src")}/` },
        { find: /^next\/dynamic$/, replacement: path.join(FIXTURE, "shims.ts") },
        { find: /^next\/navigation$/, replacement: path.join(FIXTURE, "shims.ts") },
      ],
    },
    define: { "process.env.NODE_ENV": JSON.stringify("production") },
    build: { outDir: OUT, emptyOutDir: true, minify: false, chunkSizeWarningLimit: 4000 },
  });
});

async function open(page: Page) {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const rel = new URL(route.request().url()).pathname.replace(/^\/$/, "/index.html");
    try {
      const body = await readFile(path.join(OUT, rel));
      await route.fulfill({ body, contentType: TYPES[path.extname(rel)] ?? "application/octet-stream" });
    } catch {
      await route.fulfill({ status: 404, body: "" });
    }
  });
  await page.goto(`${ORIGIN}/`);
  await expect(page.locator("[data-chart-card='fx-bar'] svg").first()).toBeVisible({ timeout: 30_000 });
}

const viewports = [
  { name: "1440 mouse", use: { viewport: { width: 1440, height: 900 } } },
  { name: "390 touch", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } },
] as const;

for (const vp of viewports) {
  test.describe(`charts a11y · ${vp.name}`, () => {
    test.use({ ...vp.use, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

    test("keyboard scrub reads the bucket; Esc hides; focus never on <body>", async ({ page }) => {
      await open(page);
      const group = page.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" }).first();
      await group.focus();
      await page.keyboard.press("End");
      await expect(page.locator(".ch-tt").first()).toContainText("14 Ekim Çarşamba");
      await expect(page.getByTestId("chart-live-fx-bar")).toHaveText("14 Ekim Çarşamba: toplam 82.300 token; Sohbet 37.120, Kurallar 45.180");
      await page.keyboard.press("ArrowLeft");
      await expect(page.getByTestId("chart-live-fx-bar")).toContainText("13 Ekim Salı: toplam 69.000 token");
      await page.keyboard.press("Escape");
      await expect(page.locator(".ch-tt").first()).toBeHidden();
      expect(await page.evaluate(() => document.activeElement !== document.body && document.activeElement?.getAttribute("role"))).toBe("group");
    });

    test("forced colours turn the hatch patterns on", async ({ page }) => {
      await open(page);
      const patterns = page.locator("[data-chart-card='fx-bar'] svg pattern");
      await expect(patterns).toHaveCount(0);
      await page.emulateMedia({ forcedColors: "active" });
      await expect.poll(() => patterns.count(), { timeout: 10_000 }).toBeGreaterThan(0);
    });

    test("print: SVG renderer, controls hidden, the table twin printed; page.pdf() has the chart", async ({ page }) => {
      await open(page);
      const line = page.getByTestId("chart-plot-fx-line");
      await expect(line).toHaveAttribute("data-renderer", vp.name === "390 touch" ? "svg" : "canvas");
      await page.emulateMedia({ media: "print" });
      await expect(line).toHaveAttribute("data-renderer", "svg");
      await expect(page.locator("[data-chart-card='fx-line'] svg").first()).toBeVisible();
      await expect(page.locator("[data-chart-card='fx-bar'] [data-chart-menu]")).toBeHidden();
      await expect(page.locator("[data-chart-card='fx-bar'] [data-chart-footer]")).toBeHidden();
      const box = await page.locator("[data-chart-table='fx-bar']").boundingBox();
      expect(box && box.height).toBeGreaterThan(100);
      const pdf = await page.pdf({ format: "A4" });
      expect(pdf.byteLength).toBeGreaterThan(10_000);
      expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
    });
  });
}
