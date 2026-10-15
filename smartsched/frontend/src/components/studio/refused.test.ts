import { describe, expect, it } from "vitest";
import { ProposedConstraint } from "@/lib/api/schemas";
import { refusedAsDecisions, splitRefused } from "./refused";

const ok = ProposedConstraint.parse({ kind: "room_preference", params: {}, hardness: "soft", weight: 5, nl_text: "A 204 olsun", confidence: 0.9, status: "ok" });
const refused = ProposedConstraint.parse({ kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5, nl_text: "Hep aynı derslik", confidence: 0.9, status: "rejected", issues: ["untargeted: say which classes", "soft structural rule"] });

describe("AI proposals refused by the source policy are shown, not dropped (ai-engineer follow-up)", () => {
  it("splits usable proposals from refused ones", () => {
    const { usable, refused: r } = splitRefused([ok, refused]);
    expect(usable).toEqual([ok]);
    expect(r).toEqual([refused]);
  });
  it("turns a refused proposal into a 'planner decision needed' note with the reasons", () => {
    expect(refusedAsDecisions([refused])).toEqual([{ text: "Hep aynı derslik", reason: "untargeted: say which classes; soft structural rule", source_ref: null, decision: true }]);
  });
});
