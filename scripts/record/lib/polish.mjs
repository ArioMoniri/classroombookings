// ffmpeg compositor: raw Playwright video + timeline → a lossless master, then a Recordly-style MP4, the README GIF
// clips (REC_GIF=1; one per `clip` id of the journey, lib/gif.mjs), a poster and, with REC_WEBP=1, an animated WebP.
//   camera   (own ffmpeg pass) perspective filter in "source" mode = sub-pixel crop that follows a spring-smoothed
//            camera track (no zoompan jitter), sampled per frame and compressed to piecewise-linear
//            expressions
//   frame    rounded corners (alphamerge with a mask), blurred drop shadow, soft gradient background
//   cursor   enlarged arrow overlaid from the logged pointer track (camera-transformed), click ripple
//   captions one pill per step, faded in/out
import { execFileSync, spawnSync } from "node:child_process";
import { readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { buildAssets, layoutFor } from "./assets.mjs";
import { cameraTrack, piecewiseExpr, pointerAt, shots } from "./camera.mjs";
import { FPS } from "./fps.mjs";
import { clipSpans, makeGif } from "./gif.mjs";

function ff(args, label) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-y", "-loglevel", "error", ...args], { stdio: ["ignore", "inherit", "pipe"] });
  if (r.status !== 0) throw new Error(`ffmpeg ${label} failed:\n${r.stderr?.toString().slice(-3000)}`);
}

export function probeDuration(file) {
  return Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim());
}

/**
 * @param {object} p
 * @param {string} p.raw      CFR mp4 already trimmed to the kept range (video clock starts at 0)
 * @param {object} p.tl       timeline on the video clock (steps/pointer in ms from the first frame)
 * @param {string} p.outDir
 * @param {string} p.name     base file name
 * @param {"light"|"dark"} p.theme
 */
