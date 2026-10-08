#!/usr/bin/env node
// Motion audit for docs/lottie/*.json: every animated segment whose value changes must last
// <= 9 frames (300 ms at 30 fps, tokens.md section 6 "--dur-max"). Hold segments are exempt.
// Usage: node docs/lottie/build/audit.mjs   (exit 1 on violation). Licence: AGPL-3.0 (repository).
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const dir = join(dirname(fileURLToPath(import.meta.url)), "..");
let bad = 0;
for (const f of readdirSync(dir).filter((x) => x.endsWith(".json"))) {
  const j = JSON.parse(readFileSync(join(dir, f), "utf8"));
  const maxFrames = Math.floor(0.3 * j.fr);
  let segs = 0, longest = 0;
  const walk = (o, path) => {
    if (Array.isArray(o)) return o.forEach((v, i) => walk(v, path + "/" + i));
    if (!o || typeof o !== "object") return;
    if (o.a === 1 && Array.isArray(o.k)) {
      for (let i = 0; i < o.k.length - 1; i++) {
        const a = o.k[i], b = o.k[i + 1];
        if (a.h === 1 || JSON.stringify(a.s) === JSON.stringify(b.s)) continue;
        const d = b.t - a.t; segs++; longest = Math.max(longest, d);
        if (d > maxFrames) { bad++; console.error(`${f} ${path}: ${a.t}->${b.t} (${d} f > ${maxFrames})`); }
      }
    }
    for (const [k, v] of Object.entries(o)) walk(v, path + "/" + (o.nm && k === "it" ? o.nm : k));
  };
  walk(j, "");
  console.log(`${f.padEnd(26)} ${segs} tweens, longest ${longest} f = ${Math.round((longest / j.fr) * 1000)} ms, loop ${(j.op / j.fr).toFixed(1)} s`);
}
process.exit(bad ? 1 : 0);
