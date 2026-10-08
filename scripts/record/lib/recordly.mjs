// Recordly bridge.
// 1. writeProject(): turns a trimmed raw video + timeline into a Recordly project:
//      <video>.cursor.json   cursor telemetry sidecar (Recordly v2 format: normalised cx/cy, clicks)
//      <name>.recordly       project JSON (PROJECT_VERSION 2): videoPath + editor state with zoom
//                            regions (from the same camera shots as the ffmpeg route), captions as
//                            caption cues, and the SmartSched demo preset
//    The project opens in the Recordly editor on any platform for manual fine-tuning.
// 2. exportWithRecordly(): renders that project headlessly through Recordly's own smoke-export mode
//    (RECORDLY_SMOKE_EXPORT=1, present in the packaged v1.4.0 build) under Xvfb with SwiftShader.
//    Verified on Linux x64 with the official AppImage; slow (software WebGL, ~45 s per video second).
// Format sources (webadderallorg/Recordly @ 535d1cf): src/components/video-editor/projectPersistence.ts,
// src/components/video-editor/types.ts, electron/ipc/cursor/telemetry.ts, electron/windows.ts.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { shots } from "./camera.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
export const PRESET_FILE = resolve(HERE, "../../../docs/recording/recordly-preset.json");
const ZOOM_DEPTH_SCALES = { 1: 1.25, 2: 1.5, 3: 1.8, 4: 2.2, 5: 3.5, 6: 5.0 };

export function loadPreset(theme) {
  const p = JSON.parse(readFileSync(PRESET_FILE, "utf8"));
  return { ...p.editor, ...(p.themes?.[theme] ?? {}) };
}

function depthFor(z) {
  let best = 1;
  for (const [d, s] of Object.entries(ZOOM_DEPTH_SCALES)) if (s <= z + 0.05) best = Number(d);
  return best;
}

export function writeProject({ video, tl, outDir, name, theme }) {
  const { width: W, height: H } = tl.viewport;
  const absVideo = resolve(video);
  const samples = tl.pointer
    .filter((p) => p.t >= 0 && p.t <= tl.durationMs)
    .map((p) => ({
      timeMs: Math.round(p.t),
      cx: Math.min(1, Math.max(0, p.x / W)),
      cy: Math.min(1, Math.max(0, p.y / H)),
      interactionType: p.type === "click" ? "click" : p.type === "up" ? "mouseup" : "move",
      cursorType: "arrow",
    }));
  writeFileSync(`${absVideo}.cursor.json`, JSON.stringify({ version: 2, samples }, null, 2));

  const zoomRegions = shots(tl.steps, tl.viewport)
    .map((s, i) => ({
      id: `zoom-${i + 1}`,
      startMs: Math.max(0, Math.round(s.start)),
      endMs: Math.min(tl.durationMs, Math.round(s.end)),
      depth: depthFor(s.z),
      focus: { cx: +(s.cx / W).toFixed(4), cy: +(s.cy / H).toFixed(4) },
      mode: "manual",
    }))
    .filter((z) => z.endMs - z.startMs > 300);
  const autoCaptions = tl.steps
    .filter((s) => s.endMs > 0)
    .map((s, i) => ({ id: `cap-${i + 1}`, startMs: Math.max(0, s.startMs), endMs: Math.min(tl.durationMs, s.endMs), text: s.caption }));
  const preset = loadPreset(theme);
  const project = {
    version: 2,
    videoPath: absVideo,
    editor: {
      ...preset,
      zoomRegions,
      autoCaptions,
      autoCaptionSettings: { ...(preset.autoCaptionSettings ?? {}), enabled: autoCaptions.length > 0 },
      trimRegions: [],
      speedRegions: [],
      annotationRegions: [],
      audioRegions: [],
    },
  };
  const file = join(outDir, `${name}.recordly`);
  writeFileSync(file, JSON.stringify(project, null, 2));
  return { project: file, telemetry: `${absVideo}.cursor.json`, zoomRegions: zoomRegions.length, captions: autoCaptions.length };
}

/** Default location of the extracted AppImage (see docs/recording/RECORDLY.md). */
export function findRecordly() {
  const cands = [process.env.RECORDLY_BIN, join(process.env.REC_TOOLS ?? "", "recordly/squashfs-root/recordly")];
  return cands.find((c) => c && existsSync(c)) ?? null;
}

export function exportWithRecordly({ project, out, bin = findRecordly(), quality = "good", timeoutS = 3600 }) {
  if (!bin) throw new Error("Recordly binary not found: set RECORDLY_BIN to the extracted AppImage's `recordly` executable");
  const env = {
    ...process.env,
    RECORDLY_SMOKE_EXPORT: "1",
    RECORDLY_SMOKE_EXPORT_PROJECT: resolve(project),
    RECORDLY_SMOKE_EXPORT_INPUT: JSON.parse(readFileSync(project, "utf8")).videoPath,
    RECORDLY_SMOKE_EXPORT_OUTPUT: resolve(out),
    RECORDLY_SMOKE_EXPORT_PIPELINE: "legacy", // the "modern" Pixi renderer needs real WebGL/WebGPU
    RECORDLY_SMOKE_EXPORT_RENDER_BACKEND: "webgl",
    RECORDLY_SMOKE_EXPORT_QUALITY: quality,
    RECORDLY_DISABLE_AUTO_UPDATES: "1",
    // Recordly forces --use-gl=egl on X11 sessions, which has no EGL under Xvfb; claiming a Wayland
    // session skips that switch while --ozone-platform=x11 still opens the window on Xvfb
    XDG_SESSION_TYPE: "wayland",
  };
  const args = ["-a", "-s", "-screen 0 1920x1080x24", bin, "--no-sandbox", "--ozone-platform=x11",
    "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
  const r = spawnSync("xvfb-run", args, { env, timeout: timeoutS * 1000, encoding: "utf8", maxBuffer: 1 << 28 });
  const reportFile = `${resolve(out)}.report.json`;
  const report = existsSync(reportFile) ? JSON.parse(readFileSync(reportFile, "utf8")) : null;
  writeFileSync(join(dirname(resolve(out)), `${basename(out)}.recordly.log`), `${r.stdout ?? ""}\n${r.stderr ?? ""}`);
  if (!report?.success) throw new Error(`Recordly export failed: ${report?.error ?? r.error ?? `exit ${r.status}`}`);
  return { out, report };
}
