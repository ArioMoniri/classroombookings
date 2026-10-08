#!/usr/bin/env node
// Liquid Glass contrast gate — parses the @tokens blocks in smartsched/frontend/src/app/globals.css,
// composites every translucent material over its worst-case backdrop, and checks WCAG 2.x ratios.
//
//   node docs/design/v2/verify-contrast.mjs            # table + exit 1 on any failure
//   node docs/design/v2/verify-contrast.mjs --json     # machine-readable
//
// Model: browsers blend translucent layers in sRGB (source-over). Blur only averages what is
// behind the glass, so a uniform worst-case colour behind it is the strict bound.
// Backdrops:
//   scene   - the five mesh samples (base, highlight, tint corner, warm corner, cool corner)
//   content - the darkest (light theme: #000) / lightest (dark theme: #fff) thing that can scroll
//             under floating chrome. Only thick + chrome materials may float over content (rule G1).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const cssPath = resolve(here, "../../../smartsched/frontend/src/app/globals.css");
const css = readFileSync(cssPath, "utf8");

function block(name) {
  const m = css.match(new RegExp(`/\\* @tokens ${name}[^*]*\\*/([\\s\\S]*?)/\\* @end \\*/`));
  if (!m) throw new Error(`@tokens ${name} block not found in globals.css`);
  return m[1];
}
function decls(text) {
  const out = {};
  for (const m of text.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}
const light = decls(block("light"));
const dark = { ...light, ...decls(block("dark")) };
const accentBlock = block("accents");
const presets = {};
for (const m of accentBlock.matchAll(/(:root:not\(\.dark\)|\.dark)\[data-accent="([a-z]+)"\]\s*\{([^}]*)\}/g)) {
  const theme = m[1] === ".dark" ? "dark" : "light";
  presets[`${theme}:${m[2]}`] = decls(m[3]);
}

