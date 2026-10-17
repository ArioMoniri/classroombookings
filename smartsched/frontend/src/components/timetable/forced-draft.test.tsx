/**
 * Owner decision 2026-10-17 (R1-S-37): an administrator's forced move on the published plan goes into a new draft
 * (`bulk-move` answers `draft_run_id`). The success message says the live plan did not change and links the draft;
 * the live calendar is not patched and no undo entry is pushed (nothing changed on this run).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useCalendarActions } from "./use-calendar-actions";
import { useUndoStore } from "./model/undo-store";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const api = vi.hoisted(() => ({ bulkMove: vi.fn() }));
vi.mock("@/lib/api/calendar", async (orig) => {
  const real = await orig<typeof import("@/lib/api/calendar")>();
  return { ...real, calendarApi: { ...real.calendarApi, bulkMove: api.bulkMove } };
});

const draftAnswer = { ok: false, applied: true, dry_run: false, items: [], ok_count: 0, conflict_count: 1, assignments: [{ id: 9001 }], undo: { snapshots: [], delete_ids: [] }, draft_run_id: 42, live_run_id: 7 };

describe("forced move on the published plan (R1-S-37)", () => {
  it("says the live plan did not change and links the new draft", async () => {
    api.bulkMove.mockResolvedValue(draftAnswer);
    const qc = new QueryClient();
    qc.setQueryData(["calendar-index", 7], { assignments: [] });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">{children}</I18nProvider>
      </QueryClientProvider>
    );
    const before = useUndoStore.getState().past.length;
    const { result } = renderHook(() => useCalendarActions(7, { isAdmin: true }), { wrapper });
    const out = await result.current.move([{ aid: 11, day: 1, start_period: 1, end_period: 2, room_ids: [3], scope: "week", week: 3 }], "PSY 277", "B 201", true, "Bölüm başkanı onayladı");
    expect(out.applied).toBe(true);
    expect(out.draftRunId).toBe(42);
    expect(toast.success).toHaveBeenCalledTimes(1);
    const [msg, opts] = toast.success.mock.calls[0]!;
    expect(msg).toBe("Yayındaki plan değişmedi: taslak #42 oluşturuldu");
    render(<I18nProvider initialLocale="tr">{(opts as { description: React.ReactNode }).description}</I18nProvider>);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/runs/42");
    expect(useUndoStore.getState().past.length).toBe(before); // no undo entry for the live run
  });
});
