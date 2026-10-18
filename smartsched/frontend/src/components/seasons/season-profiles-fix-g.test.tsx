/**
 * FIX-G AS20-F09: a planner drafts and edits season profiles, only an admin approves (no "Etkinleştir", "Geri al",
 * "Kullanımdan kaldır" or "Düzenlemelerden ağırlık öner" for a planner). AS20-F08: retired keys fold into "Eski profiller".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seasonsApi, type Profile } from "@/lib/api/seasons";
import { I18nProvider } from "@/lib/i18n/provider";
import { routeRequirement } from "@/lib/permissions";
import { SeasonProfiles } from "./season-profiles";

vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, name: "2026 Bahar" }, terms: [{ id: 2, name: "2026 Bahar" }], isLoading: false }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const p = (over: Partial<Profile>): Profile => ({
  id: 1, key: "a", version: 1, name: { tr: "A profili", en: "A" }, name_tr: "A profili", name_en: "A",
  applies_to: [{ season: "FINAL", period_kind: "EXAM" }], solver_weights: {}, booking_overlays: [], peak_threshold_pct: 85,
  status: "active", builtin: false, origin: "admin", parent_id: null, approved_at: "2026-10-01T10:00:00", explanation: {}, evidence: {},
  source: "profile:a@1", weights_diff: [], ...over,
});

const list = [
  p({ id: 1, key: "a", status: "active" }),
  p({ id: 2, key: "a", version: 2, status: "draft", parent_id: 1, approved_at: null }),
  p({ id: 3, key: "b", name: { tr: "B taslağı", en: "B" }, name_tr: "B taslağı", status: "draft", approved_at: null }),
  p({ id: 4, key: "c", name: { tr: "Eski C", en: "Old C" }, name_tr: "Eski C", status: "retired" }),
];

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr"><SeasonProfiles /></I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SeasonProfiles · planner drafts, admin approves", () => {
  beforeEach(() => {
    vi.spyOn(seasonsApi, "periods").mockResolvedValue({ term_id: 2, periods: [], segments: [], needs: { tr: "x", en: "x" } });
  });
  afterEach(() => vi.restoreAllMocks());

  it("a planner sees Düzenle and Taslağı sil, never the approval actions", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue({ profiles: list, weight_keys: [], defaults: {}, seasons: [], period_kinds: [], can_activate: false });
    mount();
    const live = await screen.findByTestId("profile-list");
    const rows = within(live).getAllByTestId("profile-row");
    expect(rows).toHaveLength(2);
    expect(screen.queryByTestId("profile-activate")).toBeNull();
    expect(screen.queryByTestId("profile-revert")).toBeNull();
    expect(screen.queryByTestId("profile-retire")).toBeNull();
    expect(screen.queryByTestId("profile-propose")).toBeNull();
    expect(screen.getByTestId("profile-new")).toBeInTheDocument();
    expect(within(rows[0]!).getByTestId("profile-edit")).toBeInTheDocument();
    expect(within(rows[0]!).getByTestId("profile-delete")).toBeInTheDocument();
    expect(within(rows[0]!).getByTestId("profile-awaiting")).toHaveTextContent("Bir yönetici onaylayınca uygulanır.");
    // the season calendar stays an admin tool
    expect(seasonsApi.periods).not.toHaveBeenCalled();
  });

  it("an admin keeps Etkinleştir; retired keys sit under Eski profiller", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue({ profiles: list, weight_keys: [], defaults: {}, seasons: [], period_kinds: [], can_activate: true });
    mount();
    const live = await screen.findByTestId("profile-list");
    expect(within(live).getAllByTestId("profile-activate")).toHaveLength(2);
    expect(within(live).queryByText("Eski C")).toBeNull();
    const old = screen.getByTestId("profile-retired");
    expect(old).toHaveTextContent("Eski profiller (1)");
    expect(within(old).getByText("Eski C")).toBeInTheDocument();
    // a retired version is read-only: no actions on its row
    expect(within(old).queryByTestId("profile-edit")).toBeNull();
  });

  it("/admin/weeks lets a planner in (the week editors stay behind setup.timetable_weeks)", () => {
    expect(routeRequirement("/admin/weeks")).toEqual(["setup.timetable_weeks", "planning.edit"]);
  });
});
