/**
 * HX-06 hand-overs on the runs pages: `?publish=` opens the run's own publish dialog (nothing is published until its
 * confirm), `?chat=` puts the text into the run chat's composer (nothing is sent until the person sends it).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { ScheduleRun } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { PromptComposer } from "@/components/ui/beautifului/prompt-composer";
import { PublishRunButton } from "./publish-run";

const run = ScheduleRun.parse({ id: 12, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", params: {}, objective_value: null, soft_score: 80, hard_score: 100, stats: { placed: 683, events_total: 683 }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: "2026-10-15T10:00:00Z", finished_at: "2026-10-15T10:01:00Z" });

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

afterEach(() => vi.restoreAllMocks());

describe("hand-over prefills on the runs pages", () => {
  it("?publish= opens the publish dialog and publishes nothing by itself", async () => {
    const activate = vi.spyOn(api.runs, "activate");
    wrap(<PublishRunButton run={run} published={7} autoOpen />);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(activate).not.toHaveBeenCalled();
  });

  it("without the param the dialog stays closed", () => {
    wrap(<PublishRunButton run={run} published={7} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("?chat= prefills the composer; it is sent only by the person", () => {
    const onSend = vi.fn();
    wrap(<PromptComposer onSend={onSend} label="Mesaj" sendLabel="Gönder" initialDraft="MAT 112'yi salıya taşı" />);
    expect(screen.getByLabelText("Mesaj")).toHaveValue("MAT 112'yi salıya taşı");
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    expect(onSend).toHaveBeenCalledWith("MAT 112'yi salıya taşı");
  });
});
