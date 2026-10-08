import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "./client";
import type { ImportJob } from "./schemas";
import { waitForImport } from "./shell-extra";

const job = (status: ImportJob["status"], rows = 0): ImportJob => ({ id: 7, kind: "planning-list", filename: "f.xlsx", status, summary: { rows, created: 0, updated: 0, skipped: 0, warnings: [] }, created_at: "2026-10-08T00:00:00Z" });
const backend = (statuses: { status: string; summary: Record<string, unknown> }[]) => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    const next = statuses.shift() ?? { status: "DONE", summary: {} };
    return new Response(JSON.stringify({ id: 7, kind: "planning-list", filename: "f.xlsx", created_at: "2026-10-08T00:00:00", ...next }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
};

afterEach(() => vi.unstubAllGlobals());

describe("waitForImport (POST /imports answers 202 with a queued job)", () => {
  it("polls GET /imports/{id} until the importer finished and returns the real report", async () => {
    const calls = backend([{ status: "RUNNING", summary: {} }, { status: "DONE", summary: { rows_total: 1529 } }]);
    const out = await waitForImport(job("QUEUED"), undefined, 1);
    expect(out.status).toBe("DONE");
    expect(out.summary.rows).toBe(1529);
    expect(calls).toHaveLength(2);
    expect(calls[0]).toContain("/api/v1/imports/7");
  });

  it("returns a finished job at once and rejects a failed one", async () => {
    const calls = backend([{ status: "FAILED", summary: {} }]);
    expect((await waitForImport(job("DONE", 5), undefined, 1)).summary.rows).toBe(5);
    expect(calls).toHaveLength(0);
    await expect(waitForImport(job("RUNNING"), undefined, 1)).rejects.toBeInstanceOf(HttpError);
  });
});
