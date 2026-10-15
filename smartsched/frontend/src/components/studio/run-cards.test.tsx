import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { I18nProvider } from "@/lib/i18n/provider";
import { CancelRunButton } from "@/components/runs/cancel-run";
import { runTone } from "./run-cards";

afterEach(() => vi.unstubAllGlobals());

describe("run result tone (Phase 9: FEASIBLE_PARTIAL is a usable amber result)", () => {
  it("good / partial / bad / running", () => {
    expect(runTone("OPTIMAL")).toBe("good");
    expect(runTone("FEASIBLE")).toBe("good");
    expect(runTone("FEASIBLE_PARTIAL")).toBe("partial");
    expect(runTone("INFEASIBLE")).toBe("bad");
    expect(runTone("RUNNING")).toBe("running");
  });
});

describe("cancelling a run (Review follow-ups: POST /runs/{id}/cancel, never DELETE)", () => {
  it("api.runs.cancel posts to /runs/{id}/cancel", async () => {
    const calls: { url: string; method: string }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET" });
      return new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    await api.runs.cancel(5).catch(() => undefined);
    expect(calls[0].url).toContain("/runs/5/cancel");
    expect(calls[0].method).toBe("POST");
  });

  it("the run page button asks the server to cancel and says so while it works", async () => {
    let resolve: () => void = () => undefined;
    const cancel = vi.spyOn(api.runs, "cancel").mockImplementation(() => new Promise((r) => (resolve = () => r({} as never))));
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="en">
          <CancelRunButton runId={5} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const btn = screen.getByRole("button", { name: "Cancel run" });
    await userEvent.click(btn);
    expect(cancel).toHaveBeenCalledWith(5);
    expect(btn).toHaveAttribute("aria-busy", "true");
    resolve();
  });
});