function parse(v, vars) {
  v = v.trim();
  const ref = v.match(/^var\((--[a-z0-9-]+)\)$/);
  if (ref) return parse(vars[ref[1]], vars);
  let m = v.match(/^#([0-9a-f]{6})$/i);
  if (m) return [parseInt(m[1].slice(0, 2), 16), parseInt(m[1].slice(2, 4), 16), parseInt(m[1].slice(4, 6), 16), 1];
  m = v.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+))?\s*\)$/);
  if (m) return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
  throw new Error(`cannot parse colour "${v}"`);
}
const over = (top, bottom) => {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1);
};
const mix = (c, base, pct) => over([c[0], c[1], c[2], pct / 100], base);
const lum = (c) => {
  const f = (x) => {
    x /= 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const hex = (c) => "#" + c.slice(0, 3).map((x) => Math.round(x).toString(16).padStart(2, "0")).join("");

const rows = [];
let failures = 0;
function check(theme, what, fgC, bgC, min, note = "") {
  const r = ratio(fgC, bgC);
  const ok = r >= min;
  if (!ok) failures++;
  rows.push({ theme, what, fg: hex(fgC), bg: hex(bgC), ratio: +r.toFixed(2), min, ok, note });
}

function themeChecks(theme, v) {
  const P = (k) => parse(v[k], v);
  const scene = P("--scene");
  const accent = P("--accent");
  const sceneSamples = {
    base: scene,
    highlight: P("--scene-hi"),
    tintCorner: mix(accent, scene, parseFloat(v["--scene-tint-mix"])),
    warmCorner: over(P("--scene-warm"), scene),
    coolCorner: over(P("--scene-cool"), scene),
  };
  const content = theme === "light" ? [0, 0, 0, 1] : [255, 255, 255, 1];
  const materials = {
    "ultra-thin": { tint: P("--mat-ultra-thin"), solid: P("--mat-ultra-thin-solid"), overContent: false },
    thin: { tint: P("--mat-thin"), solid: P("--mat-thin-solid"), overContent: false },
    regular: { tint: P("--mat-regular"), solid: P("--mat-regular-solid"), overContent: false },
    thick: { tint: P("--mat-thick"), solid: P("--mat-thick-solid"), overContent: true },
    chrome: { tint: P("--mat-chrome"), solid: P("--mat-chrome-solid"), overContent: true },
  };
  const labels = { "label-1": P("--label-1"), "label-2": P("--label-2"), "label-3": P("--label-3") };

  // worst composite per material = the backdrop giving the lowest ratio for each label
  const composites = {};
  for (const [mName, m] of Object.entries(materials)) {
    const backs = Object.entries(sceneSamples).map(([k, c]) => [`scene:${k}`, over(m.tint, c)]);
    if (m.overContent) backs.push(["content", over(m.tint, content)]);
    composites[mName] = backs;
    for (const [lName, l] of Object.entries(labels)) {
      let worst = null;
      for (const [bName, b] of backs) {
        const r = ratio(l, b);
        if (!worst || r < worst.r) worst = { r, b, bName };
      }
      check(theme, `${lName} on ${mName} (worst: ${worst.bName})`, l, worst.b, 4.5);
    }
    // solid fallback (reduced transparency / no backdrop-filter)
    check(theme, `label-2 on ${mName} solid fallback`, labels["label-2"], m.solid, 4.5);
    check(theme, `label-3 on ${mName} solid fallback`, labels["label-3"], m.solid, 4.5);
  }
  // body text directly on the scene
  for (const [k, c] of Object.entries(sceneSamples)) check(theme, `label-3 on scene:${k}`, labels["label-3"], c, 4.5);

  // accent: text-on-accent and accent-as-text (links) on cards
  const accentPresets = [["default", v]].concat(
    Object.entries(presets).filter(([k]) => k.startsWith(theme + ":")).map(([k, p]) => [k.split(":")[1], { ...v, ...p }]),
  );
  for (const [name, pv] of accentPresets) {
    const a = parse(pv["--accent"], pv);
    const afg = parse(pv["--accent-fg"], pv);
    const at = parse(pv["--accent-text"], pv);
    const focus = parse(pv["--focus"], pv);
    check(theme, `accent-fg on accent [${name}]`, afg, a, 4.5);
    const s = { ...sceneSamples, tintCorner: mix(a, scene, parseFloat(v["--scene-tint-mix"])) };
    let worstText = null;
    for (const [bName, b] of Object.entries(s).flatMap(([k, c]) => [[`regular/${k}`, over(materials.regular.tint, c)], [`scene:${k}`, c]])) {
      const r = ratio(at, b);
      if (!worstText || r < worstText.r) worstText = { r, b, bName };
    }
    check(theme, `accent-text (links) [${name}] (worst: ${worstText.bName})`, at, worstText.b, 4.5);
    let worstFocus = null;
    for (const [k, c] of Object.entries(s)) {
      const r = ratio(focus, c);
      if (!worstFocus || r < worstFocus.r) worstFocus = { r, c, k };
    }
    check(theme, `focus ring vs scene [${name}] (worst: ${worstFocus.k})`, focus, worstFocus.c, 3, "non-text 3:1");
    // the accent-soft selected-row tint must keep label-1 readable
    check(theme, `label-1 on accent-soft over regular [${name}]`, labels["label-1"], over(parse(pv["--accent-soft"], pv), over(materials.regular.tint, s.tintCorner)), 4.5);
  }

  // status: fg on its tint, over a regular card on the worst scene sample, and over the solid card
  for (const st of ["feasible", "infeasible", "warning", "locked", "preoccupied", "tip", "pclab"]) {
    const fg = P(`--status-${st}-fg`);
    const bg = P(`--status-${st}-bg`);
    let worst = null;
    for (const [bName, b] of composites.regular.concat([["regular solid", materials.regular.solid], ["thick/content", over(materials.thick.tint, content)]])) {
      const c = over(bg, b);
      const r = ratio(fg, c);
      if (!worst || r < worst.r) worst = { r, c, bName };
    }
    check(theme, `status ${st} fg on tint (worst: ${worst.bName})`, fg, worst.c, 4.5);
    if (st !== "preoccupied") {
      const solid = P(`--status-${st}-solid`);
      const onSolid = theme === "light" && !["warning", "feasible"].includes(st) ? [255, 255, 255, 1] : P("--label-1");
      const darkText = theme === "dark" || st === "warning" || st === "feasible" ? [17, 17, 20, 1] : onSolid;
      check(theme, `text on ${st}-solid badge`, darkText, solid, 4.5, theme === "light" && !["warning", "feasible"].includes(st) ? "white text" : "#111114 text");
    }
  }
}

themeChecks("light", light);
themeChecks("dark", dark);

if (process.argv.includes("--json")) {
  console.log(JSON.stringify({ failures, rows }, null, 2));
} else {
  console.log("| theme | pair | fg | composite bg | ratio | min | |");
  console.log("|---|---|---|---|---|---|---|");
  for (const r of rows) console.log(`| ${r.theme} | ${r.what} | \`${r.fg}\` | \`${r.bg}\` | ${r.ratio} | ${r.min} | ${r.ok ? "pass" : "FAIL"}${r.note ? " · " + r.note : ""} |`);
  console.log(`\n${rows.length} pairs, ${failures} failures`);
}
process.exit(failures ? 1 : 0);
