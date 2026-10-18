// HB-23c (helper-file-router.md §6.3, §6.5, §11.2 "file-handoff.test.ts"): the target page addresses per feature_id,
// the token never in an address, the sessionStorage mirror (never localStorage), the expiry, and the stage id.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { isStageGone, sidOf, stageIdOf } from "@/lib/api/helper-files";
import { HttpError } from "@/lib/api/client";
import { HANDOFF_STORAGE_KEY, fileHandoffHref, handedFile, useFileHandoffStore, useHelperFileHandoff, type FileHandoff } from "./file-handoff";

const TOKEN = `${btoa(JSON.stringify({ k: "file", s: "abc123", u: 1 })).replace(/=+$/, "")}.c2lnbmF0dXJl`;

const sample = (over: Partial<FileHandoff> = {}): FileHandoff => ({
  featureId: "import",
  kind: "weekly_grid",
  params: { kind: "weekly-grid", term_id: 12, year: 2026 },
  items: [{ token: TOKEN, sid: "abc123", name: "Bahar_son.xlsx", size: 1000, format: "xlsx", expiresAt: Date.now() + 600_000 }],
  at: Date.now(),
  ...over,
});

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  useFileHandoffStore.getState().clear();
});
afterEach(() => vi.useRealTimers());

describe("fileHandoffHref", () => {
  it("builds each page's address from the server's params", () => {
    expect(fileHandoffHref("import", { kind: "weekly-grid", term_id: 12, year: 2026 })).toBe("/import?kind=weekly-grid&term=12&year=2026&from=helper");
    expect(fileHandoffHref("import", { kind: "planning-list", term_id: 7 })).toBe("/import?kind=planning-list&term=7&from=helper");
    expect(fileHandoffHref("onboarding")).toBe("/onboarding?from=helper");
    expect(fileHandoffHref("admin.users", { import: 1 })).toBe("/admin/users?import=1&from=helper");
    expect(fileHandoffHref("profile.calendar")).toBe("/profile?calendar=1");
    expect(fileHandoffHref("my_classes")).toMatch(/^\/my-classes/);
    expect(fileHandoffHref("no.such.feature")).toBeNull();
  });

  it("never carries a token or an unknown param, and drops bad values", () => {
    const href = fileHandoffHref("import", { kind: "../../etc", term_id: "12x", year: 99999, upload_token: TOKEN, token: TOKEN } as never)!;
    expect(href).toBe("/import?from=helper");
    for (const id of ["import", "onboarding", "admin.users", "profile.calendar", "reserve", "find_room", "my_requests"]) {
      const h = fileHandoffHref(id, { upload_token: TOKEN, kind: "planning-list", term_id: 3 } as never) ?? "";
      expect(h).not.toContain(TOKEN);
      expect(h).not.toContain("token");
    }
  });
});

describe("the hand-over slot", () => {
  it("mirrors to sessionStorage, never localStorage, and keeps the File in memory only", () => {
    const f = new File(["x"], "Bahar_son.xlsx");
    useFileHandoffStore.getState().set(sample({ items: [{ token: TOKEN, sid: "abc123", name: f.name, size: f.size, format: "xlsx", expiresAt: Date.now() + 1000 }] }), [f]);
    expect(JSON.parse(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)!)).toMatchObject({ featureId: "import" });
    expect(Object.keys(window.localStorage).some((k) => (window.localStorage.getItem(k) ?? "").includes(TOKEN))).toBe(false);
    expect(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)).not.toContain("lastModified");
    expect(handedFile({ name: f.name, size: f.size })).toBe(f);
    useFileHandoffStore.getState().clear();
    expect(window.sessionStorage.getItem(HANDOFF_STORAGE_KEY)).toBeNull();
    expect(handedFile({ name: f.name, size: f.size })).toBeNull();
  });

  it("a page sees only the hand-over meant for it (feature and kind)", () => {
    useFileHandoffStore.getState().set(sample());
    expect(renderHook(() => useHelperFileHandoff("import", { kind: "weekly-grid" })).result.current.handoff).not.toBeNull();
    expect(renderHook(() => useHelperFileHandoff("import", { kind: "exam-list" })).result.current.handoff).toBeNull();
    expect(renderHook(() => useHelperFileHandoff("onboarding")).result.current.handoff).toBeNull();
  });

  it("turns expired after the 10 minutes (the expiry line)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-18T16:32:00Z"));
    useFileHandoffStore.getState().set(sample({ items: [{ ...sample().items[0]!, expiresAt: Date.now() + 600_000 }] }));
    const { result } = renderHook(() => useHelperFileHandoff("import"));
    expect(result.current.expired).toBe(false);
    act(() => {
      vi.advanceTimersByTime(600_100);
    });
    expect(result.current.expired).toBe(true);
  });

  it("remove() deletes the stage on the server and empties the slot", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    useFileHandoffStore.getState().set(sample());
    const { result } = renderHook(() => useHelperFileHandoff("import"));
    act(() => result.current.remove());
    expect(useFileHandoffStore.getState().handoff).toBeNull();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain("/api/v1/helper/files/abc123");
    expect(init.method).toBe("DELETE");
    vi.unstubAllGlobals();
  });
});

describe("stage helpers", () => {
  it("reads the stage id from the token's payload when the stage does not name it", () => {
    expect(stageIdOf(TOKEN)).toBe("abc123");
    expect(stageIdOf("not-a-token")).toBeNull();
    expect(stageIdOf(`${btoa(JSON.stringify({ sid: "older1" })).replace(/=+$/, "")}.x`)).toBe("older1");
    expect(sidOf({ upload_token: TOKEN, sid: "given1" })).toBe("given1");
    expect(sidOf({ upload_token: TOKEN })).toBe("abc123");
  });

  it("knows a used or expired stage (410 stage_used / stage_expired)", () => {
    expect(isStageGone(new HttpError(410, "gone", { code: "stage_used" }))).toBe(true);
    expect(isStageGone(new HttpError(400, "x", { detail: { code: "stage_expired" } }))).toBe(true);
    expect(isStageGone(new HttpError(403, "x", { code: "forbidden" }))).toBe(false);
  });
});
