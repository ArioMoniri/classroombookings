// Helpers shared by the journeys. Selectors are the data-testids the real-backend e2e specs use
// (smartsched/frontend/e2e/*.spec.ts), so a journey breaks together with a spec, not silently.
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
export const FIXTURES = resolve(REPO, "smartsched/backend/tests/fixtures");

/** Caption in the requested language. */
export const tr = (ctx, en, trText) => (ctx.lang === "tr" ? trText : en);

/** Log in through the UI without recording it (used in setup(), before the sync flash). */
export async function login(page, { email, password }) {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(email);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

/** Same-origin API call through the Next proxy (the httpOnly cookie carries the JWT). */
export async function api(page, path, { method = "GET", body } = {}) {
  const res = await page.evaluate(
    async ({ url, method, body }) => {
      const r = await fetch(url, {
        method,
        headers: { Accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
      let data = null;
      try {
        data = await r.json();
      } catch {
        /* empty */
      }
      return { status: r.status, data };
    },
    { url: `/api/v1${path}`, method, body },
  );
  return res;
}

export async function termId(page, code) {
  const { data } = await api(page, "/terms");
  const t = (data ?? []).find((x) => x.code === code) ?? (data ?? [])[0];
  if (!t) throw new Error("no term: run scripts/record/stack.sh up first");
  return t.id;
}

/** The newest run of a kind with a given status set (e.g. a FEASIBLE COURSE run for the grid). */
export async function findRun(page, tid, { kind = "COURSE", statuses = ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"], withDiagnoses = false } = {}) {
  const { data } = await api(page, `/runs?term_id=${tid}`);
  const runs = (data ?? []).filter((r) => r.kind === kind && statuses.includes(r.status));
  if (!withDiagnoses) return runs[0] ?? null;
  for (const r of runs) {
    const { data: full } = await api(page, `/runs/${r.id}`);
    if ((full?.diagnosis ?? full?.diagnoses ?? []).length) return full;
  }
  return null;
}
