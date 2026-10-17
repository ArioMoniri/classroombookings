/** The run form's checks (the backend PlanParams bounds) and the defaults it shows. */
import { describe, expect, it } from "vitest";
import { PLAN_DEFAULTS } from "@/lib/api/invigilation";
import { validateParams } from "./plan-form";

describe("plan form", () => {
  it("accepts the defaults", () => {
    expect(validateParams(PLAN_DEFAULTS)).toEqual({});
  });
  it("flags values outside the backend bounds", () => {
    const bad = validateParams({ ...PLAN_DEFAULTS, students_per_invigilator: 0, max_per_day: 13, max_per_room: 0, time_limit_s: 601, weights: { ...PLAN_DEFAULTS.weights, spread: -1 } });
    expect(Object.keys(bad).sort()).toEqual(["max_per_day", "max_per_room", "spread", "students_per_invigilator", "time_limit_s"]);
  });
  it("needs at most per room ≥ at least per room", () => {
    expect(validateParams({ ...PLAN_DEFAULTS, min_per_room: 3, max_per_room: 2 })).toEqual({ max_per_room: true });
  });
});
