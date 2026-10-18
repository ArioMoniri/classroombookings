/** FIX-F AS20-F08: an active admin profile (a first version too) can be switched off in the UI, behind a confirmation. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seasonsApi, type Profile } from "@/lib/api/seasons";
import { I18nProvider } from "@/lib/i18n/provider";
import { SeasonProfiles } from "./season-profiles";

vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, name: "2026 Bahar" }, terms: [{ id: 2, name: "2026 Bahar" }], isLoading: false }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const base: Profile = {
  id: 1, key: "as20", version: 1, name: { tr: "AS20 Bahar yoğun saat", en: "x" }, name_tr: "AS20 Bahar yoğun saat", name_en: "x",
  applies_to: [{ season: "FINAL", period_kind: "EXAM" }], solver_weights: {}, booking_overlays: [], peak_threshold_pct: 85,
  status: "active", builtin: false, origin: "admin", parent_id: null, approved_at: "2026-10-01T10:00:00", explanation: {}, evidence: {},
  source: "profile:as20@1", weights_diff: [],
};

describe("SeasonProfiles · Kullanımdan kaldır", () => {
  beforeEach(() => {
    vi.spyOn(seasonsApi, "periods").mockResolvedValue({ term_id: 2, periods: [], segments: [], needs: { tr: "x", en: "x" } });
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 0; });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("retires an active v1 after a confirmation", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue({ profiles: [base], weight_keys: [], defaults: {}, seasons: [], period_kinds: [] });
    const remove = vi.spyOn(seasonsApi, "remove").mockResolvedValue(undefined as never);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr"><SeasonProfiles /></I18nProvider>
      </QueryClientProvider>,
    );
    const row = await screen.findByTestId("profile-row");
    fireEvent.click(within(row).getByTestId("profile-retire"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("AS20 Bahar yoğun saat kullanımdan kaldırılsın mı?");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Kaldır" })); });
    await waitFor(() => expect(remove).toHaveBeenCalledWith(1));
  });
});
