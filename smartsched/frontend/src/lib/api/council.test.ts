/**
 * Council contract: payloads recorded from the real backend (room master + English CSV of the Bahar list +
 * DOCX memo, no API key) parse with the schemas the onboarding UI uses.
 */
import { describe, expect, it } from "vitest";
import commit from "./__fixtures__/real/council_commit.json";
import job from "./__fixtures__/real/council_job.json";
import created from "./__fixtures__/real/council_job_created.json";
import review from "./__fixtures__/real/council_review.json";
import reviewPost from "./__fixtures__/real/council_review_post.json";
import { CommitOut, CouncilJob, ReviewOut } from "./council";

describe("council contract (recorded payloads)", () => {
  it("job: files routed per shape, steps per agent, a plan with term groups", () => {
    const j = CouncilJob.parse(job);
    expect(j.ai_mode).toBe("heuristic");
    expect(j.files.map((f) => f.route)).toEqual(["fast:room-master", "general", "general"]);
    expect(j.files[1].counts.meeting).toBe(1348);
    expect(j.files[1].steps.map((s) => s.agent)).toEqual(["intake", "structure", "extract", "rules"]);
    expect(j.cross_steps.map((s) => s.agent)).toEqual(["reconcile", "planner", "critic"]);
    expect(j.plan?.groups[0].files).toEqual([1]);
    expect(j.plan?.global_files).toEqual([0, 2]);
    expect(CouncilJob.parse(created).status).toBe("QUEUED");
  });

  it("review: blocking mapping and merge items, rule texts that need the model", () => {
    const r = ReviewOut.parse(review);
    expect(r.blocking).toBeGreaterThan(0);
    const kinds = new Set(r.items.map((i) => i.kind));
    expect(kinds.has("mapping") && kinds.has("rule_text") && kinds.has("plan")).toBe(true);
    const mapping = r.items.find((i) => i.kind === "mapping");
    expect(mapping?.samples?.length).toBeGreaterThan(0);
    expect(ReviewOut.parse(reviewPost).blocking).toBe(0);
  });

  it("commit: term created, general records written, fast-path report", () => {
    const c = CommitOut.parse(commit);
    expect(c.term_code).toBe("2026-BAHAR-EN");
    expect(c.general.meeting_requests).toBe(1348);
    expect(c.fast_path).toHaveLength(1);
  });
});
