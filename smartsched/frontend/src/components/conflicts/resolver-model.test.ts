import { describe, expect, it } from "vitest";
import { ConflictPlan, AutoPlan, type Problem } from "@/lib/api/booking-conflicts";
import { applyAuto, buildItems, choosableOptions, initialState, problemsByGroup, progress, rowIssue, scopesFor, summarise } from "./resolver-model";
import { bannerText } from "./conflict-banner";
import { eventGroup } from "@/components/notifications/preferences-panel";

/** The shape of a real plan on Bahar 2026 (series A 104 Wednesdays P2 against BME 408-1, single D 106 against ING 302-1). */
const plan = ConflictPlan.parse({
  run_id: 3,
  term_id: 1,
  open: 3,
  banner: { tr: "Yayınlanan programla çakışan 3 rezervasyon (1 seri) · Çöz", en: "3 booking(s) clash with the published timetable (1 series) · Resolve" },
  groups: [
    {
      key: "series:1",
      series_id: 1,
      kind: "series",
      requested: false,
      room_id: 4,
      room: "A 104",
      default_scope: "one",
      conflicts: [
        { conflict_id: 2, booking_id: 2, status: "BOOKED", date: "2026-02-25", start_period: 2, end_period: 2, time: "09:20-10:00", held: { label: "BME 408-1" } },
        { conflict_id: 1, booking_id: 1, status: "BOOKED", date: "2026-02-18", start_period: 2, end_period: 2, time: "09:20-10:00", held: { label: "BME 408-1" } },
      ],
      options: [
        { id: "room:3", kind: "move_room", room_id: 3, room: "A 103", capacity: 47, dates: ["2026-02-18", "2026-02-25"], score: -0.07, reason: { tr: "A 103 aynı saatte boş", en: "A 103 is free at the same time" } },
        { id: "period:1-1", kind: "move_period", room_id: 4, room: "A 104", start_period: 1, end_period: 1, dates: [], score: 0.1 },
        { id: "cancel", kind: "cancel", default_reason: "Yayınlanan programla çakıştı" },
        { id: "override", kind: "override", admin_only: true },
      ],
    },
    {
      key: "booking:6",
      series_id: null,
      kind: "booking",
      room_id: 57,
      room: "D 106",
      default_scope: "one",
      conflicts: [{ conflict_id: 6, booking_id: 6, status: "BOOKED", date: "2026-02-18", start_period: 2, end_period: 2, time: "09:20-10:00" }],
      options: [
        { id: "day:2026-02-19", kind: "move_day", room_id: 57, dates: ["2026-02-19"] },
        { id: "cancel", kind: "cancel", default_reason: "Yayınlanan programla çakıştı" },
        { id: "override", kind: "override", admin_only: true },
      ],
    },
  ],
});

