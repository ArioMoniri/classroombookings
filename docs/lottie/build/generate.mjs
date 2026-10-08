#!/usr/bin/env node
// SmartSched README animations: original Lottie (bodymovin v5) generator.
// Licence: same as the repository (AGPL-3.0, see /LICENSE.txt). Original work, no third-party assets.
//
// Usage:  node docs/lottie/build/generate.mjs [outDir]
// Writes  <name>-light.json and <name>-dark.json for hero-solver, nl-to-rules, file-to-rules, precheck-fix.
// Colours, radii and easings come from docs/design/tokens.md (sections 2, 4 and 6).
// Every single tween is <= 9 frames (300 ms at 30 fps); the loops are short narratives of such tweens.

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.argv[2] ?? join(HERE, ".."));
const FPS = 30;

// ---------------------------------------------------------------- colour + tokens
const hex = (h) => {
  const s = h.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16) / 255);
};
const toHex = (rgb) => "#" + rgb.map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("");
/** mix(a, b, t): t=0 -> a, t=1 -> b (sRGB, like CSS color-mix in srgb). */
const mix = (a, b, t) => toHex(hex(a).map((c, i) => c + (hex(b)[i] - c) * t));
const C = (h) => [...hex(h).map((v) => +v.toFixed(4)), 1];

const THEMES = {
  light: {
    bg: "#FFFFFF", surface: "#F8FAFC", surface2: "#F1F5F9", raised: "#FFFFFF",
    border: "#E2E8F0", borderStrong: "#94A3B8", ring: null,
    fg: "#0F172A", fgMuted: "#475569", fgSubtle: "#64748B",
    primary: "#2563EB", primaryFg: "#FFFFFF", primaryTint: "#EFF6FF",
    track: "#F1F5F9", toggleTrack: "#F1F5F9",
    feasible: { fg: "#15803D", bg: "#DCFCE7", border: "#86EFAC", solid: "#16A34A", on: "#FFFFFF" },
    infeasible: { fg: "#B91C1C", bg: "#FEE2E2", border: "#FCA5A5", solid: "#DC2626", on: "#FFFFFF" },
    warning: { fg: "#B45309", bg: "#FEF3C7", border: "#FCD34D", solid: "#F59E0B", on: "#0F172A" },
    cat: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    tintAmt: 0.14, barTo: "#0F172A", barAmt: 0.2, shadow: true,
  },
  dark: {
    bg: "#0B1220", surface: "#111827", surface2: "#1F2937", raised: "#1F2937",
    border: "#273449", borderStrong: "#475569", ring: "#334155",
    fg: "#F1F5F9", fgMuted: "#A1AEC2", fgSubtle: "#8B98AD",
    primary: "#60A5FA", primaryFg: "#0B1220", primaryTint: mix("#0B1220", "#60A5FA", 0.14),
    track: "#1F2937", toggleTrack: "#111827",
    feasible: { fg: "#4ADE80", bg: "#14532D", border: "#22C55E", solid: "#22C55E", on: "#0B1220" },
    infeasible: { fg: "#FCA5A5", bg: "#7F1D1D", border: "#EF4444", solid: "#F87171", on: "#0B1220" },
    warning: { fg: "#FCD34D", bg: "#78350F", border: "#F59E0B", solid: "#F59E0B", on: "#0B1220" },
    cat: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    tintAmt: 0.24, barTo: "#FFFFFF", barAmt: 0.25, shadow: false,
  },
};

// tokens.md section 6 easings as bezier handles
const EASE = {
  out: { o: { x: [0.16], y: [1] }, i: { x: [0.3], y: [1] } }, // --ease-out
  inOut: { o: { x: [0.65], y: [0] }, i: { x: [0.35], y: [1] } }, // --ease-in-out
  emph: { o: { x: [0.2], y: [0] }, i: { x: [0], y: [1] } }, // --ease-emphasized
  lin: { o: { x: [0], y: [0] }, i: { x: [1], y: [1] } },
};

// ---------------------------------------------------------------- property helpers
/** K([[t, value, ease?], ...]) -> animated property. `ease` applies to the segment that starts at t. */
const K = (kfs) => ({ kf: kfs });
const arr = (v) => (Array.isArray(v) ? v : [v]);
function prop(v) {
  if (v && v.kf) {
    const k = [...v.kf].sort((a, b) => a[0] - b[0]);
    if (k.length === 1) return { a: 0, k: k[0][1] };
    return {
      a: 1,
      k: k.map(([t, val, e = "out"], i) => {
        const key = { t, s: arr(val) };
        if (i < k.length - 1) {
          if (e === "hold") key.h = 1;
          else Object.assign(key, structuredClone(EASE[e]));
        }
        return key;
      }),
    };
  }
  return { a: 0, k: v };
}
/** Colour property: accepts hex or K([[t, hex, ease]]). */
const col = (v) => (v && v.kf ? prop(K(v.kf.map(([t, h, e]) => [t, C(h), e]))) : prop(C(v)));

