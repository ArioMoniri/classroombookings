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
 *  4. T-R1-42 (lane F2): on the Final exam solver run (POST /runs kind EXAM, as docs/testing/flows/rounds
 *     round-1-staff R1-S-14 did) a plan with the defaults finds the exam list's people among the masked instructor
 *     rows (pool line "eşleşen N", duties assigned), the imported Final board is offered as "sınav bağlantısı yok",
 *     and a plan whose pool is empty says why in Turkish and offers the one-tap "Tüm eğitmenlerle yeniden çalıştır".
 *  5. T-R1-39 part 2 (lane F2): the /moderation header of Güz with the imported board #3 published reads a match
 *     rate above 0 % (board cells matched to the requests by course, day and period).
 *  6. Phone (390, touch) on /exams/invigilation and /moderation: no horizontal scroll (M-01), 44 px controls (M-02),
 *     16 px inputs (M-03).
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test loop-r1-laneF
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, api, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);

const GUZ = process.env.E2E_LANEF_TERM ?? "2026-GUZ";
const FINAL = process.env.E2E_LANEF_FINAL ?? "2026-FINAL";

type RunRow = { id: number; term_id: number; kind: string; status: string; params: { source?: string }; label: string | null };
type Plan = { id: number; status: string; exam_run_id: number; params: Record<string, unknown>; counts: { required: number | null; filled: number | null; people: number | null }; pool: { instructor_pool: string; exam_people: number; matched: number; ambiguous: number; unmatched: number; size: number } | null; diagnosis: { code: string; severity: string; text: { tr: string }; suggestions?: { code: string; text: { tr: string } }[] }[]; headline: { tr: string } | null };
const DONE = /^(OPTIMAL|FEASIBLE|INFEASIBLE|FAILED|ERROR)$/;

/** the Final term's solved exam run (not the imported board) and the board itself */
async function finalRuns(page: Page): Promise<{ term: TermRow; solved: RunRow; board: RunRow | undefined }> {
  const term = (await api<TermRow[]>(page, "/terms")).find((t) => t.code === FINAL)!;
  const runs = (await api<RunRow[]>(page, `/runs?term_id=${term.id}`)).filter((r) => r.kind === "EXAM" && /^(OPTIMAL|FEASIBLE|FEASIBLE_PARTIAL)$/.test(r.status));
  const solved = runs.filter((r) => r.params?.source !== "GRID_IMPORT").sort((a, b) => b.id - a.id)[0];
  test.skip(!solved, `no solved exam run in ${FINAL}: POST /runs {kind: EXAM} first (R1-S-14 step 2)`);
  return { term, solved: solved!, board: runs.find((r) => r.params?.source === "GRID_IMPORT") };
}

