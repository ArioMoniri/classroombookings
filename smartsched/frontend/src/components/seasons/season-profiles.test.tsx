/**
 * AS-15 season profiles on /admin/weeks: the list stands each key on its active version, a draft offers
 * "Onayla ve etkinleştir" behind a confirmation, revert re-activates the parent, the weights sit behind "Gelişmiş",
 * and after a confirmation focus lands on the row (never on <body>).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { seasonsApi, type Profile, type ProfileList } from "@/lib/api/seasons";
import { I18nProvider } from "@/lib/i18n/provider";
import { SeasonProfiles } from "./season-profiles";

vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: { id: 2, name: "2026 Bahar" }, terms: [{ id: 2, name: "2026 Bahar" }], isLoading: false }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const base: Profile = {
  id: 1, key: "final_pc", version: 1, name: { tr: "Final PC", en: "Final PC" }, name_tr: "Final PC", name_en: "Final PC",
  applies_to: [{ season: "FINAL", period_kind: "EXAM" }], solver_weights: {}, booking_overlays: [], peak_threshold_pct: 85,
  status: "active", builtin: false, origin: "admin", parent_id: null, approved_at: "2026-10-01T10:00:00", explanation: {}, evidence: {},
  source: "profile:final_pc@1", weights_diff: [],
};

function list(profiles: Profile[]): ProfileList {
  return {
    profiles: [{ ...base, id: null, key: "standard", builtin: true, name: { tr: "Standart", en: "Standard" }, applies_to: [{ season: "*", period_kind: "*" }] }, ...profiles],
    weight_keys: ["building_preference", "room_preference"],
    defaults: { building_preference: 5, room_preference: 10 },
    seasons: [{ key: "FINAL", label: { tr: "Final", en: "Final exams" } }],
    period_kinds: [{ key: "EXAM", label: { tr: "Sınav dönemi", en: "Exam period" } }],
  };
}

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <SeasonProfiles />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SeasonProfiles", () => {
  beforeEach(() => {
    vi.spyOn(seasonsApi, "periods").mockResolvedValue({ term_id: 2, periods: [], segments: [], needs: { tr: "Takvim yok", en: "No calendar" } });
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 0; });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("lists the built-in read-only and a draft with its explanation, weights diff and a confirmed activate", async () => {
    const draft: Profile = { ...base, id: 2, version: 2, status: "draft", parent_id: 1, origin: "learned", explanation: { tr: "Final haftasında bina tercihi daha önemli." }, evidence: { edits: 12 }, weights_diff: [{ key: "building_preference", default: 5, value: 8 }] };
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue(list([base, draft]));
    const activate = vi.spyOn(seasonsApi, "activate").mockResolvedValue({ ...draft, status: "active" });
    mount();
    const rows = await screen.findAllByTestId("profile-row");
    expect(rows[0]).toHaveTextContent("Standart");
    expect(rows[0]).toHaveTextContent("Hazır profil: değiştirilemez.");
    const row = rows[1]!;
    expect(row).toHaveTextContent("Etkin · v1");
    expect(row).toHaveTextContent("Taslak · v2");
    expect(row).toHaveTextContent("Öğrenilmiş öneri");
    expect(within(row).getByTestId("profile-explanation")).toHaveTextContent("bina tercihi daha önemli");
    expect(within(row).getByTestId("profile-weights")).toHaveTextContent("Talep edilen bina58");
    expect(row).toHaveTextContent("Geçerli: Final · Sınav dönemi");
    fireEvent.click(within(row).getByTestId("profile-activate"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Final PC v2 etkinleştirilsin mi?");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Etkinleştir" })); });
    await waitFor(() => expect(activate).toHaveBeenCalledWith(2));
    await waitFor(() => expect(document.activeElement).toBe(screen.getAllByTestId("profile-row")[1]));
  });

  it("offers Geri al on an active version with a parent and no pending draft", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue(list([{ ...base, status: "retired" }, { ...base, id: 2, version: 2, parent_id: 1 }]));
    const revert = vi.spyOn(seasonsApi, "revert").mockResolvedValue(base);
    mount();
    fireEvent.click(await screen.findByTestId("profile-revert"));
    const dialog = await screen.findByRole("alertdialog");
    await act(async () => { fireEvent.click(within(dialog).getByRole("button", { name: "Geri al" })); });
    await waitFor(() => expect(revert).toHaveBeenCalledWith(2));
  });

  it("creates a draft from the form; the weights are behind Gelişmiş and only changed ones are sent", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue(list([]));
    const create = vi.spyOn(seasonsApi, "create").mockResolvedValue({ ...base, id: 9, key: "final_haftasi", status: "draft" });
    mount();
    fireEvent.click(await screen.findByTestId("profile-new"));
    const form = await screen.findByTestId("profile-form");
    expect(within(form).getByTestId("pf-advanced")).not.toHaveAttribute("open");
    fireEvent.change(within(form).getByTestId("pf-name-tr"), { target: { value: "Final haftası" } });
    fireEvent.change(within(form).getByTestId("pf-weight-building_preference"), { target: { value: "8" } });
    fireEvent.change(within(form).getByTestId("pf-weight-room_preference"), { target: { value: "10" } });
    await act(async () => { fireEvent.click(within(form).getByTestId("pf-save")); });
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]?.[0]).toMatchObject({ key: "final_haftasi", name_tr: "Final haftası", applies_to: [{ season: "*", period_kind: "EXAM" }], solver_weights: { building_preference: 8 }, peak_threshold_pct: 85 });
  });

  it("shows the server's Turkish refusal in the form", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue(list([]));
    const { HttpError } = await import("@/lib/api/client");
    vi.spyOn(seasonsApi, "create").mockRejectedValue(new HttpError(422, "x", { detail: { code: "profile_invalid", message_tr: "ağırlık 0 ile 10000 arasında olmalı", message_en: "weight out of range" } }));
    mount();
    fireEvent.click(await screen.findByTestId("profile-new"));
    fireEvent.change(await screen.findByTestId("pf-name-tr"), { target: { value: "X" } });
    await act(async () => { fireEvent.click(screen.getByTestId("pf-save")); });
    expect(await screen.findByTestId("pf-error")).toHaveTextContent("ağırlık 0 ile 10000 arasında olmalı");
  });

  it("'Düzenlemelerden ağırlık öner' shows the backend's needs sentence with fewer than 5 edits, else focuses the draft", async () => {
    vi.spyOn(seasonsApi, "profiles").mockResolvedValue(list([{ ...base, key: "learned_bahar", status: "draft", origin: "learned" }]));
    const propose = vi.spyOn(seasonsApi, "proposeWeights").mockResolvedValueOnce({ edits: 3, confidence: "none", needs: { tr: "En az 5 elle düzenleme gerekli (şu an 3)", en: "x" }, proposal: null });
    mount();
    await act(async () => { fireEvent.click(await screen.findByTestId("profile-propose")); });
    await waitFor(() => expect(propose).toHaveBeenCalledWith(2));
    expect(await screen.findByTestId("profile-propose-note")).toHaveTextContent("En az 5 elle düzenleme gerekli (şu an 3)");
    propose.mockResolvedValueOnce({ edits: 12, confidence: "medium", needs: null, proposal: { profile_id: 4, key: "learned_bahar", version: 1 } });
    await act(async () => { fireEvent.click(screen.getByTestId("profile-propose")); });
    await waitFor(() => expect(screen.queryByTestId("profile-propose-note")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getAllByTestId("profile-row").find((r) => r.dataset.rowKey === "learned_bahar")));
  });
});
