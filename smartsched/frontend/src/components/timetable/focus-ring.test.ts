// @vitest-environment node
/**
 * U-01 (persona test 2026-10-15): the focus ring was invisible. In Tailwind v4 `outline-none` is
 * `outline-style: none`, and `outline-hidden` keeps `--tw-outline-style: none` too, so
 * `focus-visible:outline-2` (which reads `outline-style: var(--tw-outline-style)`) draws nothing
 * unless the focused state also sets the style (`focus-visible:outline-solid`).
 *
 * Three guards: the real Tailwind compiler proves the semantics, globals.css ends with the UNLAYERED
 * `:focus-visible{--tw-outline-style:solid}` that makes any focus-visible width paint (review 2026-10-15 §2),
 * and a scan of every component and route proves no `outline-none` is left and every hidden-outline class
 * string restores a solid ring.
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

/** design-system overhaul 2026-10-15: the scan covers every source under components/ and app/. */
const SCOPE = ["components", "app"];
/**
 * Files owned by other agents that still fail the scan. They are reported (docs/PROGRESS.md hand-off) instead
 * of edited here; remove an entry once its owner migrates it. Only exact `path: reason` pairs are skipped.
 */
const PENDING_MIGRATION = new Set<string>([]);
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
    expect(offenders.filter((o) => !PENDING_MIGRATION.has(o))).toEqual([]);
  });

  it("globals.css restores the outline style for :focus-visible outside every @layer", () => {
    const sheet = readFileSync(path.join(root, "app/globals.css"), "utf8");
    // strip comments, then walk the braces: the rule must sit at depth 0 (unlayered)
    const src = sheet.replace(/\/\*[\s\S]*?\*\//g, "");
    let depth = 0;
    let found = false;
    for (let i = 0; i < src.length; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") depth--;
      else if (depth === 0 && src.startsWith(":focus-visible", i)) {
        const body = src.slice(src.indexOf("{", i), src.indexOf("}", i));
        if (/--tw-outline-style:\s*solid/.test(body)) found = true;
      }
    }
    expect(found).toBe(true);
    expect(sheet).not.toMatch(/outline-ring\/50/);
  });
});
