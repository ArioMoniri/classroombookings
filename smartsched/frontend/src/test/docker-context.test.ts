/** The production image builds from smartsched/frontend with .dockerignore applied, and `next build` type-checks
 * every .ts/.tsx under src (tests included). An import from an ignored folder (e2e/, scripts/) works locally and
 * fails only in Docker (pod run #97 images gate, 2026-10-18). */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "../..");
const IGNORED = readFileSync(join(ROOT, ".dockerignore"), "utf8")
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith("#") && !l.startsWith("!") && !l.includes("*") && !l.includes("."));

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? files(join(dir, d.name)) : /\.(ts|tsx|mts)$/.test(d.name) ? [join(dir, d.name)] : [],
  );
}

describe("src stays inside the Docker build context", () => {
  it("imports nothing from a .dockerignore'd folder", () => {
    const bad: string[] = [];
    for (const f of files(join(ROOT, "src"))) {
      for (const m of readFileSync(f, "utf8").matchAll(/(?:from\s+|import\()\s*["'](\.{1,2}\/[^"']+)["']/g)) {
        const top = relative(ROOT, resolve(f, "..", m[1])).split(/[\\/]/)[0];
        if (IGNORED.includes(top)) bad.push(`${relative(ROOT, f)} -> ${m[1]}`);
      }
    }
    expect(IGNORED).toContain("e2e");
    expect(bad).toEqual([]);
  });
});
