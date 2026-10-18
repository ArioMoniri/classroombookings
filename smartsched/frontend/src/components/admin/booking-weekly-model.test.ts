import { describe, expect, it } from "vitest";
import { makeChartFormat } from "@/components/charts/chart-format";
import { translate, type MessageKey, type Vars } from "@/lib/i18n";
import type { WeeklyBookingStats } from "@/lib/api/stats";
import { bookingsSummary, requestsSummary, weeklyRows } from "./booking-weekly-model";

const t = (k: MessageKey, v?: Vars) => translate("tr", k, v);
const f = makeChartFormat("tr");
const week = (n: number, bookings: number, over: Partial<WeeklyBookingStats["weeks"][number]> = {}): WeeklyBookingStats["weeks"][number] => ({
  week: n,
  start: `2026-02-${String(n * 7 - 6).padStart(2, "0")}`,
  end: `2026-02-${String(n * 7 - 2).padStart(2, "0")}`,
  exam: false,
  partial: false,
  bookings,
  requests: { approved: 0, rejected: 0, pending: 0 },
  ...over,
});
const stats = (weeks: WeeklyBookingStats["weeks"]): WeeklyBookingStats => ({ term_id: 3, from: "2026-02-01", to: "2026-06-01", today: "2026-02-20", weeks });

describe("CH-07 weekly booking model", () => {
  it("keeps the server's weeks in week order, labels them and flags exam weeks in a text column", () => {
    const rows = weeklyRows(stats([week(2, 5), week(1, 3, { exam: true }), week(3, 9, { partial: true })]), t);
    expect(rows.map((r) => r.week)).toEqual(["1. hf", "2. hf", "3. hf"]);
    expect(rows[0]!.examText).toBe("Sınav haftası");
    expect(rows[1]!.examText).toBe("");
    expect(rows.map((r) => r.bookings)).toEqual([3, 5, 9]);
  });

  it("partial is true only when the last week is the unfinished one", () => {
    expect(weeklyRows(stats([week(1, 1), week(2, 2, { partial: true })]), t).at(-1)!.partial).toBe(true);
  });

  it("bookings summary: the total and the busiest week, plus the unfinished-week sentence", () => {
    const rows = weeklyRows(stats([week(1, 120), week(2, 210), week(3, 40, { partial: true })]), t);
    expect(bookingsSummary(rows, t, f)).toBe("Bu dönem 370 rezervasyon; en yoğun hafta 2. hafta (210). Bu hafta henüz bitmedi.");
  });

  it("bookings summary is empty when there is nothing to count (the card shows its empty state)", () => {
    expect(bookingsSummary(weeklyRows(stats([week(1, 0), week(2, 0)]), t), t, f)).toBe("");
  });

  it("request outcomes: approved / rejected / pending sums", () => {
    const rows = weeklyRows(
      stats([
        week(1, 0, { requests: { approved: 4, rejected: 1, pending: 0 } }),
        week(2, 0, { requests: { approved: 6, rejected: 2, pending: 3 } }),
      ]),
      t,
    );
    expect(requestsSummary(rows, t, f)).toBe("Bu dönem 16 talep: 10 onaylandı, 3 reddedildi, 3 bekliyor.");
    expect(requestsSummary(weeklyRows(stats([week(1, 3)]), t), t, f)).toBe("");
  });
});
