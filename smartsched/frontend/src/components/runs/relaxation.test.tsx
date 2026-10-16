/** Relaxation policy per run (Re-solve dialog → POST /runs params) and per term (Settings › Çözücü,
 * GET/PUT /terms/{id}/relaxation-policy), and the line the run report shows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { ScheduleRun } from "@/lib/api/schemas";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push, replace: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/runs/4" }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 1, code: "2026-BAHAR" } }) }));
const db = vi.hoisted(() => ({ runs: [] as unknown[], posts: [] as { path: string; method: string; body: unknown }[], policy: { policy: "lock_first", source: "default" } as { policy: string; source: string }, admin: true }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: (p: string) => p !== "planning.admin" || db.admin }) }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
    const policyOut = () => ({ term_id: 1, ...db.policy, default: "lock_first", options: ["lock_first", "most_classes_first"], stored_invalid: false });
    if (opts.method === "POST" || opts.method === "PUT") {
      db.posts.push({ path, method: opts.method, body: opts.body });
      if (path === "/terms/1/relaxation-policy") {
        const p = (opts.body as { policy: string | null }).policy;
        db.policy = p ? { policy: p, source: "term" } : { policy: "lock_first", source: "default" };
        return opts.schema ? opts.schema.parse(policyOut()) : policyOut();
      }
      return path === "/runs" ? { run_id: 9, status: "QUEUED" } : {};
    }
    if (path === "/runs") return opts.schema ? opts.schema.parse(db.runs) : db.runs;
    if (path === "/terms/1/relaxation-policy") return opts.schema ? opts.schema.parse(policyOut()) : policyOut();
    throw new Error(`unexpected ${path}`);
  },
}));

import { PolicyPicker, RunPolicyLine, policyParams, runPolicy } from "./relaxation";
import { RelaxationTermCard } from "./relaxation-term-card";
import { ResolveRunButton, resolveBody } from "./resolve-run";

const raw = (id: number, stats: Record<string, unknown>, params: Record<string, unknown> = {}) => ({
  id, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "TERM", horizon_params: {}, status: "FEASIBLE", label: null, params,
  objective_value: null, soft_score: 90, hard_score: 100, stats, diagnosis: [], parent_run_id: null, prompt_text: null,
  created_at: "2026-10-16T08:00:00", finished_at: "2026-10-16T08:01:00", is_active: false,
});
const asRun = (r: ReturnType<typeof raw>) => ({ ...r, horizon_params: { weeks: [], dates: [] }, progress: 100, params: { time_limit_s: 60, seed: 0, workers: 8, stability: true, weights: {}, ...r.params }, stats: {}, stats_detail: r.stats, objective_breakdown: {} }) as unknown as ScheduleRun;

function wrap(ui: React.ReactNode, locale: "tr" | "en" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  db.posts = [];
  db.runs = [];
  nav.push.mockReset();
});

describe("policy helpers", () => {
  it("reads what a run used and what a choice sends", () => {
    expect(runPolicy(asRun(raw(1, { relaxation_policy: { policy: "most_classes_first", source: "run" } })))).toEqual({ policy: "most_classes_first", source: "run" });
    expect(runPolicy(asRun(raw(1, {})))).toBeNull();
    expect(policyParams("term")).toEqual({});
    expect(policyParams("lock_first")).toEqual({ relaxation_policy: "lock_first" });
  });
  it("re-solves with the run as parent, stability on and the same horizon", () => {
    const r = { ...asRun(raw(4, {})), horizon: "WEEK" as const, horizon_params: { weeks: [3], dates: [] } };
    expect(resolveBody(r, "most_classes_first", "  Bahar W3 ")).toEqual({ term_id: 1, kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, parent_run_id: 4, params: { stability: true, relaxation_policy: "most_classes_first" }, label: "Bahar W3" });
    expect(resolveBody(asRun(raw(4, {})), "term", "")).toEqual({ term_id: 1, kind: "COURSE", horizon: "TERM", parent_run_id: 4, params: { stability: true } });
  });
});

describe("PolicyPicker / RunPolicyLine", () => {
  it("is a labelled radio group with the chosen rule explained", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<PolicyPicker id="p" value="term" onChange={onChange} />, "tr");
    expect(screen.getByRole("radiogroup", { name: "Her ders sığmazsa" })).toBeInTheDocument();
    expect(screen.getByTestId("p-desc")).toHaveTextContent("Dönem için seçilen kural uygulanır");
    await user.click(screen.getByRole("radio", { name: "Önce en çok ders" }));
    expect(onChange).toHaveBeenCalledWith("most_classes_first");
  });
  it("tells which rule a run used and where it came from", () => {
    wrap(<RunPolicyLine r={asRun(raw(1, { relaxation_policy: { policy: "lock_first", source: "term" } }))} />);
    expect(screen.getByTestId("run-relaxation-policy")).toHaveTextContent("Classes that do not fit: locked rows first (term setting)");
  });
});

describe("ResolveRunButton", () => {
  it("opens by itself from ?resolve=1, posts the child run and goes to it", async () => {
    const user = userEvent.setup();
    wrap(<ResolveRunButton run={asRun(raw(4, {}, { source: "COUNCIL_BASELINE" }))} autoOpen />);
    expect(await screen.findByTestId("resolve-run")).toHaveTextContent("Solve keeping the imported schedule");
    await user.click(screen.getByRole("radio", { name: "Most classes first" }));
    await user.click(screen.getByTestId("resolve-run-start"));
    await waitFor(() => expect(db.posts).toContainEqual({ path: "/runs", method: "POST", body: { term_id: 1, kind: "COURSE", horizon: "TERM", parent_run_id: 4, params: { stability: true, relaxation_policy: "most_classes_first" } } }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/runs/9"));
  });
});

describe("RelaxationTermCard", () => {
  beforeEach(() => {
    db.policy = { policy: "most_classes_first", source: "term" };
    db.admin = true;
  });
  it("reads the stored term value, saves a new one and clears it back to the default", async () => {
    const user = userEvent.setup();
    wrap(<RelaxationTermCard />);
    expect(await screen.findByText("This term's setting: the most classes first.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Most classes first" })).toBeChecked();
    expect(screen.getByTestId("relax-term-save")).toBeDisabled(); // nothing changed yet
    await user.click(screen.getByRole("radio", { name: "Locked first" }));
    await user.click(screen.getByTestId("relax-term-save"));
    await waitFor(() => expect(db.posts).toContainEqual({ path: "/terms/1/relaxation-policy", method: "PUT", body: { policy: "lock_first" } }));
    expect(await screen.findByText("This term's setting: locked rows first.")).toBeInTheDocument();
    await user.click(screen.getByTestId("relax-term-clear"));
    await waitFor(() => expect(db.posts).toContainEqual({ path: "/terms/1/relaxation-policy", method: "PUT", body: { policy: null } }));
    expect(await screen.findByTestId("relax-term-known")).toHaveAttribute("data-source", "default");
    expect(screen.queryByTestId("relax-term-clear")).not.toBeInTheDocument();
  });
  it("shows the default to non-administrators without a save button", async () => {
    db.policy = { policy: "lock_first", source: "default" };
    db.admin = false;
    wrap(<RelaxationTermCard />, "tr");
    expect(await screen.findByText("Bu dönem için seçim yok; varsayılan uygulanır: önce kilitli satırlar.")).toBeInTheDocument();
    expect(screen.queryByTestId("relax-term-save")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Önce kilitliler" })).toBeDisabled();
  });
});