// ---------------------------------------------------------------- shapes
const rect = (w, h, r = 0, x = 0, y = 0) => ({
  ty: "rc", d: 1, nm: "rect",
  s: w && w.kf ? prop(w) : prop([w, h]),
  p: x && x.kf ? prop(x) : prop([x, y]),
  r: prop(r),
});
const ellipse = (w, h, x = 0, y = 0) => ({ ty: "el", d: 1, nm: "ellipse", s: prop([w, h]), p: prop([x, y]) });
/** path(vertices, closed, inTangents?, outTangents?) */
const path = (v, c = false, ti, to) => ({
  ty: "sh", d: 1, nm: "path",
  ks: { a: 0, k: { c, v, i: ti ?? v.map(() => [0, 0]), o: to ?? v.map(() => [0, 0]) } },
});
const fill = (c, o = 100) => ({ ty: "fl", nm: "fill", c: col(c), o: prop(o), r: 1, bm: 0 });
const stroke = (c, w = 2, { o = 100, dash = null, lc = 2, lj = 2 } = {}) => {
  const s = { ty: "st", nm: "stroke", c: col(c), o: prop(o), w: prop(w), lc, lj, ml: 4, bm: 0 };
  if (dash) s.d = [
    { n: "d", nm: "dash", v: prop(dash[0]) },
    { n: "g", nm: "gap", v: prop(dash[1]) },
    { n: "o", nm: "offset", v: prop(dash[2] ?? 0) },
  ];
  return s;
};
const trim = (e = 100, s = 0) => ({ ty: "tm", nm: "trim", s: prop(s), e: prop(e), o: prop(0), m: 1 });
const tr = ({ p = [0, 0], a = [0, 0], s = [100, 100], r = 0, o = 100 } = {}) => ({
  ty: "tr", nm: "transform", p: prop(p), a: prop(a), s: prop(s), r: prop(r), o: prop(o), sk: prop(0), sa: prop(0),
});
const group = (nm, items, t = {}) => ({ ty: "gr", nm, it: [...items, tr(t)] });

// ---------------------------------------------------------------- layers + comps
function layer(nm, shapes, { p = [0, 0], a = [0, 0], s = [100, 100], o = 100, r = 0 } = {}) {
  return {
    ddd: 0, ty: 4, nm, sr: 1, ao: 0, bm: 0,
    ks: { o: prop(o), r: prop(r), p: prop(p), a: prop(a), s: prop(s) },
    shapes,
  };
}
function finalizeLayers(list, frames) {
  // list is in painter order (bottom first); Lottie wants top first.
  return list.slice().reverse().map((l, i) => ({ ...l, ind: i + 1, ip: 0, op: frames, st: 0 }));
}
function composition(name, w, h, frames, theme, { base, content, fade }) {
  const bg = layer("background", [group("bg", [rect(w, h, 0, w / 2, h / 2), fill(theme.bg)])]);
  const contentLayer = {
    ddd: 0, ty: 0, nm: "content", refId: "content", sr: 1, ao: 0, bm: 0, w, h,
    ks: {
      o: prop(fade ? K([[0, 100], [fade[0], 100, "inOut"], [fade[1], 0]]) : 100),
      r: prop(0), p: prop([w / 2, h / 2]), a: prop([w / 2, h / 2]), s: prop([100, 100]),
    },
  };
  return {
    v: "5.12.2", fr: FPS, ip: 0, op: frames, w, h, nm: name, ddd: 0,
    meta: { g: "SmartSched docs/lottie/build/generate.mjs", a: "SmartSched contributors", d: "Original work, AGPL-3.0 (same as repository)" },
    assets: [{ id: "content", nm: "content", fr: FPS, layers: finalizeLayers(content, frames) }],
    layers: finalizeLayers([bg, ...base, contentLayer], frames),
    markers: [],
  };
}

// ---------------------------------------------------------------- reusable drawings
const bar = (w, h, c, o = 100, x = 0, y = 0) => group("bar", [rect(w, h, h / 2, x, y), fill(c, o)]);

/** Card surface with token elevation: light = soft shadow + 1px border, dark = surface step + ring. */
function cardSurface(T, w, h, r, { fillC = T.raised, borderC = T.border, sizeK = null, radiusK = null, borderW = 1.25 } = {}) {
  const sz = sizeK ?? [w, h];
  const rr = radiusK ?? r;
  const R = (dx = 0, dy = 0) => ({ ty: "rc", d: 1, nm: "rect", s: sizeK ? prop(sizeK) : prop(sz), p: prop([dx, dy]), r: radiusK ? prop(radiusK) : prop(rr) });
  // Lottie paints the first item on top: surface first, shadows underneath.
  const items = [group("surface", [R(), stroke(borderC && borderC.kf ? borderC : (T.ring ?? borderC), borderW), fill(fillC)])];
  if (T.shadow) {
    items.push(group("shadow-near", [R(0, 1.5), fill(T.fg, 7)]));
    items.push(group("shadow-far", [R(0, 5), fill(T.fg, 5)]));
  }
  return items;
}

