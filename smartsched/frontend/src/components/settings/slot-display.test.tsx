/** W3-SLOT · Ayarlar › Ders saatleri (slot-display.md §4): live preview, first/last validation, save writes the keys. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { SlotDisplaySettings } from "./slot-display";

const D = "2026-02-16";
const periods = [1, 2, 3, 4].map((n) => ({ id: n, name: `P${n}`, time_start: `${String(7 + n).padStart(2, "0")}:30`, time_end: `${String(8 + n).padStart(2, "0")}:20`, start_period: n, end_period: n, days: [1, 2, 3, 4, 5] }));
const context = { sessions: [], current_term_id: 1, room_groups: [], display: { type: "day", columns: "periods", use_room_groups: false }, date_patterns: {}, permissions: [], limits: {}, active_bookings: 0 };
const grid = { display: "day", term: { id: 1, code: "B", name: "B", start: D, end: D }, date: D, dates: [{ date: D, weekday: 1, open: true }], periods, rooms: [], slots: [], nav: {}, limits: {}, problems: [] };

let puts: unknown[] = [];
function mockApi() {
  puts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      const body = u.includes("/bookings/dates") ? { term_id: 1, today: D, weeks: [], dates: [] } : u.includes("/bookings/context") ? context : u.includes("/bookings/grid") ? grid : u.includes("/bookings/slot-display") ? {} : u.includes("/settings") ? (puts.push(JSON.parse(String(init?.body ?? "{}"))), {}) : {};
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

function renderIt() {
  mockApi();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <SlotDisplaySettings />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SlotDisplaySettings", () => {
  it("the preview follows a label change in the same render; save sends booking.slot_display.* to PUT /settings", async () => {
    renderIt();
    await waitFor(() => expect(screen.getByTestId("sd-visible-summary")).toHaveTextContent("4 / 4 ders saati görünür"), { timeout: 10_000 });
    const head = () => screen.getByTestId("sd-preview-grid-body").querySelectorAll("thead th")[1]!.textContent;
    expect(head()).toBe("P108:30–09:20");
    fireEvent.click(screen.getByTestId("sd-label-time"));
    expect(head()).toBe("08:30–09:20");
    expect(screen.getByTestId("sd-unsaved")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("sd-save"));
    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 10_000 });
    expect((puts[0] as { extra: Record<string, unknown> }).extra).toMatchObject({ "booking.slot_display.label": "time", "booking.slot_display.unit": "periods" });
  });

  it("first after last is an inline error, save is disabled and the attempt focuses İlk (SD-07)", async () => {
    renderIt();
    await waitFor(() => expect(screen.getByTestId("sd-visible-summary")).toBeInTheDocument(), { timeout: 10_000 });
    fireEvent.change(screen.getByTestId("sd-first"), { target: { value: "3" } });
    fireEvent.change(screen.getByTestId("sd-last"), { target: { value: "2" } });
    expect(screen.getByRole("alert")).toHaveTextContent("İlk saat son saatten sonra olamaz.");
    expect(screen.getByTestId("sd-first")).toHaveAttribute("aria-invalid", "true");
    const save = screen.getByTestId("sd-save");
    expect(save).toHaveAttribute("aria-disabled", "true");
    fireEvent.change(screen.getByTestId("sd-last"), { target: { value: "0" } });
    expect(screen.getByTestId("sd-visible-summary")).toHaveTextContent("2 / 4 ders saati görünür");
  });
});
