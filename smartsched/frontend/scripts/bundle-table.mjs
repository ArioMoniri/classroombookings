#!/usr/bin/env node
/**
 * Bundle table of an existing `next build` (CH12-F07, FIX-G 2026-10-18): Next 16 / Turbopack prints no route sizes,
 * so the CH-01 gates ("+0 kB on chart-less routes", "/dashboard and /admin/ai <= +110 kB", lazy ECharts <= 240 kB gz)
 * are checked against a table written by this script. It never builds; it reads `.next` only.
 *
 *   node scripts/bundle-table.mjs                        # markdown table of the current build
 *   node scripts/bundle-table.mjs --json > now.json      # the same as JSON
 *   node scripts/bundle-table.mjs --write docs/testing/bundle-baseline.json   # record a baseline
 *   node scripts/bundle-table.mjs --compare docs/testing/bundle-baseline.json [--max-kb 0]
 *
 * First load of a route = the build's root main files + every `static/chunks/*.js` named in the route's
 * `page_client-reference-manifest.js` (layouts included), gzip -9. It is a union of manifest entries, so treat the
 * absolute values as an upper bound and compare builds made the same way. `--compare` exits 1 when any route grew by
 * more than `--max-kb` (default: report only).
 */
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { gzipSync } from "node:zlib";

const args = process.argv.slice(2);
const flag = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? (args[i + 1] ?? "") : null;
};
const NEXT = flag("--dir") ?? join(process.cwd(), ".next");
if (!existsSync(join(NEXT, "build-manifest.json"))) {
  console.error(`no build at ${NEXT} (run next build first, or pass --dir)`);
  process.exit(2);
}

const gzCache = new Map();
function sizes(rel) {
  if (!gzCache.has(rel)) {
    const p = join(NEXT, rel);
    if (!existsSync(p)) gzCache.set(rel, { raw: 0, gz: 0 });
    else {
      const buf = readFileSync(p);
      gzCache.set(rel, { raw: buf.length, gz: gzipSync(buf, { level: 9 }).length });
    }
  }
  return gzCache.get(rel);
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name === "page_client-reference-manifest.js") out.push(p);
  }
  return out;
}

const build = JSON.parse(readFileSync(join(NEXT, "build-manifest.json"), "utf8"));
const root = build.rootMainFiles ?? [];
const appDir = join(NEXT, "server", "app");
const routes = {};
for (const file of existsSync(appDir) ? walk(appDir) : []) {
  const route =
    "/" +
    relative(appDir, file)
      .split(sep)
      .slice(0, -1)
      .filter((s) => !(s.startsWith("(") && s.endsWith(")")))
      .join("/");
  const chunks = new Set(root);
  for (const m of readFileSync(file, "utf8").matchAll(/static\/chunks\/[\w./-]+?\.js/g)) chunks.add(m[0]);
  const gz = [...chunks].reduce((n, c) => n + sizes(c).gz, 0);
  routes[route === "/" ? "/" : route.replace(/\/$/, "")] = { first_load_gz: gz, chunks: chunks.size };
}

const chunkDir = join(NEXT, "static", "chunks");
const largest = (existsSync(chunkDir) ? readdirSync(chunkDir) : [])
  .filter((f) => f.endsWith(".js"))
  .map((f) => ({ chunk: `static/chunks/${f}`, ...sizes(`static/chunks/${f}`) }))
  .sort((a, b) => b.gz - a.gz)
  .slice(0, 8);

const table = { build_id: readFileSync(join(NEXT, "BUILD_ID"), "utf8").trim(), routes, largest };
const kb = (n) => (n / 1024).toFixed(1);

if (flag("--write") !== null) {
  writeFileSync(flag("--write"), JSON.stringify(table, null, 2) + "\n");
  console.log(`wrote ${Object.keys(routes).length} routes to ${flag("--write")}`);
} else if (flag("--compare") !== null) {
  const base = JSON.parse(readFileSync(flag("--compare"), "utf8"));
  const max = flag("--max-kb") === null ? null : Number(flag("--max-kb"));
  let over = 0;
  console.log("| Route | Baseline kB gz | Now kB gz | Delta kB |\n|---|---|---|---|");
  for (const [route, now] of Object.entries(routes).sort()) {
    const was = base.routes?.[route]?.first_load_gz;
    const delta = was === undefined ? null : (now.first_load_gz - was) / 1024;
    if (max !== null && delta !== null && delta > max) over += 1;
    console.log(`| ${route} | ${was === undefined ? "—" : kb(was)} | ${kb(now.first_load_gz)} | ${delta === null ? "new" : delta.toFixed(1)} |`);
  }
  if (over) {
    console.error(`${over} route(s) grew by more than ${max} kB gz`);
    process.exit(1);
  }
} else if (args.includes("--json")) {
  console.log(JSON.stringify(table, null, 2));
} else {
  console.log(`Build ${table.build_id}\n\n| Route | First-load JS gz (kB, upper bound) |\n|---|---|`);
  for (const [route, r] of Object.entries(routes).sort()) console.log(`| ${route} | ${kb(r.first_load_gz)} |`);
  console.log("\n| Largest chunks | Raw kB | gz kB |\n|---|---|---|");
  for (const c of largest) console.log(`| ${c.chunk} | ${kb(c.raw)} | ${kb(c.gz)} |`);
}