function checkGlyph(c, w = 2.5, scale = 1, drawK = 100) {
  const p = [[-5, 0.5], [-1.5, 4], [5.5, -3.5]].map(([x, y]) => [x * scale, y * scale]);
  return group("check", [path(p), trim(drawK), stroke(c, w)]);
}
function xGlyph(c, w = 2.5, s = 4.5) {
  return group("x", [path([[-s, -s], [s, s]]), path([[s, -s], [-s, s]]), stroke(c, w)]);
}
function lockGlyph(c) {
  const k = 0.5523 * 3.5;
  return group("lock", [
    group("shackle", [path([[-3.5, -1], [-3.5, -3.5], [0, -7], [3.5, -3.5], [3.5, -1]], false,
      [[0, 0], [0, 0], [-k, 0], [0, -k], [0, 0]], [[0, 0], [0, -k], [k, 0], [0, 0], [0, 0]]), stroke(c, 1.75)]),
    group("body", [rect(11, 8.5, 2, 0, 2.5), fill(c)]),
  ]);
}
function tildeGlyph(c) {
  return group("tilde", [path([[-6, 1.5], [0, 0], [6, -1.5]], false, [[0, 0], [-2.5, -4], [0, 0]], [[2.5, -4], [2.5, 4], [0, 0]]), stroke(c, 2)]);
}
function triangleGlyph(fillC, markC, size = 1) {
  const s = size;
  return group("warning", [
    group("dot", [ellipse(2.6 * s, 2.6 * s, 0, 5.4 * s), fill(markC)]),
    group("mark", [path([[0, -3.5 * s], [0, 2 * s]]), stroke(markC, 2.25 * s)]),
    group("tri", [path([[0, -10 * s], [10.5 * s, 8.5 * s], [-10.5 * s, 8.5 * s]], true), stroke(fillC, 3 * s, { lj: 2 }), fill(fillC)]),
  ]);
}
function octagonGlyph(fillC, markC, r = 12) {
  const pts = [];
  for (let i = 0; i < 8; i++) {
    const a = (Math.PI / 8) + (i * Math.PI) / 4;
    pts.push([+(Math.cos(a) * r).toFixed(2), +(Math.sin(a) * r).toFixed(2)]);
  }
  return group("octagon", [xGlyph(markC, r > 14 ? 3.25 : 2, r * 0.32), group("shape", [path(pts, true), stroke(fillC, 2.5, { lj: 2 }), fill(fillC)])]);
}
function circleCheck(fillC, markC, r, drawK = 100, w = 2.5) {
  return group("circle-check", [checkGlyph(markC, w, r / 11, drawK), group("disc", [ellipse(r * 2, r * 2), fill(fillC)])]);
}
/** "100/100" drawn as strokes. Returns {items, width}. */
function scoreGlyphs(c, x0, h = 16, w = 2.75) {
  const items = [];
  let x = x0;
  const one = () => { items.push(group("1", [path([[x, -h / 2 + 3.5], [x + 4, -h / 2], [x + 4, h / 2]]), stroke(c, w)])); x += 4 + 6; };
  const zero = () => { items.push(group("0", [rect(10, h, 5, x + 5, 0), stroke(c, w)])); x += 10 + 5; };
  const slash = () => { items.push(group("/", [path([[x + 7, -h / 2], [x, h / 2]]), stroke(c, w)])); x += 7 + 6; };
  one(); zero(); zero(); slash(); one(); zero(); zero();
  return { items, width: x - x0 - 5 };
}
const pop = (t, { from = 0, over = 108, dur = 9 } = {}) =>
  K([[t, [from, from], "out"], [t + Math.round(dur * 0.66), [over, over], "inOut"], [t + dur, [100, 100]]]);
const fadeIn = (t, dur = 4, to = 100) => K([[t, 0, "out"], [t + dur, to]]);

