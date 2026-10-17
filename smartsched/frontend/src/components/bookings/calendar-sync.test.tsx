/** T-R2-15 (R2-S-11, R2-M-10, R2-A-12, R2-S-21): the calendar-sync card's disabled state is quiet text (no live
 * region the toast probes count), the copy buttons carry a word and tell a refused clipboard, the link wraps. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/my-bookings",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const api = vi.hoisted(() => ({ sync: null as unknown }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string) => {
      if (path === "/auth/me") return { id: 5, username: "ayse", email: "ayse@uni.edu.tr", department_id: null };
      if (path === "/calendar/sync") return api.sync;
      if (path === "/calendar/feeds/options") return { rooms: [], room_groups: [], departments: [] };
      if (path === "/calendar/feeds/tokens") return { id: 7, label: "SmartSched", token: "sst_x", hint: "abcd", urls: { mine: "/api/v1/calendar/feeds/sst_x/mine.ics", room: "/api/v1/calendar/feeds/sst_x/room/{id}.ics", department: "/api/v1/calendar/feeds/sst_x/department/{id}.ics" } };
      throw new Error(`unexpected ${path}`);
    },
  };
});

import { CalendarSyncPanel } from "./calendar-sync";

const sync = (enabled: boolean) => ({ enabled, feeds: { tokens: [], url_templates: { mine: "/m", room: "/r/{id}", department: "/d/{id}" } }, connectors: [], consent: { purpose: "calendar_sync", required: true, granted: true } });
function renderIt(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("T-R2-15 calendar-sync card", () => {
  beforeEach(() => {
    toast.success.mockReset();
    toast.error.mockReset();
    window.sessionStorage.clear();
    Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, origin: "https://rez.uni.edu.tr", assign: vi.fn() } });
  });
  it("says sync is off as quiet text: no role=status / alert the toast probes would count", async () => {
    api.sync = sync(false);
    renderIt(<CalendarSyncPanel />);
    const off = await screen.findByTestId("sync-off");
    expect(off).toHaveTextContent("Takvim eşitleme yönetici tarafından kapatıldı.");
    expect(off).not.toHaveAttribute("role");
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("copy buttons carry a word; a refused clipboard toasts and selects the link field", async () => {
    const user = userEvent.setup();
    api.sync = sync(true);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new DOMException("Write permission denied", "NotAllowedError")) }, configurable: true });
    renderIt(<CalendarSyncPanel />);
    await user.click(await screen.findByTestId("sync-create"));
    const field = await screen.findByTestId("sync-url-mine");
    expect(field.tagName).toBe("TEXTAREA");
    expect(field).toHaveValue("https://rez.uni.edu.tr/api/v1/calendar/feeds/sst_x/mine.ics");
    const copy = screen.getByTestId("sync-copy-mine");
    expect(copy).toHaveTextContent("Kopyala");
    expect(screen.getByTestId("sync-copy-webcal-mine")).toHaveTextContent("webcal kopyala");
    await user.click(copy);
    expect(toast.error).toHaveBeenCalledWith("Kopyalanamadı: bağlantıyı alandan seçin");
    expect(toast.success).not.toHaveBeenCalled();
    expect(field).toHaveFocus();
    // with a working clipboard the old toast stays
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
    await user.click(copy);
    expect(toast.success).toHaveBeenCalledWith("Bağlantı kopyalandı");
  });
});
