import { describe, expect, it } from "vitest";
import type { Draft, Precheck, StudioRule, StudioSummary } from "@/lib/api/studio-schemas";
import type { Week } from "@/lib/api/schemas";
import { deriveSummary, estimateWords, initialStudioState, patchFor, resolveWeeks, studioReducer, type StudioState } from "./studio-reducer";

const draft = (over: Partial<Draft> = {}): Draft => ({
  draft_id: 9,
  term_id: 1,
  kind: "COURSE",
  version: 3,
  scope: { horizon: "TERM", horizon_params: {}, weeks: [1, 2, 3], holiday_weeks: [] },
  excluded_event_ids: [],
  pins: [],
  disabled_builtin_kinds: [],
  disabled_rule_ids: [],
  rule_overrides: {},
  rule_ids: [],
  params: {},
  ...over,
});

const weeks: Week[] = Array.from({ length: 16 }, (_, i) => ({ id: i + 1, term_id: 1, index: i + 1, start_date: "2026-02-02", kind: i + 1 === 9 ? "HOLIDAY" : i + 1 >= 15 ? "EXAM" : "LECTURE", label: "" }));

const rule = (id: number, hardness: "hard" | "soft", over: Partial<StudioRule> = {}): StudioRule => ({ id, kind: "room_pin", params: {}, hardness, weight: 5, source: "ADMIN", nl_text: null, enabled: true, in_play: true, title: { tr: "", en: "" }, affected_count: 3, ...over });

const hydrated = (d = draft()): StudioState => studioReducer(initialStudioState, { type: "hydrate", draft: d });

describe("studioReducer", () => {
  it("hydrates from the server draft with nothing dirty", () => {
    const s = hydrated(draft({ excluded_event_ids: [4], scope: { horizon: "WEEK", horizon_params: { weeks: [7] }, weeks: [7], holiday_weeks: [] } }));
    expect(s.local.excluded).toEqual([4]);
    expect(s.local.horizon).toBe("WEEK");
    expect(s.dirty).toEqual([]);
  });

  it("marks exclusions dirty, de-duplicates and puts classes back", () => {
    let s = hydrated();
    s = studioReducer(s, { type: "exclude", ids: [1, 2, 2] });
    expect(s.local.excluded).toEqual([1, 2]);
    expect(s.dirty).toEqual(["excluded_event_ids"]);
    s = studioReducer(s, { type: "include", ids: [1] });
    expect(s.local.excluded).toEqual([2]);
    expect(patchFor(s.local, s.dirty)).toEqual({ excluded_event_ids: [2] });
  });

  it("keeps edits made while a save was in flight", () => {
    let s = hydrated();
    s = studioReducer(s, { type: "exclude", ids: [1] });
    s = studioReducer(s, { type: "saving" });
    // user changes the scope while PUT {excluded_event_ids} is in flight
    s = studioReducer(s, { type: "setScope", horizon: "WEEK", horizon_params: { weeks: [3] } });
    s = studioReducer(s, { type: "saved", draft: draft({ version: 4, excluded_event_ids: [1] }), sent: ["excluded_event_ids"] });
    expect(s.server?.version).toBe(4);
    expect(s.local.excluded).toEqual([1]);
    expect(s.local.horizon).toBe("WEEK");
    expect(s.dirty).toEqual(["horizon", "horizon_params"]);
    expect(s.status).toBe("idle");
  });

  it("drops an empty override and toggles rules / built-ins per draft", () => {
    let s = hydrated();
    s = studioReducer(s, { type: "setOverride", ruleId: 5, override: { hardness: "soft" } });
    expect(s.local.rule_overrides).toEqual({ "5": { hardness: "soft" } });
    s = studioReducer(s, { type: "setOverride", ruleId: 5, override: { hardness: null, weight: null } });
    expect(s.local.rule_overrides).toEqual({});
    s = studioReducer(s, { type: "setRuleInPlay", ruleId: 7, inPlay: false });
    s = studioReducer(s, { type: "setBuiltin", kind: "capacity", enabled: false });
    expect(s.local.disabled_rule_ids).toEqual([7]);
    expect(s.local.disabled_builtin_kinds).toEqual(["capacity"]);
  });

  it("conflict → keep mine resends every field on top of the server version", () => {
    let s = hydrated();
    s = studioReducer(s, { type: "exclude", ids: [1] });
    s = studioReducer(s, { type: "conflict", current: draft({ version: 8 }) });
    expect(s.status).toBe("conflict");
    s = studioReducer(s, { type: "keepMine", current: draft({ version: 8 }) });
    expect(s.server?.version).toBe(8);
    expect(s.local.excluded).toEqual([1]);
    expect(s.dirty).toContain("excluded_event_ids");
    expect(s.dirty).toContain("pins");
  });

  it("setStep does not create a change when the step is unchanged", () => {
    const s = studioReducer(hydrated(draft({ last_step: "rules" })), { type: "setStep", step: "rules" });
    expect(s.dirty).toEqual([]);
  });
});

describe("resolveWeeks", () => {
  it("mirrors the backend horizons", () => {
    expect(resolveWeeks("TERM", {}, weeks)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14]);
    expect(resolveWeeks("WEEK", { weeks: [7, 3] }, weeks)).toEqual([3, 7]);
    expect(resolveWeeks("MONTH", { start_week: 7 }, weeks)).toEqual([7, 8, 9, 10]);
  });
});

