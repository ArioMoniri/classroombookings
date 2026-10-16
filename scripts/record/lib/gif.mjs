// README GIF clips from the lossless master: one short, focused clip (6-12 s) per `clip` id of a journey.
// Two-pass palette (palettegen stats_mode=diff, paletteuse sierra2_4a + diff_mode=rectangle) on the clean
// master, mpdecimate so frames that did not change cost nothing, still stretches capped at REC_GIF_MAX_HOLD (1.5 s),
// and a size ladder that only narrows the width
// (never below REC_GIF_MIN_WIDTH, never fewer frames per second): a clip that does not fit gets shorter, not uglier.
import { execFileSync, spawnSync } from "node:child_process";
import { statSync } from "node:fs";

function ff(args, label) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-y", "-loglevel", "error", ...args], { stdio: ["ignore", "inherit", "pipe"] });
  if (r.status !== 0) throw new Error(`ffmpeg ${label} failed:\n${r.stderr?.toString().slice(-2000)}`);
}

/** Frame delays of a GIF in 1/100 s: {frames, min, max, irregular (delays that are not a multiple of the base)} */
export function gifTiming(file, fps) {
  const out = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v", "-show_entries", "packet=duration", "-of", "csv=p=0", file]).toString();
  const d = out.split("\n").map(Number).filter((x) => x > 0);
  const base = Math.round(100 / fps);
  return { frames: d.length, min: Math.min(...d), max: Math.max(...d), irregular: d.filter((x) => x % base !== 0).length, seconds: d.reduce((a, b) => a + b, 0) / 100 };
}

export function makeGif({ src, startMs, endMs, out, palette, fps, maxBytes, widths, maxHold = Number(process.env.REC_GIF_MAX_HOLD ?? 1.5) }) {
  const ss = (startMs / 1000).toFixed(3);
  const t = ((endMs - startMs) / 1000).toFixed(3);
  let info = null;
  for (const w of widths) {
    // mpdecimate drops frames that did not change; setpts then caps every still stretch at maxHold seconds (a jump
    // cut of a still screen: waits for the server read as pauses, not as video). The cap is a whole number of
    // frames, so every delay stays a multiple of 1/fps. One cloned frame after the last (tpad) gives that last frame its hold before the loop.
    const cap = Math.round(maxHold * fps) / fps;
    const vf = `fps=${fps},mpdecimate,setpts='if(eq(N\\,0)\\,0\\,PREV_OUTPTS+min(PTS-PREV_INPTS\\,${cap}/TB))',tpad=stop_mode=clone:stop=1,scale=${w}:-2:flags=lanczos`;
    ff(["-ss", ss, "-t", t, "-i", src, "-vf", `${vf},palettegen=max_colors=256:stats_mode=diff`, palette], "palette");
    ff(["-ss", ss, "-t", t, "-i", src, "-i", palette, "-lavfi", `[0:v]${vf}[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle`,
      "-fps_mode", "vfr", "-loop", "0", out], "gif");
    info = { width: w, fps, bytes: statSync(out).size, seconds: Number(t), ...gifTiming(out, fps) };
    if (info.bytes <= maxBytes) return { ...info, fits: true };
  }
  return { ...info, fits: false };
}

/** Clip spans on the video clock from the steps' `clip` ids (consecutive steps with the same id). */
export function clipSpans(steps, durMs, { leadMs = 250, tailMs = 150 } = {}) {
  const spans = [];
  for (const s of steps) {
    if (!s.clip) continue;
    const last = spans[spans.length - 1];
    if (last && last.id === s.clip) last.endMs = s.endMs;
    else spans.push({ id: s.clip, startMs: s.startMs, endMs: s.endMs });
  }
  return spans.map((c) => ({ ...c, startMs: Math.max(0, c.startMs - leadMs), endMs: Math.min(durMs, c.endMs + tailMs) }));
}