describe("resolver model", () => {
  it("starts with no decision and leaves undecided rows out", () => {
    const s = initialState(plan);
    expect(buildItems(plan, s)).toEqual([]);
    expect(progress(plan, s)).toEqual({ decided: 0, total: 2 });
  });

  it("a series row with scope 'one' sends one item per clashing date", () => {
    const s = initialState(plan);
    s.groups["series:1"] = { optionId: "room:3", scope: "one", reason: "" };
    expect(buildItems(plan, s)).toEqual([
      { conflict_id: 2, action: "move_room", option_id: "room:3", scope: "one", reason: null },
      { conflict_id: 1, action: "move_room", option_id: "room:3", scope: "one", reason: null },
    ]);
  });

  it("a series row with scope 'all' sends one item for its earliest conflict", () => {
    const s = initialState(plan);
    s.groups["series:1"] = { optionId: "period:1-1", scope: "all", reason: "" };
    expect(buildItems(plan, s)).toEqual([{ conflict_id: 1, action: "move_period", option_id: "period:1-1", scope: "all", reason: null }]);
  });

  it("cancel falls back to the backend's default reason; override keeps the planner's text", () => {
    const s = initialState(plan);
    s.groups["booking:6"] = { optionId: "cancel", scope: "one", reason: "  " };
    expect(buildItems(plan, s)[0]).toMatchObject({ action: "cancel", option_id: null, reason: "Yayınlanan programla çakıştı" });
    s.groups["booking:6"] = { optionId: "override", scope: "one", reason: "Senato kararı" };
    expect(buildItems(plan, s)[0]).toMatchObject({ action: "override", option_id: null, reason: "Senato kararı" });
  });

  it("override: admins only, and never without a reason", () => {
    const g = plan.groups[1]!;
    expect(choosableOptions(g, false).map((o) => o.kind)).not.toContain("override");
    expect(choosableOptions(g, true).map((o) => o.kind)).toContain("override");
    expect(rowIssue(g, { optionId: "override", scope: "one", reason: "" }, true)).toBe("reason");
    expect(rowIssue(g, { optionId: "override", scope: "one", reason: "x" }, false)).toBe("override_forbidden");
    expect(rowIssue(g, { optionId: "override", scope: "one", reason: "x" }, true)).toBeNull();
  });

  it("a single booking and a day move only have the 'one' scope", () => {
    expect(scopesFor(plan.groups[0]!, plan.groups[0]!.options[0])).toEqual(["one", "future", "all"]);
    expect(scopesFor(plan.groups[1]!, plan.groups[1]!.options[0])).toEqual(["one"]);
  });

  it("split rows send a decision per date", () => {
    const s = initialState(plan);
    s.split["series:1"] = true;
    s.perConflict[1] = { optionId: "room:3", scope: "one", reason: "" };
    s.perConflict[2] = { optionId: "cancel", scope: "one", reason: "Bayram" };
    expect(buildItems(plan, s)).toEqual([
      { conflict_id: 2, action: "cancel", option_id: null, scope: "one", reason: "Bayram" },
      { conflict_id: 1, action: "move_room", option_id: "room:3", scope: "one", reason: null },
    ]);
    expect(progress(plan, s).decided).toBe(1);
  });

  it("auto: one shared option becomes the row decision, mixed options split the row, the rest stay unresolved", () => {
    const auto = AutoPlan.parse({
      run_id: 3,
      items: [
        { conflict_id: 1, action: "move_room", option_id: "room:3", scope: "one" },
        { conflict_id: 2, action: "move_room", option_id: "room:3", scope: "one" },
      ],
      unresolved: [{ conflict_id: 6, group: "booking:6", reason: { tr: "Eşiği geçen boş seçenek kalmadı", en: "No free option above the threshold left" } }],
    });
    const { state, unresolved } = applyAuto(plan, auto, initialState(plan));
    expect(state.groups["series:1"]).toEqual({ optionId: "room:3", scope: "one", reason: "" });
    expect(state.groups["booking:6"]?.optionId).toBeNull();
    expect(unresolved.get(6)?.tr).toMatch(/Eşiği/);
    const mixed = applyAuto(plan, AutoPlan.parse({ run_id: 3, items: [{ conflict_id: 1, action: "move_room", option_id: "room:3", scope: "one" }, { conflict_id: 2, action: "move_period", option_id: "period:1-1", scope: "one" }] }), initialState(plan)).state;
    expect(mixed.split["series:1"]).toBe(true);
    expect(buildItems(plan, mixed).map((i) => i.option_id)).toEqual(["period:1-1", "room:3"]);
  });

  it("409 problems land on the row that holds the conflict", () => {
    const problems: Problem[] = [
      { conflict_id: 2, code: "slot_taken", message_tr: "A 103 25.02.2026 09:20-10:00 dolu", message_en: "taken" },
      { conflict_id: 99, code: "not_found", message_tr: "çakışma bulunamadı", message_en: "conflict not found" },
    ];
    const by = problemsByGroup(plan, problems);
    expect(by.get("series:1")?.[0]?.code).toBe("slot_taken");
    expect(by.get("_")?.[0]?.code).toBe("not_found");
  });

  it("summarises the apply answer", () => {
    expect(summarise({ run_id: 3, resolved: [1, 2], moved: [1, 2, 3], cancelled: [6], kept: [], notified: 1, unnotified: 0, already: [], dry_run: false })).toEqual({ moved: 3, cancelled: 1, kept: 0, notified: 1, unnotified: 0, already: 0 });
  });

  it("the banner text drops the backend's trailing call to action", () => {
    expect(bannerText("Yayınlanan programla çakışan 12 rezervasyon (2 seri) · Çöz")).toBe("Yayınlanan programla çakışan 12 rezervasyon (2 seri)");
    expect(bannerText("12 booking(s) clash with the published timetable (2 series)")).toBe("12 booking(s) clash with the published timetable (2 series)");
  });

  it("the owners' digest event sits under Bookings in the notification preferences", () => {
    expect(eventGroup("booking.conflict_resolved")).toBe("bookings");
  });
});

describe("T-R2-13 group heading time", () => {
  it("names the whole span of a submission and the first period of anything else", async () => {
    const { groupTime } = await import("./resolver-model");
    const c = (start: number, end: number, time: string) => ({ conflict_id: start, booking_id: start, status: "PENDING", date: "2026-10-30", start_period: start, end_period: end, time, room_id: 1, room: "C 303", user_id: 1, user: "P. T.", notes: null, headcount: null, held: null });
    expect(groupTime({ kind: "submission", conflicts: [c(6, 6, "12:40-13:20"), c(5, 5, "11:50-12:30")] } as never)).toBe("P5–P6 (11:50–13:20)");
    expect(groupTime({ kind: "booking", conflicts: [c(5, 5, "11:50-12:30")] } as never)).toBe("11:50-12:30");
    expect(groupTime({ kind: "series", conflicts: [c(5, 5, "11:50-12:30"), c(5, 5, "11:50-12:30")] } as never)).toBe("11:50-12:30");
  });
});
