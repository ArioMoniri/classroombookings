/** FIX-E (round 4, 2026-10-18): the majors of HX-12b, personas, AUX-12, CAL-10 and WG-10 that unit tests can hold. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { ClosedDayNotice, isClosedDay } from "./bookings/closed-day";
import type { Grid } from "@/lib/api/crbs";

const tr = (ui: React.ReactNode) => render(<I18nProvider initialLocale="tr">{ui}</I18nProvider>);

describe("HX12B-F01 / PER-F11: a day without periods is never a blank grid", () => {
  it("says the day is closed and offers the next open day", async () => {
    const onGo = vi.fn();
    tr(<ClosedDayNotice next="2026-10-19" long={() => "Pazartesi 19 Ekim"} onGo={onGo} />);
    expect(screen.getByText("Bu gün rezervasyona kapalı.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Pazartesi 19 Ekim gününe git" }));
    expect(onGo).toHaveBeenCalledWith("2026-10-19");
  });
  it("only a one-day grid with no periods counts as closed", () => {
    expect(isClosedDay({ display: "day", periods: [] } as unknown as Grid)).toBe(true);
    expect(isClosedDay({ display: "room", periods: [] } as unknown as Grid)).toBe(false);
    expect(isClosedDay({ display: "day", periods: [{ id: 1 }] } as unknown as Grid)).toBe(false);
  });
});

describe("HX12B-F06: a planner's run page never reads the admin-only settings", () => {
  it("useSettings({peek, enabled:false}) sends nothing; peek is silent", async () => {
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { renderHook, waitFor } = await import("@testing-library/react");
    const client = await import("@/lib/api/client");
    const spy = vi.spyOn(client, "request").mockResolvedValue({} as never);
    const { useSettings } = await import("@/lib/api/hooks");
    const wrap = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
    renderHook(() => useSettings({ peek: true, enabled: false }), { wrapper: wrap });
    await new Promise((r) => setTimeout(r, 20));
    expect(spy).not.toHaveBeenCalled();
    renderHook(() => useSettings({ peek: true, enabled: true }), { wrapper: wrap });
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0]![1]).toMatchObject({ silent: true });
    spy.mockRestore();
  });
  it("the chat panel asks only with planning.admin", async () => {
    const { readFileSync } = await import("node:fs");
    const path = await import("node:path");
    const src = readFileSync(path.resolve(import.meta.dirname, "chat/chat-panel.tsx"), "utf8");
    expect(src).toMatch(/useSettings\(\{ peek: true, enabled: can\("planning\.admin"\) \}\)/);
  });
});
