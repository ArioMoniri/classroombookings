import { act, fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChartApi } from "@/components/charts/chart-form-types";
import { HttpError } from "@/lib/api/client";

vi.mock("@/components/charts/chart-lazy", () => ({
  LazyBarChart: (p: { data: unknown[]; partialLast: boolean; onReady: (a: ChartApi) => void }) => {
    useEffect(() => p.onReady({ getDataURL: () => null, dispatchAction: () => undefined, showTip: () => undefined, hideTip: () => undefined, indexAt: () => 1 }), [p]);
    return <div data-testid="bar" data-points={p.data.length} data-partial={String(p.partialLast)} />;
  },
}));
const state = vi.hoisted(() => ({ data: undefined as unknown, error: null as unknown }));
vi.mock("@/lib/api/stats", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/stats")>()),
  useDailyAuditStats: () => ({ data: state.data, error: state.error, isError: !!state.error, isLoading: false, refetch: vi.fn() }),
}));

import { AuditDaily } from "./audit-daily";

beforeEach(() => {
  state.error = null;
  state.data = { from: "2026-10-12", to: "2026-10-14", days: [{ day: "2026-10-12", events: 5 }, { day: "2026-10-13", events: 40 }, { day: "2026-10-14", events: 2 }] };
});

describe("CH-10 audit events per day", { timeout: 20_000 }, () => {
  it("columns per day, today hatched, a plain summary", () => {
    render(<AuditDaily onDay={vi.fn()} />);
    const fig = screen.getByRole("figure", { name: "Günlük olaylar" });
    expect(fig).toHaveAccessibleDescription(/Son 30 günde 47 olay; en yoğun gün 13 Eki \(40\)\./);
    expect(screen.getByTestId("bar")).toHaveAttribute("data-points", "3");
    expect(screen.getByTestId("bar")).toHaveAttribute("data-partial", "true");
  });

  it("a click on a column, or → → Enter, filters the list to that day and announces it", () => {
    vi.useFakeTimers();
    const onDay = vi.fn();
    render(<AuditDaily onDay={onDay} />);
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    fireEvent.click(group, { clientX: 5, clientY: 5 });
    expect(onDay).toHaveBeenLastCalledWith("2026-10-13");
    expect(screen.getByTestId("audit-daily-live")).toHaveTextContent("Liste 13 Ekim Salı gününe süzüldü.");
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "Enter" });
    expect(onDay).toHaveBeenLastCalledWith("2026-10-12");
    act(() => {
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it("phones: one 44 px toggle; the card is hidden below sm until it is opened", () => {
    render(<AuditDaily onDay={vi.fn()} />);
    const toggle = screen.getByTestId("audit-daily-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.className).toMatch(/pointer-coarse:h-11/);
    expect(document.getElementById("audit-daily-card")!.className).toMatch(/max-sm:hidden/);
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveTextContent("Günlük olayları gizle");
    expect(document.getElementById("audit-daily-card")!.className).not.toMatch(/max-sm:hidden/);
  });

  it("route missing: honest empty state, no plot", () => {
    state.data = undefined;
    state.error = new HttpError(404, "Not Found", "Not Found");
    render(<AuditDaily onDay={vi.fn()} />);
    expect(screen.getByText(/Günlük sayımlar sunucuda henüz hazır değil/)).toBeInTheDocument();
    expect(screen.queryByTestId("bar")).toBeNull();
  });
});
