import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { ScheduleRun } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { publishRefusals, PublishRunButton } from "./publish-run";

const run = (over: Record<string, unknown> = {}) => ScheduleRun.parse({ id: 12, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3, 4] }, status: "FEASIBLE_PARTIAL", params: {}, objective_value: null, soft_score: 80, hard_score: 100, stats: { placed: 660, events_total: 683 }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: "2026-10-15T10:00:00Z", finished_at: "2026-10-15T10:01:00Z", ...over });

function renderButton(r = run()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="en">
        <PublishRunButton run={r} published={7} exceptions={[{ key: "waived", n: 123, rules: ["capacity"] }]} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Publish a run (admin persona M-03)", () => {
  it("reads the publish guard's refusals verbatim from a 409", () => {
    const e = new HttpError(409, "409 Conflict", { detail: { message: "run cannot be published", issues: ["run 12 breaks hard rules (hard score 92); fix or re-solve before publishing"] } });
    expect(publishRefusals(e)).toEqual(["run 12 breaks hard rules (hard score 92); fix or re-solve before publishing"]);
    expect(publishRefusals(new HttpError(409, "another run of this term was published at the same time; reload", "another run of this term was published at the same time; reload"))).toEqual(["another run of this term was published at the same time; reload"]);
  });

  it("confirms with the scope, the run it replaces and the partial / exception warnings", async () => {
    renderButton();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("weeks 3–4");
    expect(dialog).toHaveTextContent("#7");
    expect(dialog).toHaveTextContent("660/683");
    expect(dialog).toHaveTextContent("123");
  });

  it("shows the server's refusal in the dialog and keeps it open", async () => {
    vi.spyOn(api.runs, "activate").mockRejectedValue(new HttpError(409, "409", { detail: { message: "run cannot be published", issues: ["run 12 is TIMEOUT; only a finished run (FEASIBLE, FEASIBLE_PARTIAL, OPTIMAL) is published"] } }));
    renderButton();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    // a partial run needs the explicit acknowledgement first
    expect(await screen.findByTestId("publish-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("publish-partial-ack"));
    await userEvent.click(screen.getByTestId("publish-confirm"));
    expect(await screen.findByRole("alert")).toHaveTextContent("run 12 is TIMEOUT; only a finished run (FEASIBLE, FEASIBLE_PARTIAL, OPTIMAL) is published");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("409 scope_reduction names the weeks lost and resends with confirm_scope_reduction", async () => {
    const spy = vi.spyOn(api.runs, "activate")
      .mockRejectedValueOnce(new HttpError(409, "409", { detail: { code: "scope_reduction", message: "run 12 covers weeks [3, 4] only", weeks_lost: [1, 2, 5], active: { run_id: 7 }, confirm_field: "confirm_scope_reduction" } }))
      .mockResolvedValueOnce(run({ is_active: true }));
    renderButton(run({ status: "FEASIBLE", stats: { placed: 683, events_total: 683 } }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    expect(await screen.findByTestId("publish-scope-reduction")).toHaveTextContent("#7");
    await userEvent.click(screen.getByTestId("publish-confirm-reduction"));
    expect(spy).toHaveBeenLastCalledWith(12, { confirmScopeReduction: true });
  });

  it("the published run says so instead of offering to publish", () => {
    renderButton(run({ is_active: true }));
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.getByText("Published")).toBeInTheDocument();
  });
});
