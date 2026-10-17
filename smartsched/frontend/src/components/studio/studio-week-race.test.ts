/**
 * Round-1 R1-M-12: the Studio overwrote the chosen week 3 with week 6 and the run was generated for week 6.
 * Repro: the restored draft is "week 6"; "Bir hafta" saves `horizon_params {weeks: [6]}`; the planner clicks H3 while
 * that request is in flight; the answer (weeks [6]) replaced the newer local H3 because the field was in the sent
 * set. A field edited again after its request left must stay dirty and keep the planner's value.
 */
import { describe, expect, it } from "vitest";
import type { Draft } from "@/lib/api/studio-schemas";
import { initialStudioState, patchFor, studioReducer, type StudioState } from "./studio-reducer";

const draft = (weeks: number[], version: number, horizon: "WEEK" | "TERM" = "WEEK"): Draft => ({
  draft_id: 9,
  term_id: 1,
  kind: "COURSE",
  version,
  scope: { horizon, horizon_params: horizon === "WEEK" ? { weeks } : {}, weeks, holiday_weeks: [] },
  excluded_event_ids: [],
  pins: [],
  disabled_builtin_kinds: [],
  disabled_rule_ids: [],
  rule_overrides: {},
  rule_ids: [],
  params: {},
});

describe("studio draft save race (R1-M-12)", () => {
  it("keeps a week chosen while the previous save was in flight", () => {
    let s: StudioState = studioReducer(initialStudioState, { type: "hydrate", draft: draft([6], 3, "TERM") });
    // "Bir hafta": the scope step proposes the draft's own weeks (6)
    s = studioReducer(s, { type: "setScope", horizon: "WEEK", horizon_params: { weeks: [6] } });
    const sent = [...s.dirty];
    const sentEdits = { ...s.edits };
    const body = patchFor(s.local, sent);
    expect(body.horizon_params).toEqual({ weeks: [6] });
    s = studioReducer(s, { type: "saving" });
    // the planner clicks H3 before the answer arrives
    s = studioReducer(s, { type: "setScope", horizon: "WEEK", horizon_params: { weeks: [3] } });
    // the answer for the first request (weeks [6])
    s = studioReducer(s, { type: "saved", draft: draft([6], 4), sent, sentEdits });
    expect(s.local.horizon_params).toEqual({ weeks: [3] });
    expect(s.dirty).toContain("horizon_params");
    expect(s.status).toBe("idle"); // the saver sends H3 next
    // ... and once H3 is saved nothing is dirty and the server copy says week 3
    const sent2 = [...s.dirty];
    const edits2 = { ...s.edits };
    expect(patchFor(s.local, sent2).horizon_params).toEqual({ weeks: [3] });
    s = studioReducer(s, { type: "saved", draft: draft([3], 5), sent: sent2, sentEdits: edits2 });
    expect(s.dirty).toEqual([]);
    expect(s.local.horizon_params).toEqual({ weeks: [3] });
    expect(s.server?.scope.horizon_params).toEqual({ weeks: [3] });
  });

  it("a field not edited again adopts the server copy as before", () => {
    let s: StudioState = studioReducer(initialStudioState, { type: "hydrate", draft: draft([6], 3) });
    s = studioReducer(s, { type: "setScope", horizon: "WEEK", horizon_params: { weeks: [3] } });
    const sent = [...s.dirty];
    const sentEdits = { ...s.edits };
    s = studioReducer(s, { type: "saved", draft: draft([3], 4), sent, sentEdits });
    expect(s.dirty).toEqual([]);
    expect(s.status).toBe("saved");
  });
});
