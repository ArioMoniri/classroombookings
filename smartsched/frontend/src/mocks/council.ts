/**
 * MSW handlers for the Ingestion Council (`/api/v1/council`), replaying payloads recorded from the real
 * backend (room master + English CSV of the Bahar list + DOCX memo, no API key; see
 * src/lib/api/__fixtures__/real/council_*.json). One job; state resets with `resetCouncilMock()`.
 */
import { HttpResponse, http } from "msw";
import commit from "@/lib/api/__fixtures__/real/council_commit.json";
import job from "@/lib/api/__fixtures__/real/council_job.json";
import created from "@/lib/api/__fixtures__/real/council_job_created.json";
import jobs from "@/lib/api/__fixtures__/real/council_jobs.json";
import review from "@/lib/api/__fixtures__/real/council_review.json";
import reviewPost from "@/lib/api/__fixtures__/real/council_review_post.json";

let decided = false;
let committed = false;

export function resetCouncilMock(): void {
  decided = false;
  committed = false;
}

export function createCouncilHandlers(base: string) {
  return [
    http.post(`${base}/council/jobs`, () => {
      resetCouncilMock();
      return HttpResponse.json(created, { status: 202 });
    }),
    http.get(`${base}/council/jobs`, () => HttpResponse.json(jobs)),
    http.get(`${base}/council/jobs/:id`, () =>
      HttpResponse.json({ ...job, status: committed ? "COMMITTED" : decided ? "READY" : job.status, commits: committed ? [commit] : [] }),
    ),
    http.get(`${base}/council/jobs/:id/review`, () => HttpResponse.json(decided ? reviewPost : review)),
    http.post(`${base}/council/jobs/:id/review`, () => {
      decided = true;
      return HttpResponse.json(reviewPost);
    }),
    http.post(`${base}/council/jobs/:id/commit`, () => {
      if (!decided) return HttpResponse.json({ detail: "review items must be decided first" }, { status: 409 });
      committed = true;
      return HttpResponse.json(commit);
    }),
  ];
}
