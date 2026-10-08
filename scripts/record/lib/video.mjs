// Raw-video helpers: constant-frame-rate transcode, sync-flash detection, trim + clock mapping.
import { spawnSync } from "node:child_process";

const FPS = 30;

function ff(args, label) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-y", "-loglevel", "error", ...args], {
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 1 << 30,
  });
  if (r.status !== 0) throw new Error(`ffmpeg ${label} failed:\n${r.stderr?.toString().slice(-2000)}`);
  return r.stdout;
}

/** Playwright's VP8 webm (variable frame timing) → 30 fps H.264 near-lossless intermediate. */
export function toCfr(webm, out) {
  ff(["-i", webm, "-vf", `fps=${FPS}`, "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", out], "cfr");
  return out;
}

/** Every run of magenta sync frames (2×2 RGB averages) → [{startMs, endMs}] on the video clock. */
export function findFlashes(cfr) {
  const buf = ff(["-i", cfr, "-vf", "scale=2:2:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], "scan");
  const frames = buf.length / 12;
  const runs = [];
  let first = -1;
  for (let i = 0; i <= frames; i++) {
    let hits = 0;
    if (i < frames) {
      for (let p = 0; p < 4; p++) {
        const o = i * 12 + p * 3;
        if (buf[o] > 200 && buf[o + 1] < 90 && buf[o + 2] > 200) hits++;
      }
    }
    if (hits === 4 && first < 0) first = i;
    if (hits !== 4 && first >= 0) {
      runs.push({ startMs: (first * 1000) / FPS, endMs: (i * 1000) / FPS });
      first = -1;
    }
  }
  if (!runs.length) throw new Error("sync flash not found in the raw video");
  return { runs, frames };
}

/** The first sync flash (kept for callers of the old API). */
export function findFlash(cfr) {
  const { runs, frames } = findFlashes(cfr);
  return { ...runs[0], frames };
}

/**
 * Map a recorder-clock timeline onto the video and cut the kept range [marks.begin, marks.end], minus the
 * recorder's cuts (time spent waiting, see Recorder.cut). Returns the trimmed timeline (video clock,
 * 0 = first kept frame, cuts removed).
 */
export function trimAndMap(cfr, tl, out) {
  const { runs } = findFlashes(cfr);
  const flash = runs[0];
  const recCuts = tl.cuts ?? [];
  // anchors (recorder ms → video ms): the sync flash, then both marker flashes of every cut
  const anchors = [{ r: tl.marks.sync.start, v: flash.startMs }];
  const vcuts = [];
  if (runs.length - 1 >= recCuts.length * 2) {
    recCuts.forEach((c, i) => {
      const a = runs[1 + 2 * i];
      const b = runs[2 + 2 * i];
      anchors.push({ r: c.flashA.start, v: a.startMs }, { r: c.flashB.end, v: b.endMs });
      vcuts.push({ start: a.startMs, end: b.endMs });
    });
  } else if (recCuts.length) {
    throw new Error(`expected ${recCuts.length * 2} cut marker flashes, found ${runs.length - 1}`);
  }
  /** recorder ms → video ms, piecewise linear between anchors (clock drift under load) */
  const toVideo = (t) => {
    if (t <= anchors[0].r || anchors.length === 1) return t + (anchors[0].v - anchors[0].r);
    for (let i = 1; i < anchors.length; i++) {
      const p = anchors[i - 1];
      const q = anchors[i];
      if (t <= q.r) return p.v + ((t - p.r) * (q.v - p.v)) / Math.max(1, q.r - p.r);
    }
    const l = anchors[anchors.length - 1];
    return t + (l.v - l.r);
  };
  const offset = flash.startMs - tl.marks.sync.start; // video = recorder + offset at the sync flash
  const begin = Math.max(flash.endMs + 34, toVideo(tl.marks.begin));
  const end = toVideo(tl.marks.end);
  // cuts on the trimmed clock (ms from `begin`), sorted, inside the kept range
  const cuts = vcuts
    .map((c) => ({ start: c.start - begin, end: c.end - begin }))
    .filter((c) => c.end > 0 && c.start < end - begin)
    .sort((a, b) => a.start - b.start);
  const sec = (ms) => (ms / 1000).toFixed(3);
  const select = cuts.length
    ? `,select='not(${cuts.map((c) => `between(t,${sec(c.start)},${sec(c.end)})`).join("+")})',setpts=N/${FPS}/TB`
    : "";
  ff(["-ss", sec(begin), "-i", cfr, "-t", sec(end - begin), "-vf", `setpts=PTS-STARTPTS${select}`, "-r", String(FPS),
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", out], "trim");
  const removedBefore = (t) => {
    let removed = 0;
    for (const c of cuts) {
      if (t >= c.end) removed += c.end - c.start;
      else if (t > c.start) return { removed, inside: c };
    }
    return { removed, inside: null };
  };
  const shift = (t0) => {
    const t = toVideo(t0) - begin;
    const { removed, inside } = removedBefore(t);
    return Math.round((inside ? inside.start : t) - removed);
  };
  const steps = tl.steps.map((s) => ({
    ...s,
    startMs: shift(s.startMs),
    endMs: shift(s.endMs),
    targets: s.targets.map((g) => ({ ...g, t: shift(g.t) })),
  }));
  const pointer = tl.pointer.map((p) => ({ ...p, t: shift(p.t) })).filter((p) => p.t >= -2000);
  const cutMs = cuts.reduce((a, c) => a + (Math.min(c.end, end - begin) - Math.max(0, c.start)), 0);
  return {
    ...tl,
    clock: "video",
    sync: { flashStartMs: flash.startMs, flashEndMs: flash.endMs, offsetMs: offset, beginMs: begin, endMs: end, anchors },
    cuts: cuts.map((c) => ({ ...c, removedMs: Math.round(c.end - c.start) })),
    steps,
    pointer,
    durationMs: Math.round(end - begin - cutMs),
  };
}
