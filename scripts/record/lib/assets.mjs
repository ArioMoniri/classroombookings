// Static overlay assets for the ffmpeg compositor, drawn with ImageMagick (convert): background,
// rounded-corner mask, drop shadow, enlarged cursor, click-ripple frames and caption pills.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

export const THEMES = {
  light: {
    bg: ["#dfe8ff", "#f6e7f7"],
    glow: ["#ffffff", "#c7d7fe"],
    shadowOpacity: 0.28,
    ripple: "#2563eb",
    captionBg: "rgba(15,23,42,0.86)",
    captionFg: "#ffffff",
  },
  dark: {
    bg: ["#0b1020", "#1e1b4b"],
    glow: ["#312e81", "#0f172a"],
    shadowOpacity: 0.6,
    ripple: "#60a5fa",
    captionBg: "rgba(255,255,255,0.92)",
    captionFg: "#0f172a",
  },
};

const FONT_CANDIDATES = [
  "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
];

function im(args) {
  execFileSync("convert", args, { stdio: ["ignore", "ignore", "pipe"] });
}

function font() {
  return process.env.REC_FONT ?? FONT_CANDIDATES.find((f) => existsSync(f)) ?? "DejaVu-Sans";
}

/** layout: {CW, CH, VW, VH, pad, radius} */
export function layoutFor(viewport, { pad = 80, radius = 16 } = {}) {
  const VW = viewport.width;
  const VH = viewport.height;
  const even = (n) => Math.round(n / 2) * 2;
  return { VW, VH, pad, radius, CW: even(VW + 2 * pad), CH: even(VH + 2 * pad) };
}

export function buildAssets(dir, layout, themeName, captions) {
  mkdirSync(dir, { recursive: true });
  const th = THEMES[themeName] ?? THEMES.light;
  const { CW, CH, VW, VH, pad, radius } = layout;
  const out = {};

  out.bg = join(dir, "bg.png");
  im([
    "-size", `${CW}x${CH}`, "-define", "gradient:angle=135", `gradient:${th.bg[0]}-${th.bg[1]}`,
    "(", "-size", `${CW}x${CH}`, "xc:none", "-fill", th.glow[0],
    "-draw", `circle ${Math.round(CW * 0.18)},${Math.round(CH * 0.15)} ${Math.round(CW * 0.18)},${Math.round(CH * 0.62)}`,
    "-fill", th.glow[1],
    "-draw", `circle ${Math.round(CW * 0.86)},${Math.round(CH * 0.9)} ${Math.round(CW * 0.86)},${Math.round(CH * 0.42)}`,
    "-channel", "A", "-evaluate", "multiply", "0.55", "+channel", "-blur", "0x120", ")",
    "-compose", "over", "-composite", "-depth", "8", out.bg,
  ]);

  out.mask = join(dir, "mask.png");
  im(["-size", `${VW}x${VH}`, "xc:black", "-fill", "white",
    "-draw", `roundrectangle 0,0 ${VW - 1},${VH - 1} ${radius},${radius}`, "-depth", "8", out.mask]);

  out.shadow = join(dir, "shadow.png");
  im(["-size", `${CW}x${CH}`, "xc:none", "-fill", `rgba(0,0,0,${th.shadowOpacity})`,
    "-draw", `roundrectangle ${pad},${pad + 14} ${pad + VW},${pad + VH + 14} ${radius},${radius}`,
    "-blur", "0x26", out.shadow]);

  // macOS-like arrow, drawn at 4x and downsampled for clean edges; hotspot = tip
  const S = 4;
  const scale = Number(process.env.REC_CURSOR_SCALE ?? 2.1); // "enlarged": ~2x a normal cursor
  const pts = [[0, 0], [0, 17], [4.2, 13.2], [7, 19.6], [9.7, 18.4], [6.9, 12.2], [12.4, 12.2]];
  const off = 6;
  const poly = pts.map(([x, y]) => `${(x * scale + off) * S},${(y * scale + off) * S}`).join(" ");
  const size = Math.ceil((13 * scale + 2 * off) * S);
  const sizeH = Math.ceil((20 * scale + 2 * off) * S);
  out.cursor = join(dir, "cursor.png");
  im([
    "-size", `${size}x${sizeH}`, "xc:none",
    "(", "-size", `${size}x${sizeH}`, "xc:none", "-fill", "rgba(0,0,0,0.45)", "-draw", `polygon ${poly}`,
    "-blur", `0x${2.2 * S}`, "-geometry", `+0+${1.5 * S}`, ")", "-compose", "over", "-composite",
    "-fill", "white", "-stroke", "black", "-strokewidth", String(1.15 * S * (scale / 2)),
    "-draw", `polygon ${poly}`, "-resize", "25%", out.cursor,
  ]);
  out.cursorHotspot = { x: off, y: off };

  // click ripple: 18 frames (600 ms @ 30 fps)
  const R = 64;
  out.rippleDir = join(dir, "ripple");
  mkdirSync(out.rippleDir, { recursive: true });
  for (let i = 0; i < 18; i++) {
    const u = i / 17;
    const e = 1 - Math.pow(1 - u, 3);
    const r = (8 + 46 * e) * 2;
    const a = (0.9 * (1 - u)).toFixed(3);
    const fillA = (0.22 * (1 - u)).toFixed(3);
    const c = R * 2;
    im([
      "-size", `${R * 4}x${R * 4}`, "xc:none",
      "-fill", hexA(th.ripple, fillA), "-stroke", hexA(th.ripple, a), "-strokewidth", String(Math.max(2, 7 * (1 - u)) * 2),
      "-draw", `circle ${c},${c} ${c + r},${c}`, "-resize", "50%",
      join(out.rippleDir, `r_${String(i).padStart(2, "0")}.png`),
    ]);
  }
  out.rippleSize = R * 2;

  out.captions = captions.map((text, i) => {
    const p = join(dir, `caption_${String(i).padStart(2, "0")}.png`);
    const textPng = join(dir, `caption_${i}_text.png`);
    im(["-background", "none", "-fill", th.captionFg, "-font", font(), "-pointsize", "52",
      `label:${text.startsWith("@") ? ` ${text}` : text}`, "-resize", "50%", textPng]);
    const [tw, tH] = execFileSync("identify", ["-format", "%w %h", textPng]).toString().trim().split(" ").map(Number);
    const w = tw + 44;
    const h = tH + 22;
    im(["-size", `${w}x${h}`, "xc:none", "-fill", th.captionBg,
      "-draw", `roundrectangle 0,0 ${w - 1},${h - 1} ${h / 2},${h / 2}`,
      textPng, "-gravity", "center", "-compose", "over", "-composite", p]);
    return { path: p, w, h };
  });
  return out;
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
