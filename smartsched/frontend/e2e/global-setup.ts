/**
 * Global setup for the real-backend browser run (E2E_REAL=1; see playwright.config.ts).
 *
 * Fails fast when the backend is not reachable, and resolves the run ids the specs read from the
 * environment when they are not set explicitly:
 *   E2E_BOARD_RUN   the imported weekly board of the term (a FEASIBLE COURSE run made by the grid import)
 *   E2E_SOLVER_RUN  the newest finished full-term COURSE run the solver produced (e2e-backend-entry.sh makes one)
 *   AUDIT_RUN       the run report the motion audit measures (defaults to E2E_SOLVER_RUN)
 * Values set here are inherited by the test workers.
 */
import { request } from "@playwright/test";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!";
const TERM = process.env.E2E_TERM_CODE ?? "2026-BAHAR";
/** finished runs with a timetable to look at (a partial best effort is still one) */
const USABLE = new Set(["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"]);

type Term = { id: number; code: string };
type Run = { id: number; term_id: number; kind: string; horizon: string; status: string; label: string | null; created_at?: string };

export default async function globalSetup(): Promise<void> {
  const ctx = await request.newContext();
  try {
    const health = await ctx.get(`${API}/health`).catch((e: unknown) => {
      throw new Error(`E2E_REAL=1 but the backend at ${API} is not reachable (${String(e)}). Start it first: smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh`);
    });
    if (!health.ok()) throw new Error(`backend ${API}/health answered ${health.status()}`);

    const login = await ctx.post(`${API}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
    if (!login.ok()) throw new Error(`seeded admin ${EMAIL} cannot sign in (${login.status()}): ${await login.text()}`);
    const { access_token: token } = (await login.json()) as { access_token: string };
    const get = async <T>(path: string): Promise<T> => {
      const res = await ctx.get(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok()) throw new Error(`GET ${path} → ${res.status()} ${await res.text()}`);
      return (await res.json()) as T;
    };

    const terms = await get<Term[]>("/terms");
    const term = terms.find((t) => t.code === TERM);
    if (!term) throw new Error(`term ${TERM} is not imported (terms: ${terms.map((t) => t.code).join(", ") || "none"})`);
    const runs = (await get<Run[]>(`/runs?term_id=${term.id}`)).filter((r) => r.term_id === term.id).sort((a, b) => a.id - b.id);

    if (!process.env.E2E_BOARD_RUN) {
      const board = runs.find((r) => r.kind === "COURSE" && ["FEASIBLE", "OPTIMAL"].includes(r.status));
      if (board) process.env.E2E_BOARD_RUN = String(board.id);
    }
    if (!process.env.E2E_SOLVER_RUN) {
      const solver = [...runs].reverse().find((r) => r.kind === "COURSE" && r.horizon === "TERM" && USABLE.has(r.status) && String(r.id) !== process.env.E2E_BOARD_RUN);
      if (solver) process.env.E2E_SOLVER_RUN = String(solver.id);
    }
    process.env.AUDIT_RUN ??= process.env.E2E_SOLVER_RUN ?? process.env.E2E_BOARD_RUN;
    console.log(`e2e: backend ${API}, term ${TERM} #${term.id}, board run #${process.env.E2E_BOARD_RUN ?? "?"}, solver run #${process.env.E2E_SOLVER_RUN ?? "?"}, audit run #${process.env.AUDIT_RUN ?? "?"}`);
  } finally {
    await ctx.dispose();
  }
}
