// Camera + cursor maths shared by the ffmpeg compositor and the Recordly project writer.
// All times here are on the VIDEO clock (ms from the first kept frame).

export const DEFAULTS = {
  fps: 30,
  maxZoom: 1.6, // between Recordly depth 2 and 3: text stays sharp on a 1440 px capture
  fill: 0.5, // a click target may fill this share of the frame (width or height)
  minZoom: 1.18, // smaller zooms are not worth the motion: stay on the overview
  leadMs: 550, // the camera starts moving this long before the action
  tailMs: 900, // ... and stays this long after it
  bridgeMs: 1400, // two shots closer than this are connected (pan) instead of zoom-out/zoom-in
  stiffness: 70, // spring (per second²); critically damped → no overshoot
};

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

/** Zoom shots: [{start, end, z, cx, cy}] from the steps' targets. */
export function shots(steps, viewport, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const { width: W, height: H } = viewport;
  const out = [];
  for (const s of steps) {
    if (s.zoom === false) continue;
    const ts = s.targets ?? [];
    ts.forEach((tg, i) => {
      const next = ts[i + 1];
      const z0 = Math.min((W * o.fill) / Math.max(tg.w, 1), (H * o.fill) / Math.max(tg.h, 1));
      const z = clamp(z0, 1, o.maxZoom);
      if (z < o.minZoom) return;
      const start = tg.t - o.leadMs;
      const end = next ? next.t - o.leadMs : s.endMs + o.tailMs;
      out.push({ start, end: Math.max(end, tg.t + o.tailMs), z, cx: tg.x + tg.w / 2, cy: tg.y + tg.h / 2 });
    });
  }
  out.sort((a, b) => a.start - b.start);
  // merge overlaps and bridge short gaps so the camera pans instead of bouncing out and in
  for (let i = 0; i < out.length - 1; i++) {
    if (out[i + 1].start - out[i].end < o.bridgeMs) out[i].end = out[i + 1].start;
  }
  return out;
}

function clampCenter(z, cx, cy, W, H) {
  const hw = W / (2 * z);
  const hh = H / (2 * z);
  return { cx: clamp(cx, hw, W - hw), cy: clamp(cy, hh, H - hh) };
}

/** Per-frame camera [{t, z, cx, cy, x, y, w, h}] (x,y,w,h = source crop rectangle). */
export function cameraTrack(shotList, viewport, durationMs, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const { width: W, height: H } = viewport;
  const dt = 1 / o.fps;
  const k = o.stiffness;
  const c = 2 * Math.sqrt(k); // critical damping
  let state = { lz: 0, cx: W / 2, cy: H / 2 };
  let vel = { lz: 0, cx: 0, cy: 0 };
  const frames = [];
  const n = Math.ceil((durationMs / 1000) * o.fps);
  let si = 0;
  for (let f = 0; f <= n; f++) {
    const t = (f / o.fps) * 1000;
    while (si < shotList.length && shotList[si].end <= t) si++;
    const sh = shotList[si] && shotList[si].start <= t ? shotList[si] : null;
    const target = sh
      ? { lz: Math.log(sh.z), ...clampCenter(sh.z, sh.cx, sh.cy, W, H) }
      : { lz: 0, cx: W / 2, cy: H / 2 };
    for (const key of ["lz", "cx", "cy"]) {
      const a = k * (target[key] - state[key]) - c * vel[key];
      vel[key] += a * dt;
      state[key] += vel[key] * dt;
    }
    const z = Math.max(1, Math.exp(state.lz));
    const { cx, cy } = clampCenter(z, state.cx, state.cy, W, H);
    const w = W / z;
    const h = H / z;
    frames.push({ t, z, cx, cy, x: cx - w / 2, y: cy - h / 2, w, h });
  }
  return frames;
}

/** Pointer position at time t (linear between logged samples). */
export function pointerAt(pointer, t, fallback) {
  if (!pointer.length || t <= pointer[0].t) return pointer[0] ?? fallback;
  let lo = 0;
  let hi = pointer.length - 1;
  if (t >= pointer[hi].t) return pointer[hi];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pointer[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = pointer[lo];
  const b = pointer[hi];
  const u = b.t === a.t ? 1 : (t - a.t) / (b.t - a.t);
  return { x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u };
}

/** Ramer–Douglas–Peucker on (t, v) samples → keyframes reproducing v within eps. */
export function simplify(samples, eps) {
  if (samples.length <= 2) return samples.slice();
  const keep = new Uint8Array(samples.length);
  keep[0] = keep[samples.length - 1] = 1;
  const stack = [[0, samples.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    let best = -1;
    let dmax = 0;
    for (let i = a + 1; i < b; i++) {
      const u = (samples[i].t - samples[a].t) / (samples[b].t - samples[a].t || 1);
      const v = samples[a].v + (samples[b].v - samples[a].v) * u;
      const d = Math.abs(samples[i].v - v);
      if (d > dmax) {
        dmax = d;
        best = i;
      }
    }
    if (dmax > eps && best > 0) {
      keep[best] = 1;
      stack.push([a, best], [best, b]);
    }
  }
  return samples.filter((_, i) => keep[i]);
}

/**
 * ffmpeg expression for a piecewise-linear function of time. `tv` is the time variable as ffmpeg
 * names it in the target filter (overlay: "t", perspective: "(in/30)"). Flat sum of gated segments
 * (not nested if()s) so long tracks do not hit the parser's recursion depth.
 */
export function piecewiseExpr(samples, eps, tv = "t", digits = 2) {
  const k = simplify(samples, eps);
  const r = (x) => Number(x.toFixed(digits));
  if (k.length === 1) return String(r(k[0].v));
  const parts = [];
  parts.push(`lt(${tv},${r(k[0].t)})*${r(k[0].v)}`);
  for (let i = 0; i < k.length - 1; i++) {
    const a = k[i];
    const b = k[i + 1];
    if (b.t - a.t <= 0) continue;
    const slope = (b.v - a.v) / (b.t - a.t);
    const seg =
      Math.abs(slope) < 1e-9 ? `${r(a.v)}` : `(${r(a.v)}+${slope.toFixed(6)}*(${tv}-${r(a.t)}))`;
    parts.push(`gte(${tv},${r(a.t)})*lt(${tv},${r(b.t)})*${seg}`);
  }
  const last = k[k.length - 1];
  parts.push(`gte(${tv},${r(last.t)})*${r(last.v)}`);
  return parts.join("+");
}
