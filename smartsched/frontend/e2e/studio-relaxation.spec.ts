/**
 * Studio Generate: the relaxation policy control (Dönem ayarı / Önce kilitliler / Önce en çok ders) on the real
 * backend (E2E_REAL=1). The term's own setting is read from GET /terms/{id}/relaxation-policy; a chosen policy goes
 * into the generate request as `params.relaxation_policy` and the queued run records it; "Dönem ayarı" sends nothing.
 * The run this spec queues is deleted again (no extra solver run for later specs).
 */
import { expect, test, type Request } from "@playwright/test";
import { REAL, SKIP_REASON, TERM_CODE, api, login, pickSegment, type Term } from "./helpers";

test.skip(!REAL, SKIP_REASON);

const isGenerate = (r: Request) => r.method() === "POST" && /\/api\/v1\/terms\/\d+\/studio\/generate/.test(r.url());

test("studio generate sends the chosen relaxation policy and the run records it", async ({ page }) => {
  test.setTimeout(4 * 60_000);
  await login(page);
  const term = (await api<Term[]>(page, "/terms")).find((t) => t.code === TERM_CODE)!;
  const policy = await api<{ policy: string; source: string }>(page, `/terms/${term.id}/relaxation-policy`);
  expect(["lock_first", "most_classes_first"]).toContain(policy.policy);
  expect(["term", "default"]).toContain(policy.source);

  await page.goto("/generate?step=scope");
  await expect(page.getByTestId("scope-step")).toBeVisible();
  await page.getByTestId("horizon-WEEK").click();
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 15_000 });
  await page.getByTestId("rail-step-run").click();
  await expect(page.getByTestId("generate-step")).toBeVisible();
  const control = page.getByTestId("studio-relaxation");
  await expect(control).toBeVisible();
  // the draft starts on the term setting (the control is a segmented track, or its select in a narrow column)
  await expect(control.getByTestId("studio-relax-desc")).toContainText("Dönem için seçilen kural uygulanır");
  await pickSegment(page, "Önce en çok ders", control);
  await expect(control.getByTestId("studio-relax-desc")).toContainText("Önce en çok ders yerleşir");
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 15_000 });

  let runId: number | null = null;
  try {
    const sent = page.waitForRequest(isGenerate, { timeout: 60_000 });
    await page.getByTestId("studio-generate").click();
    // real data: Bahar has hard-impossible classes, so the studio may ask first; generate anyway
    const blocked = page.getByTestId("blocked-confirm");
    await expect(page.getByTestId("run-card").or(blocked).first()).toBeVisible({ timeout: 60_000 });
    if (await blocked.isVisible()) await page.getByTestId("blocked-confirm-cancel").click();
    const req = await sent;
    const body = (req.postDataJSON() ?? {}) as { params?: Record<string, unknown> };
    expect(body.params?.relaxation_policy).toBe("most_classes_first");
    const res = await req.response();
    expect(res?.status()).toBe(202);
    runId = ((await res!.json()) as { run_id: number }).run_id;
    const run = await api<{ params: { relaxation_policy?: string } }>(page, `/runs/${runId}`);
    expect(run.params.relaxation_policy).toBe("most_classes_first");
  } finally {
    if (runId) await page.evaluate(async (id) => { await fetch(`/api/v1/runs/${id}`, { method: "DELETE" }); }, runId);
    // back to the term setting, so the next specs' drafts send no policy
    await pickSegment(page, "Dönem ayarı", control).catch(() => undefined);
    await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 15_000 }).catch(() => undefined);
  }
});
