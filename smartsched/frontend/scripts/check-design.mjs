#!/usr/bin/env node
// Static design-system gates (docs/review/2026-10-15-uiux-visual-review.md §5; docs/design/tokens.md §A).
//
//   npm run check:design            # exit 1 on any new violation
//   npm run check:design -- --list  # print every violation, allow-listed ones too
//
// Rules on smartsched/frontend/src (tests excluded):
//   outline-none            0 anywhere (the ring must stay visible; popups use outline-hidden)
//   text-[Npx]              0 (use type-* / text-2xs)
//   shadow-[                0 outside components/ui/** (use edge-* / shadow-elev-* / glass-*)
//   <button                 0 outside components/ui/** (use Button / IconButton / SegmentedControl)
//   Sparkles                0 (an "AI" tell; pick a section icon)
// plus docs/design/v2/verify-contrast.mjs (WCAG pairs, border-control, faculty ink, label-4).
//
// ALLOW is a ratchet for files that still carry violations: the count per file may only go DOWN. Owners: the
// shell/admin agent and the Phase 19 UI agent migrate theirs (see the design-system hand-off in docs/PROGRESS.md);
// the design-system agent's own remaining raw <button>s are listed too. Lower a number (or delete the entry)
// when a file improves; the gate fails if a count grows or a new file appears.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, "../src");
const ALLOW = JSON.parse(readFileSync(join(here, "check-design.allow.json"), "utf8"));

const RULES = [
  { id: "outline-none", re: /(?<![\w-])outline-none(?![\w-])/g, scope: () => true },
  { id: "text-px", re: /(?<![\w-])text-\[[0-9.]+px\]/g, scope: () => true },
  { id: "shadow-arbitrary", re: /(?<![\w-])shadow-\[/g, scope: (rel) => !rel.startsWith("components/ui/") },
  { id: "raw-button", re: /<button\b/g, scope: (rel) => !rel.startsWith("components/ui/") },
  { id: "sparkles", re: /\bSparkles\b/g, scope: () => true },
];

function walk(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return walk(p);
    return /\.(tsx?|css)$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

const list = process.argv.includes("--list");
const found = {};
for (const file of walk(SRC)) {
  const rel = relative(SRC, file).split("\\").join("/");
  const text = readFileSync(file, "utf8");
  for (const r of RULES) {
    if (!r.scope(rel)) continue;
    const n = (text.match(r.re) ?? []).length;
    if (n) (found[r.id] ??= {})[rel] = n;
  }
}

let failures = 0;
const lines = [];
for (const r of RULES) {
  const files = found[r.id] ?? {};
  const allow = ALLOW[r.id] ?? {};
  let total = 0;
  for (const [rel, n] of Object.entries(files)) {
    total += n;
    const max = allow[rel] ?? 0;
    if (n > max) {
      failures++;
      lines.push(`FAIL ${r.id}: ${rel} has ${n}${max ? ` (allowed ${max}; the ratchet only goes down)` : ""}`);
    } else if (list) lines.push(`allow ${r.id}: ${rel} ${n}/${max}`);
  }
  const stale = Object.keys(allow).filter((rel) => !(rel in files));
  lines.push(`${r.id}: ${total} in ${Object.keys(files).length} files${stale.length ? ` · ${stale.length} allow-list entries are clean now (remove them)` : ""}`);
}

const contrast = spawnSync(process.execPath, [resolve(here, "../../../docs/design/v2/verify-contrast.mjs")], { encoding: "utf8" });
const last = (contrast.stdout || "").trim().split("\n").pop();
lines.push(`verify-contrast: ${last}`);
if (contrast.status !== 0) {
  failures++;
  lines.push(contrast.stdout.split("\n").filter((l) => l.includes("FAIL")).join("\n"));
}

console.log(lines.join("\n"));
console.log(failures ? `\ncheck:design FAILED (${failures})` : "\ncheck:design passed");
process.exit(failures ? 1 : 0);
