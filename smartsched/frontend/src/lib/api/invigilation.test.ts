/** Invigilation client helpers: poll backoff, only-changed params, re-run prefill, refusal texts. */
import { describe, expect, it } from "vitest";
import { errorProblems, errorText } from "./analytics";
import { HttpError } from "./client";
import addFx from "@/components/invigilation/__fixtures__/add-duty-final.json";
import { changedParams, dutyRefusal, instructorIdOf, paramsFrom, PLAN_DEFAULTS, pollDelay, withAddedDuty, withBrief, type AddDutyOut, type PlanBrief, type PlanDetail, type Post } from "./invigilation";

describe("invigilation client", () => {
  it("polls a running plan with a growing interval and stops once it has finished", () => {
    expect([0, 1, 2, 3, 10].map((n) => pollDelay("RUNNING", n))).toEqual([1000, 1500, 2250, 3375, 8000]);
    expect(pollDelay("QUEUED", 0)).toBe(1000);
    expect(pollDelay("FEASIBLE", 3)).toBe(false);
    expect(pollDelay("INFEASIBLE", 0)).toBe(false);
    expect(pollDelay(undefined, 0)).toBe(false);
  });

  it("sends only the parameters that differ from the defaults", () => {
    expect(changedParams(PLAN_DEFAULTS)).toEqual({});
    const v = { ...PLAN_DEFAULTS, time_limit_s: 3, own_exam: "forbid" as const, max_per_room: 2, weights: { ...PLAN_DEFAULTS.weights, own_exam: 2 } };
    expect(changedParams(v)).toEqual({ time_limit_s: 3, own_exam: "forbid", max_per_room: 2, weights: { own_exam: 2 } });
  });

  it("prefills a re-run from the stored plan params (the real Final plan's)", () => {
    const stored = { students_per_invigilator: 40, min_per_room: 1, max_per_room: null, own_exam: "prefer" as const, instructor_pool: "none" as const, max_per_day: 3, min_rest: 0, time_limit_s: 3.0, seed: 0, weights: {} };
    const p = paramsFrom(stored);
    expect(p.instructor_pool).toBe("none");
    expect(p.time_limit_s).toBe(3);
    expect(p.weights).toEqual(PLAN_DEFAULTS.weights);
    expect(changedParams(p)).toEqual({ instructor_pool: "none", time_limit_s: 3 });
  });

  it("links an instructor person key to the instructor id", () => {
    expect(instructorIdOf("INS:174")).toBe(174);
    expect(instructorIdOf("STAFF:1")).toBeNull();
  });

  it("shows a refusal in the UI language, with the reassign problems", () => {
    const body = { detail: { tr: "Bu kişi bu göreve atanamaz: bir sert kural bozulur", en: "This person cannot take the duty: a hard rule would break", problems: ["INS:5 on two duties at 2026-06-01 P1"] } };
    const e = new HttpError(409, "409 Conflict", body);
    expect(errorText(e, "tr")).toMatch(/atanamaz/);
    expect(errorText(e, "en")).toMatch(/cannot take/);
    expect(errorProblems(e)).toEqual(["INS:5 on two duties at 2026-06-01 P1"]);
    expect(errorText(new HttpError(404, "404", "plan 9 not found"), "tr")).toBe("plan 9 not found");
  });

  it("places a hand-filled duty on its post and takes the re-scored brief (real POST …/duties answer)", () => {
    const out = addFx.added as unknown as AddDutyOut;
    const before = { ...(addFx.brief_before as unknown as PlanBrief), posts: [addFx.post as unknown as Post], people: [], diagnosis: [], objective_breakdown: {}, stats: {} } as PlanDetail;
    const after = withAddedDuty(before, out);
    expect(after.counts.filled).toBe(37);
    expect(after.counts.missing).toBe(1054);
    expect(after.headline?.tr).toMatch(/^37\/1091 görev atandı/);
    const p = after.posts[0]!;
    expect(p.missing).toBe(1);
    expect(p.assigned.map((d) => d.person_key)).toEqual(["STAFF:1", "STAFF:2"]);
    expect(p.assigned[1]).toMatchObject({ id: 1128, origin: "MANUAL", is_locked: true, person_name: "Arş. Gör. Fixture İki" });
    expect(p.assigned.at(-1)).not.toHaveProperty("plan");
    // applying the same answer twice (cache + refetch race) keeps one duty
    expect(withAddedDuty(after, out).posts[0]!.assigned).toHaveLength(2);
    // another plan's detail is left alone
    expect(withAddedDuty({ ...before, id: 99 }, out)).toEqual({ ...before, id: 99 });
    expect(withBrief([before, { ...before, id: 1 }], out.plan).map((x) => x.counts.filled)).toEqual([37, 36]);
  });

  it("reads a duty refusal: the sentence, the reason code, the server's reason text and the problems", () => {
    const e = new HttpError(409, "409 Conflict", addFx.refused_on_post);
    expect(dutyRefusal(e, "tr")).toEqual({ text: "Bu kişi bu göreve atanamaz: bir sert kural bozulur", reason: "on_post", reasonText: "bu görevde zaten var", problems: ["post 2026-05-13|30|6-8: a person listed twice"] });
    expect(dutyRefusal(new HttpError(409, "409", addFx.refused_post_full), "en")).toMatchObject({ reason: "post_full", reasonText: "fully staffed" });
    expect(dutyRefusal(new Error("offline"), "tr")).toEqual({ text: "offline", reason: null, reasonText: null, problems: [] });
  });
});
