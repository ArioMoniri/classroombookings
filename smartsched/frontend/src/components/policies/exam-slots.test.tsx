/** AS-17 exam hold mode `slots`: the mode is read back (no longer folded to "off"), buffer + effect save, freed room-periods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptiveApi } from "@/lib/api/adaptive";
import { ExamPeriod, policiesApi } from "@/lib/api/booking-policies";
import { I18nProvider } from "@/lib/i18n/provider";
import { ExamSlotsOptions } from "./exam-slots";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("ExamPeriod schema", () => {
  it("keeps the slots mode with its buffer and effect (defaults 1 / request)", () => {
    expect(ExamPeriod.parse({ mode: "slots", room_ids: [1] })).toMatchObject({ mode: "slots", buffer_periods: 1, slots_effect: "request" });
    expect(ExamPeriod.parse({ mode: "slots", buffer_periods: 2, slots_effect: "refuse" })).toMatchObject({ buffer_periods: 2, slots_effect: "refuse" });
  });
});

describe("ExamSlotsOptions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the buffer and the effect and names the freed room-periods", async () => {
    vi.spyOn(adaptiveApi, "exams").mockResolvedValue({ method: "requests", confidence: "high", days: [], slots: [], holds: { exam_run_id: 9, buffer_periods: 1, held_room_periods: 120, freed_room_periods: 860 } });
    const save = vi.spyOn(policiesApi, "examPeriod").mockResolvedValue(ExamPeriod.parse({ mode: "slots" }));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr"><ExamSlotsOptions exam={ExamPeriod.parse({ mode: "slots" })} termId={4} /></I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("860 oda-saat rezervasyona açıldı, 120 oda-saat sınavlar için tutuluyor.")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("exam-buffer"), { target: { value: "2" } });
    await waitFor(() => expect(save).toHaveBeenCalledWith({ buffer_periods: 2 }));
    fireEvent.click(screen.getByTestId("exam-effect-refuse"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ slots_effect: "refuse" }));
  });
});
