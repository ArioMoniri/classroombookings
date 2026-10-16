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
    expect(screen.getByTestId("publish-confirm")).toBeDisabled(); // the week run also needs the scope tick
    await userEvent.click(screen.getByTestId("publish-scope-ack"));
    await userEvent.click(screen.getByTestId("publish-confirm"));
    expect(await screen.findByTestId("publish-refused")).toHaveTextContent("run 12 is TIMEOUT; only a finished run (FEASIBLE, FEASIBLE_PARTIAL, OPTIMAL) is published");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("a week run replacing a published run needs the scope tick before it is sent (round-1 R1-M-02)", async () => {
    const spy = vi.spyOn(api.runs, "activate").mockResolvedValueOnce(run({ is_active: true }));
    renderButton(run({ status: "FEASIBLE", stats: { placed: 683, events_total: 683 } }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByTestId("publish-scope-reduction")).toHaveTextContent("#7");
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("publish-scope-ack"));
    await userEvent.click(screen.getByTestId("publish-confirm"));
    expect(spy).toHaveBeenLastCalledWith(12, { confirmScopeReduction: true, confirmForcedBreaks: false });
  });

  it("409 scope_reduction names the weeks lost, asks for the tick and resends with confirm_scope_reduction", async () => {
    const spy = vi.spyOn(api.runs, "activate")
      .mockRejectedValueOnce(new HttpError(409, "409", { detail: { code: "scope_reduction", message: "run 12 covers weeks [3, 4] only", message_tr: "#12 yalnız 3, 4. haftaları kapsıyor", weeks_lost: [1, 2, 5], active: { run_id: 7 }, confirm_field: "confirm_scope_reduction" } }))
      .mockResolvedValueOnce(run({ is_active: true }));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="en">
          {/* a term run: no tick up front, the server answers 409 */}
          <PublishRunButton run={run({ status: "FEASIBLE", horizon: "TERM", horizon_params: { weeks: [] }, stats: { placed: 683, events_total: 683 } })} published={null} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    const box = await screen.findByTestId("publish-scope-reduction");
    expect(box).toHaveTextContent("weeks 1–2, 5");
    expect(screen.getByTestId("publish-confirm-reduction")).toBeDisabled();
    await userEvent.click(screen.getByTestId("publish-scope-ack"));
    await userEvent.click(screen.getByTestId("publish-confirm-reduction"));
    expect(spy).toHaveBeenLastCalledWith(12, { confirmScopeReduction: true, confirmForcedBreaks: false });
  });

  it("409 forced_breaks lists every forced break with its reason and resends with confirm_forced_breaks (R1-S-01)", async () => {
    const spy = vi.spyOn(api.runs, "activate")
      .mockRejectedValueOnce(new HttpError(409, "409", { detail: { code: "forced_breaks", message_tr: "#12 1 kesin kuralı gerekçeli zorunlu taşımayla bozuyor", breaks: [{ rule: "tags", message: "PHAR 240 §1 placed in the medicine (TIP) room A201", reason: "Bölüm başkanı onayı" }] } }))
      .mockResolvedValueOnce(run({ is_active: true }));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="en">
          <PublishRunButton run={run({ status: "FEASIBLE", horizon: "TERM", horizon_params: { weeks: [] }, stats: { placed: 683, events_total: 683 } })} published={null} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    const box = await screen.findByTestId("publish-forced-breaks");
    expect(box).toHaveTextContent("TIP");
    expect(box).toHaveTextContent("Bölüm başkanı onayı");
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("publish-forced-ack"));
    await userEvent.click(screen.getByTestId("publish-confirm"));
    expect(spy).toHaveBeenLastCalledWith(12, { confirmScopeReduction: false, confirmForcedBreaks: true });
  });

  it("a non-stale 409 is shown in the server's words, never as 'someone else changed it' (R1-S-06)", async () => {
    vi.spyOn(api.runs, "activate").mockRejectedValue(new HttpError(409, "409 Conflict", { detail: { message: "run cannot be published", issues: ["run 11 is ERROR; only a finished run (FEASIBLE, FEASIBLE_PARTIAL, OPTIMAL) is published"] } }));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <PublishRunButton run={run({ status: "FEASIBLE", horizon: "TERM", horizon_params: { weeks: [] }, stats: { placed: 683, events_total: 683 } })} published={null} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Yayınla" }));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    const alert = await screen.findByTestId("publish-refused");
    expect(alert).toHaveTextContent("run 11 is ERROR");
    expect(alert).not.toHaveTextContent("başka biri değiştirdi");
  });

  it("the published run says so instead of offering to publish", () => {
    renderButton(run({ is_active: true }));
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.getByText("Published")).toBeInTheDocument();
  });
});