export function polish({ raw, tl, outDir, name, theme, gifMaxBytes = Number(process.env.REC_GIF_MAX_BYTES ?? 9_000_000), captions = true, cameraOpts = {} }) {
  const viewport = tl.viewport;
  const { width: W, height: H } = viewport;
  const durMs = Math.floor(probeDuration(raw) * 1000);
  const durS = (durMs / 1000).toFixed(3);
  const layout = layoutFor(viewport);
  const { CW, CH, VW, VH, pad } = layout;
  const steps = tl.steps.filter((s) => s.endMs > 0 && s.startMs < durMs);
  const assets = buildAssets(join(outDir, `${name}.assets`), layout, theme, captions ? steps.map((s) => s.caption) : []);

  // ---- camera ----------------------------------------------------------------------------------
  const cam = cameraTrack(shots(steps, viewport, cameraOpts), viewport, durMs, { fps: FPS, ...cameraOpts });
  const tvP = `(in/${FPS})`;
  const series = (fn) => cam.map((f) => ({ t: f.t / 1000, v: fn(f) }));
  const ex = (fn, eps = 0.15) => piecewiseExpr(series(fn), eps, tvP, 3);
  // perspective sense=source: the 4 source corners mapped onto the output corners
  const persp = [
    ex((f) => f.x), ex((f) => f.y),
    ex((f) => f.x + f.w), ex((f) => f.y),
    ex((f) => f.x), ex((f) => f.y + f.h),
    ex((f) => f.x + f.w), ex((f) => f.y + f.h),
  ];
  const zoomed = cam.some((f) => f.z > 1.001);

  // ---- cursor in output coordinates ------------------------------------------------------------
  const sx = VW / W;
  const sy = VH / H;
  const fallback = { x: W * 0.62, y: H * 0.72 };
  const cur = cam.map((f) => {
    const p = pointerAt(tl.pointer, f.t, fallback);
    return { t: f.t / 1000, x: pad + (p.x - f.x) * f.z * sx, y: pad + (p.y - f.y) * f.z * sy };
  });
  const hx = assets.cursorHotspot.x;
  const hy = assets.cursorHotspot.y;
  const curX = piecewiseExpr(cur.map((c) => ({ t: c.t, v: c.x - hx })), 0.4, "t", 3);
  const curY = piecewiseExpr(cur.map((c) => ({ t: c.t, v: c.y - hy })), 0.4, "t", 3);

  // ---- pass 1: camera ---------------------------------------------------------------------------
  // A separate pass on purpose: inside the big overlay graph below, ffmpeg 6.1's perspective filter
  // sees a different `in` frame counter than the frames it is given (camera drifted seconds away
  // from the content); alone it is exact.
  const camFile = join(outDir, `${name}.camera.mp4`);
  const cameraF = zoomed
    ? `perspective=x0='${persp[0]}':y0='${persp[1]}':x1='${persp[2]}':y1='${persp[3]}':x2='${persp[4]}':y2='${persp[5]}':x3='${persp[6]}':y3='${persp[7]}':sense=source:interpolation=cubic:eval=frame,`
    : "";
  const camScript = join(outDir, `${name}.camera.filter.txt`);
  const lossless = process.env.REC_LOSSLESS === "1";
  writeFileSync(camScript, `[0:v]fps=${FPS},${cameraF}scale=${VW}:${VH}:flags=lanczos,format=${lossless ? "rgb24" : "yuv420p"}[cam]`);
  ff(["-i", raw, "-filter_complex_script", camScript, "-map", "[cam]", ...(lossless ? ["-c:v", "libx264rgb", "-preset", "ultrafast", "-qp", "0"] : ["-c:v", "libx264", "-preset", "veryfast", "-crf", "12"]), camFile], "camera");

  // ---- inputs ----------------------------------------------------------------------------------
  const inputs = ["-i", camFile];
  const still = (file) => inputs.push("-loop", "1", "-framerate", String(FPS), "-t", durS, "-i", file);
  still(assets.bg); // 1
  still(assets.mask); // 2
  still(assets.shadow); // 3
  still(assets.cursor); // 4
  let idx = 5;
  const capIdx = [];
  if (captions) {
    steps.forEach((s, i) => {
      const len = Math.max(0.6, (Math.min(s.endMs, durMs) - Math.max(0, s.startMs)) / 1000);
      inputs.push("-loop", "1", "-framerate", String(FPS), "-t", len.toFixed(3), "-i", assets.captions[i].path);
      capIdx.push({ idx: idx++, start: Math.max(0, s.startMs) / 1000, len, ...assets.captions[i] });
    });
  }
  const clicks = tl.pointer.filter((p) => p.type === "click" && p.t >= 0 && p.t < durMs - 200);
  const ripIdx = [];
  for (const c of clicks) {
    inputs.push("-framerate", String(FPS), "-i", join(assets.rippleDir, "r_%02d.png"));
    ripIdx.push({ idx: idx++, t: c.t / 1000 });
  }

  // ---- filter graph ----------------------------------------------------------------------------
  const g = [];
  g.push(`[0:v]format=rgba[cam]`);
  g.push(`[2:v]format=gray[mask]`);
  g.push(`[cam][mask]alphamerge[card]`);
  g.push(`[1:v]format=rgba[bg]`);
  g.push(`[bg][3:v]overlay=0:0[bgs]`);
  g.push(`[bgs][card]overlay=${pad}:${pad}:shortest=1[v0]`);
  let last = "v0";
  let n = 1;
  const rs = assets.rippleSize;
  for (const r of ripIdx) {
    g.push(`[${r.idx}:v]format=rgba,tpad=start_duration=${r.t.toFixed(3)}:color=0x00000000[rp${n}]`);
    g.push(`[${last}][rp${n}]overlay=x='${curX}+${hx}-${rs / 2}':y='${curY}+${hy}-${rs / 2}':eof_action=pass:eval=frame[v${n}]`);
    last = `v${n++}`;
  }
  g.push(`[${last}][4:v]overlay=x='${curX}':y='${curY}':eval=frame:shortest=1[v${n}]`);
  last = `v${n++}`;
  for (const c of capIdx) {
    const fo = Math.max(0, c.len - 0.25).toFixed(3);
    g.push(`[${c.idx}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st=${fo}:d=0.25:alpha=1,tpad=start_duration=${c.start.toFixed(3)}:color=0x00000000[cp${n}]`);
    const x = Math.round((CW - c.w) / 2);
    const y = Math.round(CH - pad - c.h - 22);
    g.push(`[${last}][cp${n}]overlay=${x}:${y}:eof_action=pass[v${n}]`);
    last = `v${n++}`;
  }
  g.push(`[${last}]format=rgb24[out]`);
  const script = join(outDir, `${name}.filter.txt`);
  writeFileSync(script, g.join(";\n"));

  // lossless RGB master: the GIF clips are cut from it, so a frame that did not change is bit-identical to the
  // one before (mpdecimate drops it, diff_mode=rectangle redraws only what moved)
  const master = join(outDir, `${name}.master.mkv`);
  ff([...inputs, "-filter_complex_script", script, "-map", "[out]", "-t", durS, "-r", String(FPS), "-c:v", "libx264rgb",
    "-preset", "ultrafast", "-qp", "0", "-an", master], "compose");
  const mp4 = join(outDir, `${name}.mp4`);
  ff(["-i", master, "-c:v", "libx264", "-preset", process.env.REC_X264_PRESET ?? "medium", "-crf", process.env.REC_CRF ?? "18",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4], "mp4");

  // ---- poster: middle of the step marked poster, else 60 % in --------------------------------
  const ps = steps.find((s) => s.poster) ?? null;
  const posterT = ps ? (ps.startMs + ps.endMs) / 2000 : (durMs / 1000) * 0.6;
  const poster = join(outDir, `${name}.poster.png`);
  ff(["-ss", posterT.toFixed(2), "-i", mp4, "-frames:v", "1", poster], "poster");

  // ---- animated WebP for the README under the size budget: shrink quality, width, then fps -----
  const webp = join(outDir, `${name}.webp`);
  let webpInfo = null;
  const webpMax = Number(process.env.REC_WEBP_MAX_BYTES ?? 3_900_000);
  for (const [w, fps, q] of process.env.REC_WEBP === "1" ? [[1000, 15, 72], [1000, 12, 62], [920, 12, 55], [840, 10, 50], [760, 10, 45], [680, 8, 40]] : []) {
    ff(["-i", mp4, "-vf", `fps=${fps},scale=${w}:-2:flags=lanczos`, "-c:v", "libwebp_anim", "-lossless", "0",
      "-quality", String(q), "-compression_level", "6", "-preset", "picture", "-loop", "0", "-an", webp], "webp");
    const size = statSync(webp).size;
    webpInfo = { width: w, fps, quality: q, bytes: size };
    if (size <= webpMax) break;
  }

  // ---- GIF clips (REC_GIF=1): one per `clip` id; a journey without clips gives one GIF of the whole take ----
  const gifs = [];
  if (process.env.REC_GIF === "1") {
    // REC_GIF_CLIPS (record-all.sh: the README set) limits the encoding to the clips that are published
    const wanted = process.env.REC_GIF_CLIPS ? new Set(process.env.REC_GIF_CLIPS.split(/\s+/).filter(Boolean)) : null;
    const spans = clipSpans(steps, durMs).filter((c) => !wanted || wanted.has(c.id));
    if (!spans.length && !wanted) spans.push({ id: tl.journey?.id ?? name, startMs: 0, endMs: durMs });
    const widths = (process.env.REC_GIF_WIDTHS ?? "1200,1120,1040").split(",").map(Number);
    for (const c of spans) {
      const out = join(outDir, `${name}.${c.id}.gif`);
      const info = makeGif({ src: master, startMs: c.startMs, endMs: c.endMs, out, palette: join(outDir, `${name}.palette.png`), fps: FPS, maxBytes: gifMaxBytes, widths });
      gifs.push({ id: c.id, file: out, startMs: c.startMs, endMs: c.endMs, ...info });
    }
  }
  rmSync(camFile, { force: true });
  if (!process.env.REC_KEEP_MASTER) rmSync(master, { force: true });
  return { mp4, gifs, webp: webpInfo ? webp : null, webpInfo, poster, durationMs: durMs, layout, filterScript: script, clicks: clicks.length, zoomed };
}

export function listOutputs(dir) {
  return readdirSync(dir).filter((f) => /\.(mp4|gif|png|json|recordly)$/.test(f));
}
