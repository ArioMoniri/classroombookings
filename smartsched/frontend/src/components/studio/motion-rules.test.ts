// @vitest-environment node
/**
 * Motion audit 2026-10-15 T5 / T11 guards for the Studio (motion_designer skill §4, §8):
 * - the in-app "Reduce motion" switch must work: `useReduce()` from @/lib/motion, never motion's `useReducedMotion`;
 * - only transform / opacity animate: no `height` (or width) in initial / animate / exit objects;
 * - tokens, not raw numbers: no `duration: 0.x` literals;
 * - no extra live backdrop-filter surface over the scrolling rule list (`backdrop-blur`).
 */
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const dir = path.resolve(__dirname);
const files = readdirSync(dir)
  .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f))
  .map((f) => ({ f, src: readFileSync(path.join(dir, f), "utf8") }));

describe("Studio motion rules", () => {
  it("uses useReduce() (OS + in-app switch), never motion's useReducedMotion", () => {
    expect(files.filter(({ src }) => /import\s*\{[^}]*\buseReducedMotion\b[^}]*\}\s*from\s*"motion\/react"/.test(src)).map(({ f }) => f)).toEqual([]);
  });
  it("animates no layout property (height / width) in initial / animate / exit", () => {
    // per line: the motion props of one element sit on one line in this codebase (nested objects included)
    const bad = files.filter(({ src }) => src.split("\n").some((l) => /\b(?:initial|animate|exit)=\{/.test(l) && /[{,]\s*(?:height|width)\s*:/.test(l))).map(({ f }) => f);
    expect(bad).toEqual([]);
  });
  it("uses motion tokens, not raw durations", () => {
    expect(files.filter(({ src }) => /duration:\s*0\.\d/.test(src)).map(({ f }) => f)).toEqual([]);
  });
  it("adds no backdrop-blur surface", () => {
    expect(files.filter(({ src }) => /backdrop-blur/.test(src)).map(({ f }) => f)).toEqual([]);
  });
});
