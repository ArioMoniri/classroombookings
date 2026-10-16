/**
 * SuggestionList "Geri al" (POST /learning/suggestions/{id}/restore): the card is back under Bekleyen as soon as the
 * server answers, without waiting for the list refetch (before, it left the list for a moment and its exit
 * animation swallowed the re-entry for seconds; e2e followup.phase19 test 5).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { learningApi, type Suggestion } from "@/lib/api/learning";
import { I18nProvider } from "@/lib/i18n/provider";
import { suggestion } from "./learning-model.test";
import { SuggestionList } from "./suggestion-list";

vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, perms: [], can: () => true, canAll: () => true }) }));

/** a view of the SegmentedControl (tabs or radios, whichever it renders) */
const view = (name: RegExp) => screen.queryByRole("tab", { name }) ?? screen.getByRole("radio", { name });

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("SuggestionList Geri al", () => {
  afterEach(() => vi.restoreAllMocks());

  it("puts a dismissed suggestion back under Bekleyen right after the restore, before the refetch lands", async () => {
    const dismissed = suggestion({ id: 41, state: "dismissed", decided_at: "2026-10-16T02:00:00Z" });
    const refetch = deferred<Suggestion[]>();
    const list = vi.spyOn(learningApi, "suggestions").mockResolvedValueOnce([dismissed]).mockImplementation(() => refetch.promise);
    const restore = vi.spyOn(learningApi, "restore").mockResolvedValue({ id: 41, state: "open", undone: "dismissed", disabled_constraint_id: null });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <SuggestionList termId={2} canAct surface="moderation" />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await screen.findAllByText(/Geçmiş 1/);
    fireEvent.click(view(/Geçmiş 1/));
    const row = await screen.findByTestId("history-row");
    expect(row).toHaveAttribute("data-state", "dismissed");
    await act(async () => {
      fireEvent.click(screen.getByTestId("history-undo"));
    });
    expect(restore).toHaveBeenCalledWith(41);
    fireEvent.click(view(/Bekleyen 1/));
    // the refetch is still pending: the card comes from the cache update
    await waitFor(() => expect(document.querySelector('[data-testid="suggestion-card"][data-suggestion-id="41"]')).not.toBeNull());
    expect(list.mock.calls.length).toBeGreaterThanOrEqual(2);
    refetch.resolve([{ ...dismissed, state: "open", decided_at: null }]);
  });
});

describe("SuggestionList undo toast (T-R1-41)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("confirms an undone accept with a toast, not only for screen readers", async () => {
    const sonner = await import("sonner");
    const success = vi.spyOn(sonner.toast, "success");
    const accepted = suggestion({ id: 42, state: "accepted", decided_at: "2026-10-16T02:00:00Z", constraint_id: 9 });
    vi.spyOn(learningApi, "suggestions").mockResolvedValue([accepted]);
    vi.spyOn(learningApi, "restore").mockResolvedValue({ id: 42, state: "open", undone: "accepted", disabled_constraint_id: 9 });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <SuggestionList termId={2} canAct surface="moderation" />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await screen.findAllByText(/Geçmiş 1/);
    fireEvent.click(view(/Geçmiş 1/));
    await screen.findByTestId("history-row");
    await act(async () => {
      fireEvent.click(screen.getByTestId("history-undo"));
    });
    await waitFor(() => expect(success).toHaveBeenCalledWith("Kabul geri alındı: tercih kaldırıldı."));
  });
});