// ================================================================= 1. hero-solver (960x540, 6 s)
function heroSolver(T) {
  const W = 960, H = 540, F = 180;
  const base = [], content = [];
  const cardX = 40, cardY = 36, cardW = 880, cardH = 468;
  const gx = 144, gy = 140, cw = 87, ch = 50, gapX = 8, gapY = 8;
  const cellX = (c) => gx + c * (cw + gapX);
  const cellY = (r) => gy + r * (ch + gapY);

  base.push(layer("card", cardSurface(T, cardW, cardH, 16, { fillC: T.shadow ? T.raised : T.surface }), { p: [cardX + cardW / 2, cardY + cardH / 2] }));
  // header: logo tile + title skeleton
  base.push(layer("header", [
    group("logo", [
      ...[[-5, -5], [5, -5], [-5, 5], [5, 5]].map(([x, y], i) => group("dot" + i, [rect(7, 7, 2, x, y), fill(T.primaryFg, i === 3 ? 55 : 100)])),
      group("tile", [rect(34, 34, 9), fill(T.primary)]),
    ], { p: [81, 68] }),
    bar(172, 10, T.fg, 80, 196, 61),
    bar(116, 8, T.fgSubtle, 45, 168, 79),
  ]));
  // column ticks, room labels, empty cells
  const cells = [];
  for (let r = 0; r < 6; r++) for (let c = 0; c < 8; c++) cells.push(group(`cell-${r}-${c}`, [rect(cw, ch, 8, cellX(c) + cw / 2, cellY(r) + ch / 2), fill(T.surface2)]));
  base.push(layer("grid-cells", cells));
  const ticks = [];
  for (let c = 0; c < 8; c++) ticks.push(bar(30, 6, T.fgSubtle, 45, cellX(c) + 22, 126));
  for (let r = 0; r < 6; r++) {
    ticks.push(bar(44, 8, T.fgMuted, 55, 64 + 22, cellY(r) + ch / 2 - 5));
    ticks.push(bar(26, 6, T.fgSubtle, 35, 64 + 13, cellY(r) + ch / 2 + 9));
  }
  base.push(layer("axis-labels", ticks));
  // score placeholder pill + progress track
  const bx = 818, by = 68, bw = 156, bh = 40;
  base.push(layer("score-placeholder", [group("pill", [rect(bw, bh, bh / 2), fill(T.surface2)])], { p: [bx, by] }));
  base.push(layer("progress-track", [group("track", [path([[64, 108], [896, 108]]), stroke(T.track, 4)])]));

  // class blocks: [row, col, span, faculty slot]
  const blocks = [
    [0, 0, 2, 0], [0, 3, 1, 2], [0, 5, 2, 3], [1, 1, 2, 1], [1, 4, 1, 4], [1, 6, 2, 0],
    [2, 0, 1, 6], [2, 2, 2, 2], [2, 5, 1, 7], [2, 7, 1, 5], [3, 0, 2, 3], [3, 3, 1, 5],
    [3, 4, 2, 0], [4, 1, 1, 4], [4, 2, 2, 6], [4, 6, 2, 2], [5, 0, 1, 1], [5, 2, 1, 0],
    [5, 4, 2, 5], [5, 7, 1, 3],
  ];
  const order = [0, 7, 12, 4, 17, 9, 2, 14, 6, 19, 10, 3, 15, 8, 1, 18, 11, 5, 13, 16];
  const START = 14, STAGGER = 3, FLY = 9;
  const blockLayer = (nm, [r, c, span, slot], t0, extra = {}) => {
    const w = span * cw + (span - 1) * gapX;
    const cx = cellX(c) + w / 2, cy = cellY(r) + ch / 2;
    const k = T.cat[slot];
    const tint = mix(T.shadow ? T.raised : T.surface, k, T.tintAmt);
    const strong = mix(k, T.barTo, T.barAmt);
    const dx = extra.dx ?? ((slot % 2 ? 1 : -1) * 26), dy = extra.dy ?? -42;
    const pos = extra.pos ?? K([[t0, [cx + dx, cy + dy], "out"], [t0 + FLY, [cx, cy]]]);
    return layer(nm, [
      bar(Math.min(54, w - 34), 8, strong, 100, -w / 2 + 17 + Math.min(54, w - 34) / 2, -7),
      bar(Math.min(54, w - 34) * 0.6, 6, k, 60, -w / 2 + 17 + Math.min(54, w - 34) * 0.3, 8),
      group("stripe", [rect(4, ch - 18, 2, -w / 2 + 8, 0), fill(k)]),
      group("body", [rect(w, ch, 8), stroke(mix(tint, k, 0.45), 1.25), fill(tint)]),
    ], {
      p: pos,
      o: K([[t0, 0, "out"], [t0 + 4, 100]]),
      s: K([[t0, [90, 90], "out"], [t0 + 6, [103, 103], "inOut"], [t0 + FLY, [100, 100]]]),
    });
  };
  const landings = [];
  order.forEach((bi, i) => {
    const t0 = START + i * STAGGER;
    landings.push(t0 + FLY);
    content.push(blockLayer(`block-${bi}`, blocks[bi], t0));
  });

  // conflict: an orange block lands on row 3 / col 5 (taken), flashes, then slides to col 7
  const tC = START + order.length * STAGGER; // 74
  const land = tC + FLY; // 83
  const slideAt = land + 24; // 107
  const done = slideAt + 9; // 116
  const conflictBlock = [3, 5, 1, 1];
  const fromX = cellX(5) + cw / 2, toX = cellX(7) + cw / 2, cy = cellY(3) + ch / 2;
  const shake = [];
  for (let i = 0; i < 4; i++) shake.push([land + 2 + i * 2, [fromX + (i % 2 ? -4 : 4), cy], "inOut"]);
  content.push(blockLayer("conflict-block", conflictBlock, tC, {
    pos: K([
      [tC, [fromX - 30, cy - 46], "out"], [land, [fromX, cy], "inOut"], ...shake,
      [land + 10, [fromX, cy], "hold"], [slideAt, [fromX, cy], "inOut"], [slideAt + 9, [toX, cy]],
    ]),
  }));
  // conflict overlay: red tint + dashed outline, pulses 3x, each pulse <= 300 ms
  const pulse = K([
    [land, 0, "out"], [land + 3, 100, "inOut"], [land + 8, 45, "inOut"], [land + 13, 100, "inOut"],
    [land + 18, 45, "inOut"], [land + 23, 100, "inOut"], [slideAt + 2, 100, "out"], [slideAt + 8, 0],
  ]);
  content.push(layer("conflict-overlay", [
    group("outline", [rect(cw + 8, ch + 8, 11), stroke(T.infeasible.solid, 2.5, { dash: [7, 5] })]),
    group("tint", [rect(cw, ch, 8), fill(T.infeasible.bg, 55)]),
  ], { p: [fromX, cy], o: pulse }));
  content.push(layer("conflict-badge", [octagonGlyph(T.infeasible.solid, T.infeasible.on, 11)], {
    p: [fromX + cw / 2 - 2, cy - ch / 2 + 2],
    s: K([[land, [0, 0], "out"], [land + 6, [112, 112], "inOut"], [land + 9, [100, 100], "hold"], [slideAt, [100, 100], "inOut"], [slideAt + 6, [0, 0]]]),
  }));
  // drop-ok outline on the free slot
  content.push(layer("drop-ok", [group("outline", [rect(cw + 6, ch + 6, 10), stroke(T.primary, 2), fill(T.primaryTint, 0)])], {
    p: [toX, cy], o: K([[slideAt - 4, 0, "out"], [slideAt + 2, 100, "hold"], [done + 2, 100, "out"], [done + 8, 0]]),
  }));
  content.push(layer("resolved-check", [circleCheck(T.feasible.solid, T.feasible.on, 10, K([[done + 2, 0, "out"], [done + 8, 100]]), 2.25)], {
    p: [toX + cw / 2 - 2, cy - ch / 2 + 2], s: pop(done, { dur: 8 }),
  }));

  // progress: steps up per landing, turns green when the conflict resolves
  const pk = [[0, 0, "hold"], [START, 0, "out"]];
  landings.forEach((t, i) => pk.push([t - 3, ((i + 1) / (order.length + 1)) * 92, "out"]));
  pk.push([land, 92, "hold"], [done, 92, "out"], [done + 8, 100]); // conflict block lands -> 92 %, resolved -> 100 %
  content.push(layer("progress-fill", [group("fill", [path([[64, 108], [896, 108]]), trim(K(pk)),
    stroke(K([[done, T.primary, "inOut"], [done + 6, T.feasible.solid]]), 4)])]));

  // placeholder dots pulse while solving
  const dots = [0, 1, 2].map((i) => {
    const kf = [[0, 0, "hold"], [START - 6, 0, "out"], [START - 2, 35]]; // 0 at frame 0 so the loop seam matches
    for (let t = START + i * 3; t < done; t += 18) kf.push([t, 35, "inOut"], [t + 6, 90, "inOut"], [t + 12, 35]);
    kf.push([done + 6, 35, "out"], [done + 10, 0]);
    return group("dot" + i, [ellipse(7, 7, (i - 1) * 14, 0), fill(T.fgSubtle, K(kf))]);
  });
  content.push(layer("solving-dots", dots, { p: [bx, by] }));

  // 100/100 badge
  const tB = done + 8; // 124
  const g = scoreGlyphs(T.feasible.fg, 0);
  const cr = 13, inner = cr * 2 + 10 + g.width;
  const left = -inner / 2;
  const glyphs = scoreGlyphs(T.feasible.fg, left + cr * 2 + 10).items;
  content.push(layer("score-badge", [
    group("ring", [ellipse(cr * 2, cr * 2, left + cr, 0), stroke(T.feasible.solid, 2)], {
      s: K([[tB + 2, [100, 100], "out"], [tB + 11, [175, 175]]]), o: K([[tB + 2, 70, "out"], [tB + 11, 0]]), p: [left + cr, 0], a: [left + cr, 0],
    }),
    group("text", glyphs),
    group("icon", [circleCheck(T.feasible.solid, T.feasible.on, cr, K([[tB + 3, 0, "out"], [tB + 9, 100]]))], { p: [left + cr, 0] }),
    group("pill", [rect(bw, bh, bh / 2), stroke(T.feasible.border, 2), fill(T.feasible.bg)]),
  ], { p: [bx, by], s: pop(tB), o: K([[tB, 0, "out"], [tB + 3, 100]]) }));

  return composition("hero-solver", W, H, F, T, { base, content, fade: [162, 171] });
}