async function postJson<T>(page: Page, path: string, body: unknown): Promise<{ status: number; json: T }> {
  return page.evaluate(async ({ path, body }) => {
    const r = await fetch(`/api/v1${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return { status: r.status, json: (await r.json()) as T };
  }, { path, body });
}

async function waitPlan(page: Page, id: number, timeoutMs = 240_000): Promise<Plan> {
  const until = Date.now() + timeoutMs;
  for (;;) {
    const p = await api<Plan>(page, `/invigilation/plans/${id}`);
    if (DONE.test(p.status)) return p;
    expect(Date.now(), `plan #${id} still ${p.status}`).toBeLessThan(until);
    await page.waitForTimeout(2_000);
  }
}

type TermRow = { id: number; code: string };
type Dash = { utilisation: number; utilisation_week: number; active_run_id: number | null };
type Heat = { source: string; runs: { run_id: number }[]; overall: { total: { pct: number } } };
type Sugg = { subject: { type: string; id: number | string }; state: string };

/** the working term (shell store) and no remembered dashboard week: the server picks the week */
async function useTerm(page: Page, code: string): Promise<TermRow> {
  const terms = await api<TermRow[]>(page, "/terms");
  const term = terms.find((t) => t.code === code);
  // the Güz board comes from `stack.sh runs`; the e2e gate backend (e2e-backend-entry.sh) seeds Bahar + Final only
  test.skip(!term, `term ${code} is not on this backend (stack.sh runs imports it; the e2e gate seed does not)`);
  if (!term) throw new Error(`term ${code} is not on this backend`);
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

test.describe("desktop 1440 · lane F2", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("T-R1-42: the default pool finds the exam list's people on the masked Final data; the board is marked", async ({ page }) => {
    test.setTimeout(420_000);
    await login(page);
    const { term, solved, board } = await finalRuns(page);
    await useTerm(page, FINAL);
    await page.goto(`/exams/invigilation?run=${solved.id}`);
    const select = page.getByTestId("invig-run");
    await expect(select).toHaveValue(String(solved.id));
    if (board) {
      await expect(select.locator(`option[value="${board.id}"]`)).toContainText("sınav bağlantısı yok");
      await page.goto(`/exams/invigilation?run=${board.id}`);
      await expect(page.getByTestId("invig-board-run")).toContainText("içe aktarılan bir pano");
      await page.goto(`/exams/invigilation?run=${solved.id}`);
    }
    // a plan with the defaults (the "Sınavlarda adı geçen eğitmenler" pool), as R1-S-14 step 2 ran it
    await page.getByTestId("invig-new").click();
    const form = page.getByTestId("invig-form");
    await expect(form.getByTestId("invig-param-pool")).toHaveValue("exam_instructors");
    await form.getByTestId("invig-param-label").fill("F2 varsayılan havuz");
    await form.getByTestId("invig-form-submit").click();
    await expect(form).toHaveCount(0);
    await expect(page).toHaveURL(/plan=\d+/);
    const planId = Number(new URL(page.url()).searchParams.get("plan"));
    const plan = await waitPlan(page, planId);
    expect(plan.pool, "pool summary on the brief").not.toBeNull();
    expect(plan.pool!.instructor_pool).toBe("exam_instructors");
    expect(plan.pool!.exam_people).toBeGreaterThan(100);
    expect(plan.pool!.matched).toBeGreaterThan(100);
    expect(plan.pool!.size).toBeGreaterThan(100);
    expect(plan.counts.required).toBeGreaterThan(1000);
    expect(plan.counts.filled!).toBeGreaterThan(0);
    expect(plan.headline!.tr).not.toMatch(/\d\.\d/); // decimal comma, never "12.0"
    await page.reload();
    const line = page.getByTestId("invig-pool-line");
    await expect(line).toContainText(/sınav listesinde \d+ kişi; eğitmen kaydıyla eşleşen [1-9]\d*/);
    await expect(page.getByTestId("invig-counts").locator('[data-key="filled"]')).not.toContainText(/^\D*0\D*$/);
    expect(term.id).toBe(solved.term_id);

    // an empty pool: the plan says why in Turkish and offers the one-tap "Tüm eğitmenler"
    const created = await postJson<{ plan_id: number }>(page, "/invigilation/plans", { exam_run_id: solved.id, label: "F2 boş havuz", params: { instructor_pool: "none" } });
    expect(created.status).toBe(202);
    const empty = await waitPlan(page, created.json.plan_id);
    expect(empty.status).toBe("INFEASIBLE");
    const diag = empty.diagnosis.find((d) => d.code === "pool_empty")!;
    expect(diag.severity).toBe("error");
    expect(diag.text.tr).toMatch(/^Gözetmen havuzu boş: /);
    expect(diag.suggestions?.[0]?.code).toBe("pool_all");
    await page.goto(`/exams/invigilation?run=${solved.id}&plan=${empty.id}`);
    const alert = page.getByTestId("invig-pool-empty");
    await expect(alert).toContainText("Gözetmen havuzu boş");
    await expect(alert).toContainText(/Eğitmen yok/);
    await alert.getByTestId("invig-pool-all").click();
    await expect(page.getByText(/tüm eğitmenlerle başlatıldı/)).toBeVisible();
    await expect(page).not.toHaveURL(new RegExp(`plan=${empty.id}(&|$)`));
    const childId = Number(new URL(page.url()).searchParams.get("plan"));
    const child = await api<Plan>(page, `/invigilation/plans/${childId}`);
    expect(child.params.instructor_pool).toBe("all");
    expect(child.exam_run_id).toBe(solved.id);
  });

  test("T-R1-39 part 2: the moderation header rate of the published imported board is above 0 %", async ({ page }) => {
    await login(page);
    const term = await useTerm(page, GUZ);
    const m = await api<{ run_id: number | null; match_rate: number | null; counts: Record<string, number> }>(page, `/terms/${term.id}/moderation/matchings?limit=1`);
    expect(m.run_id).not.toBeNull();
    expect(m.match_rate).not.toBeNull();
    expect(m.match_rate!).toBeGreaterThan(0.5);
    expect(m.counts.satisfied).toBeGreaterThan(300);
    await page.goto("/moderation");
    await expect(page.getByText(new RegExp(`Yayında: #${m.run_id} · taleplerin %[1-9]\\d*'[a-zçğıöşü]+ karşılandı`))).toBeVisible({ timeout: 30_000 });
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

    // the learning pass the testers ran (POST /learning/refresh), then a person with an open card
    const refreshed = await page.evaluate(async (id) => (await fetch("/api/v1/learning/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ term_id: id }) })).status, term.id);
    expect([200, 202]).toContain(refreshed);
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

  /** MOBILE.md M-01 / M-02 / M-03 on a route: no horizontal scroll, every control ≥ 44 px or with a 44 px hit area
   *  (the M-02 snippet, repeated down the page), no text under 11 px and no text input under 16 px */
  async function mobileChecks(page: Page): Promise<void> {
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches), "touch emulation").toBe(true);
    const [sw, cw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth, innerWidth]);
    expect(sw! <= cw! && iw === cw, `M-01 scroll ${sw} client ${cw} inner ${iw}`).toBe(true);
    const total = await page.evaluate(() => document.documentElement.scrollHeight);
    const vh = await page.evaluate(() => document.documentElement.clientHeight);
    const bad = new Set<string>();
    for (let y = 0; y < total; y += Math.round(vh * 0.8)) {
      await page.evaluate((y) => window.scrollTo(0, y), y);
      await page.waitForTimeout(100);
      const found = await page.evaluate(() => {
        const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
        const hits = (el: Element, x: number, y: number) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
        const out: string[] = [];
        for (const el of document.querySelectorAll<HTMLElement>(SEL)) {
          const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
          if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
          if (el.checkVisibility && !el.checkVisibility()) continue;
          if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
          if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
          let w = r.width, h = r.height;
          const lab = (el as HTMLInputElement).labels?.[0]; if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
          if (w >= 44 && h >= 44) continue;
          const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
          const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
          if (!(cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22)) continue; // another scroll step measures it
          if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x!, y!))) continue;
          out.push(`${(el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40)} ${Math.round(w)}×${Math.round(h)}`);
        }
        return out;
      });
      for (const f of found) bad.add(f);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    // the segmented controls (components/ui/segmented-control: 38 px items in a 44 px track) are a shared component outside lane F
    const own = [...bad].filter((b) => !/^(invig-view-|invig-tab-|Sınıflar|Kişiler|Talepler|Tercihler|Eşleşmeler)/.test(b));
    expect(own, "M-02 controls under 44 px without a 44 px hit area").toEqual([]);
    const m03 = await page.evaluate(() => {
      const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue?.trim() ? 1 : 2) });
      const small: string[] = [];
      while (tw.nextNode()) {
        const el = tw.currentNode.parentElement!, cs = getComputedStyle(el), r = el.getBoundingClientRect();
        if (!r.width || r.width <= 1 || cs.visibility === "hidden" || el.closest(".sr-only,[data-allow-small-text]")) continue;
        const px = parseFloat(cs.fontSize); if (px < 11) small.push(`${el.textContent?.trim().slice(0, 30)} ${px}px`);
      }
      const inputs = [...document.querySelectorAll<HTMLElement>('input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea')]
        .filter((i) => i.getBoundingClientRect().width > 1 && !i.closest(".sr-only") && (!i.checkVisibility || i.checkVisibility()) && parseFloat(getComputedStyle(i).fontSize) < 16)
        .map((i) => `${i.dataset.testid ?? i.id ?? i.tagName} ${getComputedStyle(i).fontSize}`);
      return { small, inputs };
    });
    expect(m03.small, "M-03 text under 11 px").toEqual([]);
    expect(m03.inputs, "M-03 inputs under 16 px").toEqual([]);
  }

  test("T-R1-42 / T-R1-39 phone: /exams/invigilation and the /moderation header fit a phone", async ({ page }) => {
    await login(page);
    const { solved } = await finalRuns(page);
    await useTerm(page, FINAL);
    const plans = (await api<Plan[]>(page, `/invigilation/plans?exam_run_id=${solved.id}`)).filter((p) => DONE.test(p.status) && p.pool?.instructor_pool === "exam_instructors");
    await page.goto(`/exams/invigilation?run=${solved.id}${plans[0] ? `&plan=${plans[0].id}` : ""}`);
    await expect(page.getByTestId("invigilation-page")).toBeVisible();
    if (plans[0]) await expect(page.getByTestId("invig-pool-line")).toContainText(/eşleşen [1-9]\d*/);
    await mobileChecks(page);
    await useTerm(page, GUZ);
    await page.goto("/moderation");
    await expect(page.getByRole("heading", { level: 1, name: "Moderasyon" })).toBeVisible();
    await expect(page.getByText(/taleplerin %[1-9]\d*'[a-zçğıöşü]+ karşılandı/)).toBeVisible();
    await mobileChecks(page);
  });
});
