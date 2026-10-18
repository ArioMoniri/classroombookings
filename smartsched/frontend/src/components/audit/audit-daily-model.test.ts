import { describe, expect, it } from "vitest";
import { makeChartFormat } from "@/components/charts/chart-format";
import { translate, type MessageKey, type Vars } from "@/lib/i18n";
import { emptyAuditFilters } from "./audit-model";
import { auditDailySummary, dailyRows, filterToDay } from "./audit-daily-model";

const t = (k: MessageKey, v?: Vars) => translate("tr", k, v);
const f = makeChartFormat("tr");

describe("CH-10 audit events per day model", () => {
  it("fills every day of the range with 0 and keeps the server's counts (no invented days outside the range)", () => {
    const rows = dailyRows({ from: "2026-10-01", to: "2026-10-05", days: [{ day: "2026-10-02", events: 7 }, { day: "2026-10-05", events: 3 }, { day: "2026-09-01", events: 99 }] });
    expect(rows.map((r) => [r.day, r.events])).toEqual([
      ["2026-10-01", 0],
      ["2026-10-02", 7],
      ["2026-10-03", 0],
      ["2026-10-04", 0],
      ["2026-10-05", 3],
    ]);
  });

  it("summary: total and the busiest day; empty when nothing happened", () => {
    const rows = dailyRows({ from: "2026-10-12", to: "2026-10-14", days: [{ day: "2026-10-12", events: 4 }, { day: "2026-10-13", events: 40 }] });
    expect(auditDailySummary(rows, t, f)).toBe("Son 30 günde 44 olay; en yoğun gün 13 Eki (40).");
    expect(auditDailySummary(dailyRows({ from: "2026-10-12", to: "2026-10-13", days: [] }), t, f)).toBe("");
  });

  it("a column click filters the list to that one day and keeps the other filters", () => {
    const next = filterToDay({ ...emptyAuditFilters, entityType: "booking", from: "2026-09-01" }, "2026-10-13");
    expect(next).toEqual({ ...emptyAuditFilters, entityType: "booking", from: "2026-10-13", to: "2026-10-13" });
  });
});