// ================================================================= shared rule card (720x405 scenes)
const CARD = { w: 290, h: 76, x: 525, ys: [114, 202, 290] };
function chip(T, k, x, y) {
  return group("source-chip", [
    group("dot", [ellipse(8, 8, -14, 0), fill(k)]),
    bar(22, 5, mix(k, T.barTo, T.barAmt), 100, 5, 0),
    group("pill", [rect(52, 20, 10), fill(mix(T.raised, k, T.shadow ? 0.16 : 0.3))]),
  ], { p: [x, y] });
}
/** Dashed placeholders where the rule stack will land (keeps the composition balanced before cards arrive). */
function stackSlots(T, tIn = 2) {
  return layer("stack-slots", CARD.ys.map((y, i) => group("slot" + i, [rect(CARD.w, CARD.h, 14, CARD.x, y), stroke(T.border, 1.5, { dash: [6, 6] }), fill(T.surface, T.shadow ? 100 : 60)], {
    o: K([[tIn + i * 2, 0, "out"], [tIn + i * 2 + 6, 100]]),
  })));
}
function ruleText(T) {
  return [bar(132, 8, T.fg, 75, -145 + 16 + 66, 7), bar(92, 6, T.fgSubtle, 45, -145 + 16 + 46, 22)];
}

// ================================================================= 2. nl-to-rules (720x405, 5 s)
function nlToRules(T) {
  const W = 720, H = 405, F = 150;
  const content = [];
  const bL = 50, bB = 264, bw = 280, bh = 132;
  content.push(stackSlots(T, 6));
  const bubbleFill = T.shadow ? T.surface2 : T.surface2;
  const tExpand = 40, tExp2 = tExpand + 9;
  // avatar
  content.push(layer("avatar", [
    group("head", [ellipse(9, 9, 0, -3), fill(T.fgSubtle, 80)]),
    group("shoulders", [path([[-7, 9], [0, 3], [7, 9]], false, [[0, 0], [-6, 0], [0, 0]], [[0, -5], [6, 0], [0, 0]]), stroke(T.fgSubtle, 2.5, { o: 80 })]),
    group("disc", [ellipse(30, 30), fill(T.surface2), stroke(T.border, 1.25)]),
  ], { p: [64, 294], o: fadeIn(0, 5), s: pop(0, { from: 70, over: 104, dur: 7 }) }));

  // bubble: grows from the typing pill to the full message
  const sK = K([[tExpand, [76, 40], "emph"], [tExp2, [bw, bh]]]);
  const pK = K([[tExpand, [bL + 38, bB - 20], "emph"], [tExp2, [bL + bw / 2, bB - bh / 2]]]);
  const rK = K([[tExpand, 20, "emph"], [tExp2, 18]]);
  const lines = [[220, 158], [190, 190], [150, 222]];
  const tLines = tExp2 - 1;
  const hlCats = [0, 2, 6];
  const tHL = (i) => 64 + i * 14;
  const lineItems = lines.map(([w, y], i) => group("line" + i, [
    path([[bL + 24, y], [bL + 24 + w, y]]), trim(K([[tLines + i * 3, 0, "out"], [tLines + i * 3 + 8, 100]])), stroke(T.fgMuted, 9, { o: 75 }),
  ]));
  const hlItems = lines.map(([w, y], i) => group("highlight" + i, [rect(w + 22, 22, 7, bL + 24 + w / 2, y), fill(T.cat[hlCats[i]], K([[tHL(i), 0, "out"], [tHL(i) + 4, T.shadow ? 22 : 35]]))]));
  const bubbleDim = 116;
  content.push(layer("bubble", [
    ...lineItems,
    ...hlItems,
    group("body", [{ ty: "rc", d: 1, nm: "rect", s: prop(sK), p: prop(pK), r: prop(rK) }, stroke(T.ring ?? T.border, 1.25), fill(bubbleFill)]),
  ], { o: K([[0, 0, "out"], [5, 100, "hold"], [bubbleDim, 100, "out"], [bubbleDim + 6, 55]]), s: pop(0, { from: 80, over: 103, dur: 7 }), p: [bL, bB], a: [bL, bB] }));

  // typing dots
  const dots = [0, 1, 2].map((i) => {
    const kf = [[0, [0, 0]]];
    for (let t = 7 + i * 3; t < tExpand - 6; t += 14) kf.push([t, [0, 0], "inOut"], [t + 4, [0, -5], "inOut"], [t + 8, [0, 0]]);
    return group("dot" + i, [ellipse(8, 8), fill(T.fgSubtle)], { p: K(kf.map(([t, [x, y], e]) => [t, [bL + 24 + i * 14 + x, bB - 20 + y], e])) });
  });
  content.push(layer("typing-dots", dots, { o: K([[4, 0, "out"], [8, 100, "hold"], [tExpand - 2, 100, "out"], [tExpand + 3, 0]]) }));

  // sparkle between bubble and stack
  const st = (r1, r2) => {
    const v = [], ti = [], to = [];
    for (let i = 0; i < 4; i++) {
      const a = (i * Math.PI) / 2 - Math.PI / 2;
      v.push([Math.cos(a) * r1, Math.sin(a) * r1]); ti.push([0, 0]); to.push([0, 0]);
      const b = a + Math.PI / 4;
      v.push([Math.cos(b) * r2, Math.sin(b) * r2]); ti.push([0, 0]); to.push([0, 0]);
    }
    return path(v.map(([x, y]) => [+x.toFixed(2), +y.toFixed(2)]), true, ti, to);
  };
  content.push(layer("sparkle", [group("star", [st(11, 3.2), stroke(T.primary, 1.5, { lj: 2 }), fill(T.primary)]),
    group("star-small", [st(5, 1.6), fill(T.primary, 70)], { p: [10, -12] })], {
    p: [355, 196], s: pop(58, { dur: 8 }), r: K([[58, -30, "out"], [67, 0]]),
    o: K([[58, 0, "out"], [61, 100, "hold"], [bubbleDim, 100, "out"], [bubbleDim + 6, 0]]),
  }));

  // rule cards
  const modes = ["must", "try", "must"];
  CARD.ys.forEach((y, i) => {
    const t0 = tHL(i) + 2, tl = t0 + 9, tt = tl + 4;
    const k = T.cat[hlCats[i]];
    const tx = 93, sx = modes[i] === "must" ? tx - 18 : tx + 18;
    const activeC = modes[i] === "must" ? T.primary : T.warning.solid;
    const activeOn = modes[i] === "must" ? T.primaryFg : T.warning.on;
    const [lw, ly] = lines[i];
    content.push(layer("rule-card-" + i, [
      group("toggle", [
        group("lock-on", [lockGlyph(activeOn)], { p: [tx - 18, 0], o: modes[i] === "must" ? K([[tt + 3, 0, "out"], [tt + 7, 100]]) : 0 }),
        group("tilde-on", [tildeGlyph(activeOn)], { p: [tx + 18, 0], o: modes[i] === "try" ? K([[tt + 3, 0, "out"], [tt + 7, 100]]) : 0 }),
        group("lock", [lockGlyph(T.fgSubtle)], { p: [tx - 18, 0] }),
        group("tilde", [tildeGlyph(T.fgSubtle)], { p: [tx + 18, 0] }),
        group("thumb", [rect(34, 26, 13), fill(activeC)], {
          p: K([[tt, [tx, 0], "out"], [tt + 7, [sx, 0]]]), s: K([[tt, [40, 40], "out"], [tt + 7, [100, 100]]]),
          o: K([[tt, 0, "out"], [tt + 3, 100]]),
        }),
        group("track", [rect(72, 30, 15, tx, 0), fill(T.toggleTrack), stroke(T.border, 1)]),
      ]),
      chip(T, k, -145 + 16 + 26, -16),
      ...ruleText(T),
      ...cardSurface(T, CARD.w, CARD.h, 14),
    ], {
      p: K([[t0, [bL + 24 + lw / 2, ly], "out"], [tl, [CARD.x, y]]]),
      s: K([[t0, [55, 55], "out"], [tl - 2, [102, 102], "inOut"], [tl, [100, 100]]]),
      o: K([[t0, 0, "out"], [t0 + 4, 100]]),
    }));
  });
  return composition("nl-to-rules", W, H, F, T, { base: [], content, fade: [138, 147] });
}

