/** Studio Generate sends the relaxation policy the planner picked (Dönem ayarı = nothing sent, the term setting
 * decides; Önce kilitliler / Önce en çok ders = `params.relaxation_policy`), backend `app/services/studio.py`. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useReducer } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PolicyPicker } from "@/components/runs/relaxation";
import { I18nProvider } from "@/lib/i18n/provider";

const calls = vi.hoisted(() => ({ generate: [] as unknown[] }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  api: { studio: { generate: async (_term: number, _kind: string, body: unknown) => { calls.generate.push(body); return { run_id: 21, status: "QUEUED" }; } } },
}));
const ctx = vi.hoisted(() => ({ params: {} as Record<string, unknown> }));
vi.mock("./studio-context", () => ({
  useStudio: () => ({
    termId: 1,
    kind: "COURSE",
    flush: async () => true,
    runPrecheck: async () => null,
    store: { getState: () => ({ setActiveRun: vi.fn() }) },
    summary: { lastGoodRunId: null },
    local: { params: ctx.params },
    goStep: vi.fn(),
  }),
}));

import { GenerateProvider, useGenerate } from "./use-generate";

function Harness({ rerender }: { rerender: () => void }) {
  // the generate step's control: "term" clears the param, a policy sets it (studio-reducer setParams)
  const { generate } = useGenerate();
  const value = (ctx.params.relaxation_policy as "lock_first" | "most_classes_first" | null | undefined) ?? "term";
  return (
    <>
      <PolicyPicker id="studio-relax" value={value} onChange={(v) => { ctx.params = { ...ctx.params, relaxation_policy: v === "term" ? null : v }; rerender(); }} />
      <button type="button" onClick={() => void generate()}>go</button>
    </>
  );
}

function Root() {
  const [, rerender] = useReducer((x: number) => x + 1, 0);
  return (
    <GenerateProvider>
      <Harness rerender={rerender} />
    </GenerateProvider>
  );
}

function wrap() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <Root />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls.generate = [];
  ctx.params = { time_limit_s: 60 };
});

describe("studio generate relaxation policy", () => {
  it("sends nothing for Dönem ayarı and the chosen policy otherwise", async () => {
    const user = userEvent.setup();
    wrap();
    expect(screen.getByRole("radio", { name: "Dönem ayarı" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "go" }));
    await waitFor(() => expect(calls.generate).toHaveLength(1));
    expect((calls.generate[0] as { params: Record<string, unknown> }).params).not.toHaveProperty("relaxation_policy");
    await user.click(screen.getByRole("radio", { name: "Önce en çok ders" }));
    await user.click(screen.getByRole("button", { name: "go" }));
    await waitFor(() => expect(calls.generate).toHaveLength(2));
    expect((calls.generate[1] as { params: Record<string, unknown> }).params).toMatchObject({ time_limit_s: 60, relaxation_policy: "most_classes_first" });
    await user.click(screen.getByRole("radio", { name: "Dönem ayarı" }));
    await user.click(screen.getByRole("button", { name: "go" }));
    await waitFor(() => expect(calls.generate).toHaveLength(3));
    expect((calls.generate[2] as { params: Record<string, unknown> }).params).not.toHaveProperty("relaxation_policy");
  });
});
