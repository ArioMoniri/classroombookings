/**
 * helper.md §3.4: every "Göster" anchor the feature index may name exists as a `data-tour` attribute on its page
 * (one attribute each, no layout change), so the helper's spotlight finds it instead of "Bu düğme şu an bu sayfada
 * görünmüyor".
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "../../..");
const helperMd = readFileSync(resolve(ROOT, "../../docs/design/v3/helper.md"), "utf8");

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) sources(p, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

const listed = (() => {
  const section = helperMd.split("### 3.4")[1]?.split("\n## ")[0] ?? "";
  return [...section.matchAll(/`([a-z][a-z0-9-]+)`/g)].map((m) => m[1]!).filter((a) => a.includes("-") && a !== "data-tour");
})();

describe("helper.md §3.4 data-tour anchors", () => {
  it("lists the 18 anchors", () => {
    expect(listed).toHaveLength(18);
  });

  it("each one is on its page", () => {
    const code = sources(resolve(ROOT, "src")).map((f) => readFileSync(f, "utf8")).join("\n");
    const missing = listed.filter((a) => !code.includes(`data-tour="${a}"`));
    expect(missing).toEqual([]);
  });
});
