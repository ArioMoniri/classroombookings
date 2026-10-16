/**
 * Flow loop round 1, lane F (docs/ROADMAP.md "Flow loop tickets — round 1"), on the full recording stack before
 * `stack.sh runs` (Bahar + Güz + Final workbooks, the Güz weekly grid published as board #3, names masked):
 *
 *  1. T-R1-39: /dashboard for Güz says the published imported board is the plan (no "henüz çizelge
 *     oluşturulmadı") and its "Derslik doluluğu" is the heatmap's "Genel doluluk" of the same week (±0.5 points);
 *     on a phone the hero link has a 44 px hit area.
 *  2. T-R1-41: /moderation/learning has exactly one h1; "Tümünü sıfırla…" keeps Sıfırla disabled on "sifirla" and
 *     says "Yazılan kelime eşleşmiyor." before any submit (nothing is reset here); no reset row shows "#<digits>".
 *  3. T-R1-41 phone: a profile's suggestion card has a full-width 44 px "Kabul et" and 44 px Reddet / Ertele.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test loop-r1-laneF
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, api, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);

const GUZ = process.env.E2E_LANEF_TERM ?? "2026-GUZ";

type TermRow = { id: number; code: string };
type Dash = { utilisation: number; utilisation_week: number; active_run_id: number | null };
type Heat = { source: string; runs: { run_id: number }[]; overall: { total: { pct: number } } };
type Sugg = { subject: { type: string; id: number | string }; state: string };

/** the working term (shell store) and no remembered dashboard week: the server picks the week */
async function useTerm(page: Page, code: string): Promise<TermRow> {
  const terms = await api<TermRow[]>(page, "/terms");
  const term = terms.find((t) => t.code === code)!;
  await page.evaluate((id) => {
    const raw = localStorage.getItem("smartsched.ui");
    const cur = raw ? (JSON.parse(raw) as { state?: Record<string, unknown>; version?: number }) : {};
    localStorage.setItem("smartsched.ui", JSON.stringify({ ...cur, state: { ...(cur.state ?? {}), termId: id } }));
    localStorage.removeItem("smartsched.workspace");
  }, term.id);
  return term;
}

test.describe("desktop 1440", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("T-R1-39: the dashboard reads the published imported board like the heatmap", async ({ page }) => {
    await login(page);
    const term = await useTerm(page, GUZ);
    await page.goto("/dashboard");
    const plan = page.getByTestId("dashboard-plan");
    await expect(plan).toContainText(/Yayında: içe aktarılan pano #\d+/);
    await expect(page.getByText("Bu dönem için henüz çizelge oluşturulmadı.")).toHaveCount(0);

    const d = await api<Dash>(page, `/dashboard?term_id=${term.id}`);
    expect(d.active_run_id).not.toBeNull();
    const heat = await api<Heat>(page, `/analytics/heatmap/rooms?term_id=${term.id}&week=${d.utilisation_week}`);
    expect(heat.source).toBe("board");
    expect(heat.runs.map((r) => r.run_id)).toContain(d.active_run_id);
    expect(heat.overall.total.pct).toBeGreaterThan(15);
    expect(Math.abs(100 * d.utilisation - heat.overall.total.pct)).toBeLessThanOrEqual(0.5);
    // the hero prints that number for that week (the ticker's screen-reader twin carries the final value)
    const pct = Math.round(100 * d.utilisation);
    await expect(page.getByRole("heading", { level: 2, name: new RegExp(`Derslik doluluğu\\s*%${pct}\\b`) })).toBeVisible();
    await expect(page.getByText(`${d.utilisation_week}. hafta`, { exact: false }).first()).toBeVisible();
  });

  test("T-R1-41: one h1, and the typed reset word must be exactly SIFIRLA", async ({ page }) => {
    await login(page);
    await page.goto("/moderation/learning");
    await expect(page.getByTestId("learning-memory")).toBeVisible();
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveText("Öğrenme belleği");
    for (const row of await page.getByTestId("reset-row").all()) await expect(row).not.toContainText(/#\d/);

    await page.getByTestId("reset-all-open").click();
    const dialog = page.getByTestId("reset-dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByTestId("reset-reason").fill("yeni öğretim yılı");
    const word = dialog.getByTestId("reset-word");
    await expect(word).toHaveAttribute("autocapitalize", "off");
    await word.fill("sifirla");
    await expect(dialog.getByTestId("reset-confirm")).toBeDisabled();
    await expect(dialog.getByTestId("reset-word-mismatch")).toHaveText("Yazılan kelime eşleşmiyor.");
    await word.fill("sıfırla");
    await expect(dialog.getByTestId("reset-word-mismatch")).toHaveCount(0);
    await expect(dialog.getByTestId("reset-confirm")).toBeEnabled();
    await dialog.getByRole("button", { name: "Vazgeç" }).click(); // nothing is reset
    await expect(dialog).toHaveCount(0);
  });
});

test.describe("phone 390", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });

  /** M-02: a tap 20 px off the centre still lands on the control (a 44 px box or its ::after hit area) */
  async function tappable(page: Page, testIdOrSelector: string): Promise<void> {
    const el = page.locator(testIdOrSelector).first();
    await el.scrollIntoViewIfNeeded();
    const box = (await el.boundingBox())!;
    const hits = await el.evaluate((node, b) => {
      const cx = b.x + b.width / 2;
      const cy = b.y + b.height / 2;
      return [cy - 20, cy + 20].map((y) => {
        const at = document.elementFromPoint(cx, y);
        return !!at && (at === node || node.contains(at));
      });
    }, box);
    expect(hits, `${testIdOrSelector} ${JSON.stringify(box)}`).toEqual([true, true]);
  }

  test("T-R1-39 / T-R1-41: hit areas on the dashboard hero and the suggestion card", async ({ page }) => {
    await login(page);
    const term = await useTerm(page, GUZ);
    await page.goto("/dashboard");
    await expect(page.getByTestId("dashboard-plan")).toBeVisible();
    await tappable(page, '[data-testid="dashboard-plan"] a');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    const open = (await api<Sugg[]>(page, `/learning/suggestions?term_id=${term.id}&limit=200`)).find((s) => s.subject.type === "instructor" && s.state === "open");
    test.skip(!open, "no open instructor suggestion in this term");
    await page.goto(`/moderation/people/${open!.subject.id}`);
    const card = page.getByTestId("suggestion-card").first();
    await expect(card).toBeVisible();
    const accept = card.getByTestId("suggestion-accept");
    const a = (await accept.boundingBox())!;
    const c = (await card.boundingBox())!;
    expect(a.height).toBeGreaterThanOrEqual(44);
    // the accept row spans the card (minus the weight menu and the padding)
    expect(a.width).toBeGreaterThanOrEqual(c.width - 32 - 48 - 2);
    for (const id of ["suggestion-reject", "suggestion-snooze"]) {
      expect((await card.getByTestId(id).boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