// ================================================================= 3. file-to-rules (720x405, 5 s)
function fileToRules(T) {
  const W = 720, H = 405, F = 150;
  const content = [];
  const zx = 190, zy = 205, zw = 284, zh = 270;
  content.push(stackSlots(T, 4));
  const tDrop = 4, tLand = tDrop + 9;
  const hoverK = (a, b) => K([[tDrop + 4, a, "out"], [tDrop + 9, b, "hold"], [26, b, "out"], [32, a]]);
  content.push(layer("dropzone", [
    group("upload-hint", [
      group("arrow", [path([[0, 10], [0, -10]]), path([[-8, -2], [0, -10], [8, -2]]), stroke(T.fgSubtle, 2.5)], { p: [0, -24] }),
      group("tray", [path([[-16, 2], [-16, 10], [16, 10], [16, 2]]), stroke(T.fgSubtle, 2.5)], { p: [0, -14] }),
      bar(120, 8, T.fgSubtle, 40, 0, 26),
      bar(80, 6, T.fgSubtle, 28, 0, 42),
    ], { o: K([[tDrop + 2, 100, "out"], [tDrop + 8, 0]]) }),
    group("zone", [rect(zw, zh, 16), stroke(hoverK(T.borderStrong, T.primary), 2, { dash: [8, 6] }), fill(hoverK(T.surface, T.primaryTint))]),
  ], { p: [zx, zy], o: fadeIn(0, 4) }));

  // header of the parsed sheet (appears inside the zone)
  content.push(layer("sheet-header", [bar(140, 8, T.fg, 60, 0, -4), bar(90, 6, T.fgSubtle, 40, -25, 10)], { p: [222, 104], o: fadeIn(24, 6) }));

  // rows
  const rowsY = [140, 178, 216, 254, 292], rw = 244, rh = 30;
  const peel = { 0: 0, 2: 1, 3: 2 }; // row -> card index
  const tScan = 36, step = 8;
  const tPeel = (ci) => 82 + ci * 12;
  rowsY.forEach((y, ri) => {
    const tIn = 24 + ri * 2;
    const scanned = tScan + ri * step + 5;
    const ci = peel[ri];
    const rowBars = [bar(40, 6, T.fg, 60, -90, 0), bar(60, 6, T.fgSubtle, 45, -20, 0), bar(50, 6, T.fgSubtle, 45, 60, 0)];
    if (ci === undefined) {
      content.push(layer("row-" + ri, [...rowBars, group("row", [rect(rw, rh, 8), stroke(T.ring ?? T.border, 1.25), fill(T.raised)])], {
        p: K([[tIn, [zx, y + 10], "out"], [tIn + 7, [zx, y]]]),
        o: K([[tIn, 0, "out"], [tIn + 5, 100, "hold"], [118, 100, "out"], [124, 45]]),
      }));
      return;
    }
    const t0 = tPeel(ci), tl = t0 + 12;
    const cy = CARD.ys[ci];
    const sizeK = K([[t0 + 3, [rw, rh], "out"], [tl, [CARD.w, CARD.h]]]);
    const radiusK = K([[t0 + 3, 8, "out"], [tl, 14]]);
    const k = T.cat[2];
    content.push(layer("row-" + ri + "-to-rule", [
      group("rule-content", [
        group("check", [circleCheck(T.feasible.solid, T.feasible.on, 13, K([[tl + 4, 0, "out"], [tl + 10, 100]]))], { p: [115, 0], s: pop(tl + 1, { dur: 8 }) }),
        chip(T, k, -145 + 16 + 26, -16),
        ...ruleText(T),
      ], { o: K([[tl - 3, 0, "out"], [tl + 1, 100]]) }),
      group("row-content", rowBars, { o: K([[t0 + 1, 100, "out"], [t0 + 4, 0]]) }),
      ...cardSurface(T, rw, rh, 8, {
        sizeK, radiusK,
        borderC: K([[scanned - 2, T.ring ?? T.border, "out"], [scanned + 2, T.primary, "hold"], [tl - 2, T.primary, "out"], [tl + 4, T.ring ?? T.border]]),
        fillC: K([[scanned - 2, T.raised, "out"], [scanned + 2, T.primaryTint, "hold"], [tl - 2, T.primaryTint, "out"], [tl + 4, T.raised]]),
      }),
    ], {
      p: K([[tIn, [zx, y + 10], "out"], [tIn + 7, [zx, y], "hold"], [t0, [zx, y], "out"], [t0 + 3, [zx + 4, y - 4], "out"], [tl, [CARD.x, cy]]]),
      s: K([[t0, [100, 100], "out"], [t0 + 3, [103, 103], "out"], [tl - 2, [101, 101], "inOut"], [tl, [100, 100]]]),
      o: K([[tIn, 0, "out"], [tIn + 5, 100]]),
    }));
  });

  // scan line with soft band
  const scanKf = [];
  rowsY.forEach((y, i) => { scanKf.push([tScan + i * step, [zx, y - 19], "inOut"], [tScan + i * step + 6, [zx, y + 19], "hold"]); });
  content.push(layer("scan", [
    group("line", [path([[-132, 0], [132, 0]]), stroke(T.primary, 2.5)]),
    group("band", [rect(264, 22, 4, 0, -11), fill(T.primary, T.shadow ? 10 : 16)]),
  ], { p: K(scanKf), o: K([[tScan - 2, 0, "out"], [tScan + 2, 100, "hold"], [tScan + 4 * step + 6, 100, "out"], [tScan + 4 * step + 12, 0]]) }));

  // the spreadsheet icon: drops in, squashes, then parks in the zone corner
  const sheet = (T) => {
    const g = mix(T.raised, T.feasible.solid, T.shadow ? 0.25 : 0.3);
    const cells = [];
    [-6, 8, 22].forEach((y, r) => [-12, 10].forEach((x, c) => cells.push(group(`c${r}${c}`, [rect(r === 0 ? 20 : 20, 10, 2.5, x, y), fill(r === 0 ? T.feasible.solid : g)]))));
    return [
      ...cells,
      group("fold", [path([[12, -40], [12, -24], [28, -24]]), stroke(T.fgMuted, 2.5)]),
      group("doc", [path([[-28, -40], [12, -40], [28, -24], [28, 40], [-28, 40]], true), stroke(T.fgMuted, 2.5), fill(T.raised)]),
    ];
  };
  content.push(layer("spreadsheet", sheet(T), {
    p: K([[tDrop, [zx, -20], "out"], [tLand, [zx, zy + 34], "hold"], [20, [zx, zy + 34], "emph"], [29, [84, 121]]]),
    s: K([[tLand, [100, 100], "out"], [tLand + 2, [107, 93], "inOut"], [tLand + 6, [100, 100], "hold"], [20, [100, 100], "emph"], [29, [42, 42]]]),
    a: [0, 40],
    o: K([[tDrop, 0, "out"], [tDrop + 3, 100]]),
  }));
  return composition("file-to-rules", W, H, F, T, { base: [], content, fade: [138, 147] });
}

