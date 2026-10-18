// E2EB-F13 (FIX-K): /exams/invigilation at 390 shifted 0.12 when the 60dvh placeholder gave way to a shorter panel;
// both panels now keep the placeholder's minimum height.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const src = readFileSync(path.join(__dirname, "invigilation-view.tsx"), "utf8");
const line = (needle: string) => src.split("\n").find((l) => l.includes(needle)) ?? "";

describe("invigilation panels reserve the placeholder's height", () => {
  it("the plans and pool panels have min-h-[60dvh] like invig-loading", () => {
    expect(line('data-testid="invig-loading"')).toContain("min-h-[60dvh]");
    expect(line('id="invig-panel-plans"')).toContain("min-h-[60dvh]");
    expect(line('id="invig-panel-pool"')).toContain("min-h-[60dvh]");
  });
});
