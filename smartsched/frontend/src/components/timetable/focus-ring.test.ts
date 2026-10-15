// @vitest-environment node
/**
 * U-01 (persona test 2026-10-15): the focus ring was invisible. In Tailwind v4 `outline-none` is
 * `outline-style: none`, and `outline-hidden` keeps `--tw-outline-style: none` too, so
 * `focus-visible:outline-2` (which reads `outline-style: var(--tw-outline-style)`) draws nothing
 * unless the focused state also sets the style (`focus-visible:outline-solid`).
 *
 * Two guards: the real Tailwind compiler proves the semantics, and a scan of the calendar, studio,
 * classes, runs and chat sources proves every hidden-outline class string restores a solid ring.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { compile } from "tailwindcss";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../..");
const twBase = path.resolve(root, "../node_modules/tailwindcss");

async function css(classes: string[]): Promise<string> {
  const c = await compile('@import "tailwindcss/utilities";', {
    base: twBase,
    loadStylesheet: async (id: string, base: string) => {
      const p = id === "tailwindcss/utilities" ? path.join(twBase, "utilities.css") : path.resolve(base, id);
      return { content: readFileSync(p, "utf8"), base: path.dirname(p), path: p };
    },
  });
  return c.build(classes);
}

/** The outline-style a :focus-visible element ends with, resolving --tw-outline-style like the cascade does. */
function focusedOutlineStyle(sheet: string, classes: string[]): string {
  let varStyle = "solid"; // @property --tw-outline-style initial-value
  let style = "";
  const rules = [...sheet.matchAll(/\.([^\s{]+)\s*\{([^}]*)\}/g)].map((m) => ({ sel: m[1].replace(/\\/g, ""), body: m[2] }));
  // the utilities come out in Tailwind's order (base utilities, then variants), as in the browser
  for (const r of rules) {
    const cls = r.sel.replace(/:focus-visible$/, "");
    if (!classes.includes(cls)) continue;
    const v = /--tw-outline-style:\s*([\w-]+)/.exec(r.body);
    if (v) varStyle = v[1];
    const s = /(?:^|;|\s)outline-style:\s*([^;]+);/.exec(r.body);
    if (s) style = s[1].trim() === "var(--tw-outline-style)" ? varStyle : s[1].trim();
  }
  return style;
}

const SCOPE = ["components/studio", "components/timetable", "components/classes", "components/runs", "components/chat", "app/(app)/timetable", "app/(app)/classes", "app/(app)/generate", "app/(app)/runs"];
function sources(dir: string): string[] {
  const abs = path.join(root, dir);
  return readdirSync(abs).flatMap((f) => {
    const p = path.join(abs, f);
    if (statSync(p).isDirectory()) return sources(path.join(dir, f));
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

describe("focus ring (U-01)", () => {
  it("Tailwind: outline-none / outline-hidden + focus-visible:outline-2 draws nothing; adding focus-visible:outline-solid draws a ring", async () => {
    const broken = ["outline-none", "focus-visible:outline-2"];
    const stillBroken = ["outline-hidden", "focus-visible:outline-2"];
    const fixed = ["outline-hidden", "focus-visible:outline-2", "focus-visible:outline-solid"];
    const sheet = await css([...broken, ...fixed]);
    expect(focusedOutlineStyle(sheet, broken)).toBe("none");
    expect(focusedOutlineStyle(sheet, stillBroken)).toBe("none");
    expect(focusedOutlineStyle(sheet, fixed)).toBe("solid");
  });

  it("no `outline-none` token, and every hidden-outline class string with a focus-visible width sets the style", () => {
    const offenders: string[] = [];
    for (const file of SCOPE.flatMap(sources)) {
      const src = readFileSync(file, "utf8");
      const rel = path.relative(root, file);
      if (/(?<![\w-])outline-none(?![\w-])/.test(src)) offenders.push(`${rel}: outline-none`);
      for (const m of src.matchAll(/"[^"\n]*"|'[^'\n]*'|`[^`]*`/g)) {
        const s = m[0];
        if (!s.includes("outline-hidden")) continue;
        if (/(?<![\w:-])focus-visible:outline(?:-\d+)?(?![\w(\[-])/.test(s) && !s.includes("focus-visible:outline-solid")) offenders.push(`${rel}: ${s.slice(0, 80)}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
