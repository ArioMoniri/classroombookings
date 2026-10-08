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

/** Frames (2×2 RGB averages) where the magenta sync flash is visible → [startMs, endMs] video clock. */
export function findFlash(cfr) {
  const buf = ff(["-i", cfr, "-vf", "scale=2:2:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], "scan");
  const frames = buf.length / 12;
  let first = -1;
  let lastF = -1;
  for (let i = 0; i < frames; i++) {
    let hits = 0;
    for (let p = 0; p < 4; p++) {
      const o = i * 12 + p * 3;
      if (buf[o] > 200 && buf[o + 1] < 90 && buf[o + 2] > 200) hits++;
    }
    if (hits === 4) {
      if (first < 0) first = i;
      lastF = i;
    } else if (first >= 0) break;
  }
  if (first < 0) throw new Error("sync flash not found in the raw video");
  return { startMs: (first * 1000) / FPS, endMs: ((lastF + 1) * 1000) / FPS, frames };
}

/**
 * Map a recorder-clock timeline onto the video and cut the kept range [marks.begin, marks.end].
 * Returns the trimmed timeline (video clock, 0 = first kept frame).
 */
export function trimAndMap(cfr, tl, out) {
  const flash = findFlash(cfr);
  const offset = flash.startMs - tl.marks.sync.start; // video = recorder + offset
  const begin = Math.max(flash.endMs + 34, tl.marks.begin + offset);
  const end = tl.marks.end + offset;
  ff(["-ss", (begin / 1000).toFixed(3), "-i", cfr, "-t", ((end - begin) / 1000).toFixed(3), "-c:v", "libx264",
    "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", out], "trim");
  const shift = (t) => Math.round(t + offset - begin);
  const steps = tl.steps.map((s) => ({
    ...s,
    startMs: shift(s.startMs),
    endMs: shift(s.endMs),
    targets: s.targets.map((g) => ({ ...g, t: shift(g.t) })),
  }));
  const pointer = tl.pointer.map((p) => ({ ...p, t: shift(p.t) })).filter((p) => p.t >= -2000);
  return {
    ...tl,
    clock: "video",
    sync: { flashStartMs: flash.startMs, flashEndMs: flash.endMs, offsetMs: offset, beginMs: begin, endMs: end },
    steps,
    pointer,
    durationMs: Math.round(end - begin),
  };
}
