// Lossless capture (REC_CAPTURE=screencast): Chrome's own screencast (CDP Page.startScreencast) as PNG frames,
// sent only when the page paints, then laid out on their real timestamps as a lossless constant-rate video.
// Playwright's recordVideo is VP8 and every frame carries a little codec noise (±2-7 levels); an error-diffusion
// GIF palette turns that noise into a dither pattern that changes in every frame, so a GIF of a still screen
// costs as much as a moving one. Here a still screen is the same frame, bit for bit.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { FPS } from "./fps.mjs";

// `scale` (device pixel ratio) asks Chrome for frames at device resolution (the launch video captures at 2x).
// `keep`: the launch renderer's route (scripts/record/launch): stop() keeps the PNG frames and writes
// frames.json instead of encoding a video; a frame identical to the one before is not written again.
export async function startScreencast(page, dir, viewport, { scale = 1, keep = false } = {}) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  const writes = [];
  let stopped = false;
  let lastHash = null;
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    if (stopped) return; // a frame already in flight when the capture stopped
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => undefined);
    if (keep) {
      const hash = createHash("sha1").update(data).digest("hex");
      if (hash === lastHash) {
        frames[frames.length - 1].dup = (frames[frames.length - 1].dup ?? 0) + 1;
        return;
      }
      lastHash = hash;
    }
    const file = join(dir, `f_${String(frames.length).padStart(6, "0")}.png`);
    // the arrival time, not metadata.timestamp: Chrome's frame time stops advancing while the page does not paint
    // (a long upload), which would squeeze a 30 s wait into a second and break the clock mapping
    frames.push({ t: performance.now() / 1000, file, swap: metadata.timestamp });
    writes.push(writeFile(file, Buffer.from(data, "base64")));
  });
  await cdp.send("Page.startScreencast", { format: "png", maxWidth: Math.round(viewport.width * scale), maxHeight: Math.round(viewport.height * scale), everyNthFrame: 1 });
  return {
    frames,
    /** stop and write `out` (lossless RGB H.264 at REC_FPS); returns its path */
    async stop(out) {
      stopped = true;
      await cdp.send("Page.stopScreencast").catch(() => undefined);
      await Promise.all(writes);
      if (frames.length < 2) throw new Error(`screencast captured ${frames.length} frames`);
      if (keep) {
        // Chrome's swap time (metadata.timestamp, epoch seconds) says when a frame was painted; the arrival time adds
        // a PNG-encode/transport delay that grows with the frame size and the host's load. The smallest
        // (arrival - swap) is the clock offset; a frame painted at swap then sits at swap + offset on our clock.
        const lag = frames.filter((f) => f.swap > 0).map((f) => f.t - f.swap);
        const off = lag.length ? Math.min(...lag) : null;
        const out = frames.map((f) => ({ t: +(((off != null && f.swap > 0 ? f.swap + off : f.t) * 1000)).toFixed(1), file: f.file.split("/").pop(), lag: off != null && f.swap > 0 ? +((f.t - f.swap - off) * 1000).toFixed(0) : null }));
        writeFileSync(join(dir, "frames.json"), JSON.stringify({ clock: "performance.now ms", scale, frames: out }));
        return dir;
      }
      const lines = ["ffconcat version 1.0"];
      frames.forEach((f, i) => {
        const next = frames[i + 1];
        lines.push(`file '${f.file}'`, `duration ${Math.max(0.001, (next ? next.t - f.t : 1)).toFixed(6)}`);
      });
      lines.push(`file '${frames[frames.length - 1].file}'`);
      const list = join(dir, "frames.ffconcat");
      writeFileSync(list, lines.join("\n"));
      const r = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list,
        "-vf", `fps=${FPS},format=rgb24`, "-c:v", "libx264rgb", "-preset", "ultrafast", "-qp", "0", out], { stdio: ["ignore", "inherit", "pipe"] });
      if (r.status !== 0) throw new Error(`screencast encode failed: ${r.stderr?.toString().slice(-1500)}`);
      rmSync(dir, { recursive: true, force: true });
      return out;
    },
  };
}
