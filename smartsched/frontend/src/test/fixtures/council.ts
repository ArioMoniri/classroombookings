/**
 * Test fixture (vitest only, never imported by app code): a fetch stand-in for the Ingestion Council
 * (`/api/v1/council`) that replays payloads recorded from the real backend (room master + English CSV of
 * the Bahar list + DOCX memo, no API key; see src/lib/api/__fixtures__/real/council_*.json). One job;
 * every call to `councilBackend()` starts a fresh one. Use with `vi.stubGlobal("fetch", backend.fetch)`.
 */
import commit from "@/lib/api/__fixtures__/real/council_commit.json";
import job from "@/lib/api/__fixtures__/real/council_job.json";
import created from "@/lib/api/__fixtures__/real/council_job_created.json";
import jobs from "@/lib/api/__fixtures__/real/council_jobs.json";
import review from "@/lib/api/__fixtures__/real/council_review.json";
import reviewPost from "@/lib/api/__fixtures__/real/council_review_post.json";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export interface CouncilBackend {
  /** "METHOD /path" of every request, in order */
  calls: string[];
  fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

export function councilBackend(): CouncilBackend {
  let decided = false;
  let committed = false;
  const calls: string[] = [];

  const route = (method: string, path: string): Response => {
    if (method === "POST" && path === "/api/v1/council/jobs") {
      decided = false;
      committed = false;
      return json(created, 202);
    }
    if (method === "GET" && path === "/api/v1/council/jobs") return json(jobs);
    if (/^\/api\/v1\/council\/jobs\/\d+\/review$/.test(path)) {
      if (method === "POST") decided = true;
      return json(decided ? reviewPost : review);
    }
    if (method === "POST" && /^\/api\/v1\/council\/jobs\/\d+\/commit$/.test(path)) {
      if (!decided) return json({ detail: "review items must be decided first" }, 409);
      committed = true;
      return json(commit);
    }
    if (method === "GET" && /^\/api\/v1\/council\/jobs\/\d+$/.test(path)) {
      return json({ ...job, status: committed ? "COMMITTED" : decided ? "READY" : job.status, commits: committed ? [commit] : [] });
    }
    return json({ detail: `no recorded payload for ${method} ${path}` }, 501);
  };

  return {
    calls,
    fetch: async (input, init) => {
      const req = new Request(new URL(String(input instanceof Request ? input.url : input), "http://localhost"), init);
      const path = new URL(req.url).pathname;
      calls.push(`${req.method} ${path}`);
      return route(req.method, path);
    },
  };
}
