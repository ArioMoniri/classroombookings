// HB-23c (helper-file-router.md §8.4 "Empty states"): one "Elinizde bir dosya mı var?" link per empty state, never a
// second drop zone. /admin/users is covered by a render test (users-import-handoff.test.tsx); the rooms list and the
// fresh dashboard have no render harness yet, so their placement is pinned at the source.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const read = (rel: string) => readFileSync(resolve(import.meta.dirname, "..", rel), "utf8");

describe("empty-state file links", () => {
  it("/admin/rooms with no rooms", () => {
    const src = read("admin/rooms-admin.tsx");
    expect(src).toMatch(/rooms\.data && rooms\.data\.length === 0 \? <HelperFileLink \/> : null/);
  });

  it("a fresh /dashboard (no term yet): next to 'İçe aktar' in the empty state", () => {
    const src = read("dashboard/dashboard-view.tsx");
    const empty = src.slice(src.indexOf("if (!termsLoading && !term)"), src.indexOf("if (!termsLoading && !term)") + 900);
    expect(empty).toContain("<HelperFileLink");
  });

  it("the link itself is not a drop zone", () => {
    const src = read("helper/file-link.tsx");
    expect(src).not.toMatch(/onDrop|onDragOver/);
  });
});