// ================================================================= 4. precheck-fix (720x405, 4 s)
function precheckFix(T) {
  const W = 720, H = 405, F = 120;
  const content = [];
  const gx = 190, gy = 246, R = 118, k = 0.5523 * R;
  const arc = () => path([[-R, 0], [0, -R], [R, 0]], false, [[0, 0], [-k, 0], [0, -k]], [[0, -k], [k, 0], [0, 0]]);
  const fixes = [30, 54, 78];
  const vals = [30, 56, 80, 100];
  const meterK = [[0, 0, "hold"], [4, 0, "out"], [13, vals[0]]];
  fixes.forEach((t, i) => meterK.push([t + 6, vals[i], "out"], [t + 14, vals[i + 1]]));
  const tAmber = fixes[0] + 6, tGreen = fixes[2] + 6;
  const meterC = K([[tAmber, T.infeasible.solid, "inOut"], [tAmber + 6, T.warning.solid, "hold"], [tGreen, T.warning.solid, "inOut"], [tGreen + 6, T.feasible.solid]]);
  const tDone = tGreen + 8;
  content.push(layer("gauge", [
    group("value", [arc(), trim(K(meterK)), stroke(meterC, K([[tDone, 18, "out"], [tDone + 4, 22, "inOut"], [tDone + 9, 18]]))]),
    group("track", [arc(), stroke(T.track, 18)]),
    bar(18, 6, T.fgSubtle, 40, -R, 30), bar(18, 6, T.fgSubtle, 40, R, 30),
  ], { p: [gx, gy], o: fadeIn(0, 5) }));
  // centre status icon morphs x-octagon -> warning -> check
  const swap = (tin, tout) => {
    const kf = [];
    if (tin !== null) kf.push([tin, [0, 0], "out"], [tin + 6, [110, 110], "inOut"], [tin + 9, [100, 100], "hold"]);
    else kf.push([0, [100, 100], "hold"]);
    if (tout !== null) kf.push([tout, [100, 100], "out"], [tout + 5, [0, 0]]);
    return K(kf);
  };
  content.push(layer("status-red", [octagonGlyph(T.infeasible.solid, T.infeasible.on, 22)], { p: [gx, gy - 48], s: swap(null, tAmber), o: fadeIn(0, 5) }));
  content.push(layer("status-amber", [triangleGlyph(T.warning.solid, T.warning.on, 2.1)], { p: [gx, gy - 46], s: swap(tAmber + 2, tGreen) }));
  content.push(layer("status-green", [circleCheck(T.feasible.solid, T.feasible.on, 24, K([[tGreen + 5, 0, "out"], [tGreen + 11, 100]]), 3.25)], { p: [gx, gy - 48], s: swap(tGreen + 2, null) }));
  content.push(layer("score-skeleton", [bar(84, 10, T.fg, 70, 0, 0), bar(124, 6, T.fgSubtle, 40, 0, 18)], { p: [gx, gy + 30], o: fadeIn(2, 5) }));

  // issue list
  const rows = [128, 202, 276], rx = 525, rw = 310, rh = 62;
  rows.forEach((y, i) => {
    const t = fixes[i];
    const tIn = 4 + i * 2;
    content.push(layer("issue-" + i, [
      group("fix-button", [bar(26, 6, T.primaryFg, 100, 0, 0), group("btn", [rect(60, 28, 8), fill(T.primary)])], {
        p: [rw / 2 - 16 - 30, 0],
        s: K([[t, [100, 100], "out"], [t + 3, [90, 90], "inOut"], [t + 6, [100, 100]]]),
        o: K([[t + 5, 100, "out"], [t + 10, 0]]),
      }),
      group("done-bar", [bar(40, 6, T.feasible.fg, 70, 0, 0)], { p: [rw / 2 - 16 - 30, 0], o: K([[t + 8, 0, "out"], [t + 12, 100]]) }),
      group("check", [circleCheck(T.feasible.solid, T.feasible.on, 13, K([[t + 7, 0, "out"], [t + 13, 100]]))], { p: [-rw / 2 + 30, 0], s: K([[t + 4, [0, 0], "out"], [t + 9, [112, 112], "inOut"], [t + 12, [100, 100]]]) }),
      group("warn", [triangleGlyph(T.warning.solid, T.warning.on, 1.05)], { p: [-rw / 2 + 30, 1], s: K([[t + 2, [100, 100], "out"], [t + 6, [0, 0]]]) }),
      bar(112, 8, T.fg, 75, -rw / 2 + 54 + 56, -8),
      bar(78, 6, T.fgSubtle, 45, -rw / 2 + 54 + 39, 10),
      ...cardSurface(T, rw, rh, 12, {
        borderC: K([[t + 4, T.ring ?? T.border, "out"], [t + 10, T.feasible.border]]),
      }),
    ], { p: K([[tIn, [rx + 16, y], "out"], [tIn + 9, [rx, y]]]), o: K([[tIn, 0, "out"], [tIn + 5, 100]]) }));
  });
  return composition("precheck-fix", W, H, F, T, { base: [], content, fade: [104, 113] });
}

// ---------------------------------------------------------------- write
const SCENES = { "hero-solver": heroSolver, "nl-to-rules": nlToRules, "file-to-rules": fileToRules, "precheck-fix": precheckFix };
mkdirSync(OUT, { recursive: true });
for (const [name, fn] of Object.entries(SCENES)) {
  for (const theme of ["light", "dark"]) {
    const json = fn(THEMES[theme]);
    json.nm = `${name}-${theme}`;
    const file = join(OUT, `${name}-${theme}.json`);
    writeFileSync(file, JSON.stringify(json));
    console.log(`${file}  ${json.w}x${json.h}  ${json.op} frames @ ${json.fr} fps`);
  }
}
