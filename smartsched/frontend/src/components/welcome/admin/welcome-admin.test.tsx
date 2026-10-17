/** WG-08 admin: no access for a teacher, part switches save, "Gelişmiş" holds the advanced options, texts (limits, placeholders, reset, 409 stale, show again), stats k ≥ 5. */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWelcome, resetWelcomeStore } from "../test-helpers";
import { useWelcomeStore } from "../welcome-store";
import { WelcomeAdmin } from "./welcome-admin";

const state = vi.hoisted(() => ({
  perms: ["setup.settings"] as string[],
  tab: "general",
  calls: [] as { path: string; method: string; body?: unknown }[],
  stale: false,
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams(`tab=${state.tab}`), usePathname: () => "/admin/welcome" }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: state.perms, can: (need: string | string[] | null) => real.hasPermission(state.perms, need), canAll: () => true, userId: 1, departmentId: null }) };
});
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, body: opts.body });
      const parse = (v: unknown) => (opts.schema ? opts.schema.parse(v) : v);
      if (path === "/welcome/settings") return parse(method === "PUT" ? { enabled: true, sheet: true, tour: true, checklist: true, hints: true, hints_for_all: false, ...(opts.body as object) } : { enabled: true, sheet: true, tour: true, checklist: true, hints: true, hints_for_all: false });
      if (path === "/welcome/content/academician") {
        if (method === "PUT" && state.stale) throw new real.HttpError(409, "stale", { code: "stale", updated_by: "Fatih Bey" });
        return parse({ audience: "academician", version: 3, texts: { tr: { title: "Hoş geldiniz {ad}" }, en: {} }, updated_by: "Fatih Bey", updated_at: "2026-10-17T10:00:00Z" });
      }
      if (path === "/welcome/content/academician/reshow") return { ok: true };
      if (path === "/welcome/stats") return parse({ days: 30, audiences: [{ audience: "academician", small_group: false, shown: 12, tour_completed_pct: 50, checklist_80_pct: 25, dismissed_pct: 8, median_days_to_first_booking: 2 }, { audience: "planner", small_group: true }] });
      if (path === "/welcome/events" || path === "/auth/me") return undefined;
      throw new Error(`unexpected ${path}`);
    },
  };
});

beforeEach(() => {
  resetWelcomeStore();
  state.calls = [];
  state.perms = ["setup.settings"];
  state.tab = "general";
  state.stale = false;
});

describe("WelcomeAdmin", () => {
  it("a teacher gets the no-access page", () => {
    state.perms = ["book_single.create"];
    renderWelcome(<WelcomeAdmin />);
    expect(screen.queryByTestId("welcome-admin")).toBeNull();
    expect(screen.getByText("Bu sayfaya erişiminiz yok")).toBeInTheDocument();
  });

  it("planning.admin alone may open it", () => {
    state.perms = ["planning.admin"];
    renderWelcome(<WelcomeAdmin />);
    expect(screen.getByTestId("welcome-admin")).toBeInTheDocument();
  });

  it("Genel: four switches up front, switching the sheet off saves; Gelişmiş holds 'Herkese ipucu göster' and the preview", async () => {
    renderWelcome(<WelcomeAdmin />);
    const sheet = await screen.findByTestId("welcome-switch-sheet");
    for (const p of ["tour", "checklist", "hints"]) expect(screen.getByTestId(`welcome-switch-${p}`)).toBeInTheDocument();
    expect(screen.queryByTestId("welcome-switch-hints_for_all")).toBeNull();
    fireEvent.click(sheet);
    await waitFor(() => expect(state.calls).toContainEqual({ path: "/welcome/settings", method: "PUT", body: { sheet: false } }));
    fireEvent.click(screen.getByTestId("welcome-advanced"));
    expect(screen.getByTestId("welcome-switch-hints_for_all")).not.toBeChecked();
    fireEvent.change(screen.getByTestId("welcome-preview-audience"), { target: { value: "planner" } });
    fireEvent.click(screen.getByTestId("welcome-preview-open"));
    expect(useWelcomeStore.getState().sheet).toEqual({ mode: "preview", kind: "sheet", audience: "planner" });
  });

  it("Metinler: TR and EN fields with limits, placeholder check, reset, save with 'show again'", async () => {
    state.tab = "texts";
    renderWelcome(<WelcomeAdmin />);
    const tr = await screen.findByTestId("welcome-text-academician-title-tr");
    expect(tr).toHaveValue("Hoş geldiniz {ad}");
    expect(tr).toHaveAttribute("maxLength", "80");
    expect(screen.getByTestId("welcome-text-academician-lead-en")).toHaveAttribute("maxLength", "200");
    expect(screen.getByTestId("welcome-text-academician-lead-en")).toHaveAttribute("placeholder", "See your classes, book a free room in three taps, add them to your calendar.");
    expect(screen.getByTestId("welcome-last-change")).toHaveTextContent("Son değişiklik: Fatih Bey");
    fireEvent.change(tr, { target: { value: "Merhaba {soyad}" } });
    expect(screen.getByText("Yalnızca {ad} ve {bölüm} yer tutucuları kullanılabilir.")).toBeInTheDocument();
    expect(screen.getByTestId("welcome-save")).toBeDisabled();
    fireEvent.click(screen.getByTestId("welcome-reset-academician-title-tr"));
    expect(tr).toHaveValue("");
    fireEvent.change(tr, { target: { value: "Merhaba {ad}" } });
    // card texts sit behind "Kart metinleri"
    expect(screen.queryByTestId("welcome-text-academician-cards.quick_reserve.title-tr")).toBeNull();
    fireEvent.click(screen.getByTestId("welcome-cards-toggle"));
    expect(screen.getByTestId("welcome-text-academician-cards.quick_reserve.title-tr")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("welcome-save"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Kaydedince bu kitleye rehber yeniden gösterilsin mi?");
    fireEvent.click(within(dialog).getByTestId("welcome-reshow"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/welcome/content/academician/reshow" && c.method === "POST")).toBe(true));
    const put = state.calls.find((c) => c.path === "/welcome/content/academician" && c.method === "PUT")!;
    expect(put.body).toMatchObject({ version: 3, texts: { tr: { title: "Merhaba {ad}" } } });
  });

  it("Metinler: a stale save shows who changed it", async () => {
    state.tab = "texts";
    state.stale = true;
    renderWelcome(<WelcomeAdmin />);
    fireEvent.change(await screen.findByTestId("welcome-text-academician-lead-tr"), { target: { value: "Yeni giriş" } });
    fireEvent.click(screen.getByTestId("welcome-save"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByTestId("welcome-stale")).toHaveTextContent("Bu metni siz düzenlerken Fatih Bey değiştirdi. Sayfayı yenileyip yeniden deneyin.");
  });

  it("Tamamlanma: numbers for groups of 5 or more, '5'ten az' otherwise", async () => {
    state.tab = "stats";
    renderWelcome(<WelcomeAdmin />);
    const ac = await screen.findByTestId("welcome-stats-academician");
    expect(ac).toHaveTextContent("12");
    expect(ac).toHaveTextContent("%50");
    expect(ac).toHaveTextContent("2 gün");
    const pl = screen.getByTestId("welcome-stats-planner");
    expect(pl).toHaveTextContent("5'ten az");
    expect(pl).not.toHaveTextContent("%");
    expect(state.calls).toContainEqual({ path: "/welcome/stats", method: "GET", body: undefined });
  });
});
