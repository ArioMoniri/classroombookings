import { describe, expect, it } from "vitest";
import { addDays, currentItem, nextItem, PublicBuildingDay, publicWindow } from "@/lib/api/public-schedule";

const items = PublicBuildingDay.parse({
  date: "2026-02-18",
  building: { code: "A", name: "A Blok" },
  rooms: [
    {
      code: "A104",
      name: "A 104",
      building: "A",
      capacity: 41,
      items: [
        { kind: "class", start_period: 2, end_period: 5, start: "09:20", end: "12:30", label: { tr: "BME 408", en: "BME 408" } },
        { kind: "booked", start_period: 6, end_period: 6, start: "12:40", end: "13:20", label: { tr: "Rezerve", en: "Booked" } },
      ],
    },
  ],
}).rooms[0]!.items;

describe("public day view helpers", () => {
  it("the window is a week back to 120 days ahead of the backend's today", () => {
    expect(publicWindow("2026-02-16")).toEqual({ min: "2026-02-09", max: "2026-06-16" });
    expect(addDays("2026-03-28", 2)).toBe("2026-03-30"); // over the DST change
  });

  it("finds the running and the next item", () => {
    expect(currentItem(items, "10:00")?.label.tr).toBe("BME 408");
    expect(currentItem(items, "12:35")).toBeNull();
    expect(nextItem(items, "12:35")?.label.en).toBe("Booked");
    expect(nextItem(items, "14:00")).toBeNull();
  });

  it("an unknown kind falls back to a neutral 'reserved' (never a name)", () => {
    const parsed = PublicBuildingDay.parse({ date: "2026-02-18", building: { code: "A", name: "A" }, rooms: [{ code: "A1", name: "A 1", items: [{ kind: "person", start_period: 1, end_period: 1, start: "08:30", end: "09:10", label: { tr: "Ayrılmış", en: "Reserved" } }] }] });
    expect(parsed.rooms[0]!.items[0]!.kind).toBe("reserved");
  });
});