describe("deriveSummary (the 'What will happen' reducer)", () => {
  const summary: StudioSummary = {
    draft_id: 9,
    version: 3,
    counts: { classes_total: 5, classes_need_room: 4, classes_in: 4, classes_out: 0, classes_without_time: 1, events: 4, rooms: 61, weeks: 13, pinned: 0, rules_must: 9, rules_try: 9, builtins_off: 0 },
    weeks: [],
    holiday_weeks: [],
    readiness: "unknown",
    estimate_s: { low: 20, high: 70 },
    sentence: { tr: "", en: "" },
    human_summary: { tr: "", en: "" },
    warnings: [],
    last_good_run: { id: 41, status: "FEASIBLE" },
    disabled_builtin_kinds: [],
  };
  const classes = [
    { id: 1, schedulable: true },
    { id: 2, schedulable: true },
    { id: 3, schedulable: true },
    { id: 4, schedulable: false },
  ];
  const precheck = (version: number, readiness: Precheck["readiness"]): Precheck => ({
    draft_id: 9,
    version,
    readiness,
    counts: {},
    groups: [],
    items: [
      { id: "a", category: "info", severity: "info", group: "x", title: { tr: "", en: "info" }, message: { tr: "", en: "" }, detail: "", event_ids: [], classes: [], constraint_kinds: [], constraint_ids: [], fixes: [] },
      { id: "b", category: "impossible", severity: "error", group: "capacity", title: { tr: "", en: "BME" }, message: { tr: "", en: "" }, detail: "", event_ids: [1], classes: [], constraint_kinds: [], constraint_ids: [], fixes: [] },
    ],
    estimate_s: { low: 90, high: 300 },
    summary: { tr: "", en: "" },
    duration_s: 0,
  });

  it("counts live from the local draft: left-out, pins, overrides and per-draft offs", () => {
    let s = hydrated();
    s = studioReducer(s, { type: "exclude", ids: [2] });
    s = studioReducer(s, { type: "setPin", pin: { event_id: 1, room_ids: [3] } });
    s = studioReducer(s, { type: "setOverride", ruleId: 11, override: { hardness: "soft" } });
    s = studioReducer(s, { type: "setRuleInPlay", ruleId: 12, inPlay: false });
    const v = deriveSummary({ local: s.local, dirty: true, server: s.server, summary, classes, rules: [rule(10, "hard"), rule(11, "hard"), rule(12, "soft"), rule(13, "soft", { enabled: false })], termWeeks: weeks, precheck: null, checking: false });
    expect(v.classesIn).toBe(2);
    expect(v.classesOut).toBe(1);
    expect(v.pinned).toBe(1);
    expect(v.must).toBe(1);
    expect(v.tryTo).toBe(1);
    expect(v.rooms).toBe(61);
    expect(v.weeks).toHaveLength(13);
    expect(v.lastGoodRunId).toBe(41);
    expect(v.stability).toBe(true);
  });

  it("only trusts a pre-check for the saved draft version; shows the worst issues first", () => {
    const s = hydrated();
    const fresh = deriveSummary({ local: s.local, dirty: false, server: s.server, summary, classes, rules: [], termWeeks: weeks, precheck: precheck(3, "blocked"), checking: false });
    expect(fresh.readiness).toBe("blocked");
    expect(fresh.topIssues[0].id).toBe("b");
    expect(fresh.problems).toBe(1);
    expect(fresh.estimate).toEqual({ low: 90, high: 300 });
    const stale = deriveSummary({ local: s.local, dirty: false, server: s.server, summary, classes, rules: [], termWeeks: weeks, precheck: precheck(2, "ready"), checking: false });
    expect(stale.readiness).toBe("unknown");
    const checking = deriveSummary({ local: s.local, dirty: false, server: s.server, summary, classes, rules: [], termWeeks: weeks, precheck: precheck(3, "ready"), checking: true });
    expect(checking.readiness).toBe("checking");
  });

  it("falls back to the server summary before the class list and rules load", () => {
    const s = hydrated();
    const v = deriveSummary({ local: s.local, dirty: false, server: s.server, summary, classes: null, rules: null, termWeeks: [], precheck: null, checking: false });
    expect(v.classesIn).toBe(4);
    expect(v.must).toBe(9);
    expect(v.estimate).toEqual({ low: 20, high: 70 });
  });

  it("stability is off without a good previous run or when switched off", () => {
    const s = studioReducer(hydrated(), { type: "setParams", params: { stability: false } });
    expect(deriveSummary({ local: s.local, dirty: true, server: s.server, summary, classes, rules: [], termWeeks: weeks, precheck: null, checking: false }).stability).toBe(false);
  });
});

describe("estimateWords", () => {
  const t = (k: string, v?: Record<string, number>) => (k === "under" ? "under a minute" : k === "aboutOne" ? "about a minute" : k === "about" ? `about ${v?.n} minutes` : `(at most ${v?.n})`);
  it("rounds to plain words", () => {
    expect(estimateWords({ low: 10, high: 40 }, t)).toBe("under a minute");
    expect(estimateWords({ low: 60, high: 200 }, t)).toBe("about 2 minutes (at most 3)");
    expect(estimateWords({ low: 50, high: 70 }, t)).toBe("about a minute");
  });
});
