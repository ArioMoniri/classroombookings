// usage: node export.mjs <brandDir> <publicDir>
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(new URL("../../../../smartsched/frontend/package.json", import.meta.url));
const sharp = require("sharp");
const [B, P] = process.argv.slice(2);
fs.mkdirSync(`${B}/png`, { recursive: true }); fs.mkdirSync(`${P}/icons`, { recursive: true });
async function render(src, out, { w, h, flatten, palette } = {}) {
  const svg = fs.readFileSync(src); const m = await sharp(svg).metadata();
  const scale = h ? h / m.height : w / m.width;
  let img = sharp(svg, { density: Math.min(72 * scale * 1.0001, 4800) }).resize(w ? { width: w } : { height: h });
  if (flatten) img = img.flatten({ background: flatten });
  await img.png(palette ? { palette: true, quality: 95, compressionLevel: 9, effort: 10 } : { compressionLevel: 9 }).toFile(out);
  console.log(String(fs.statSync(out).size).padStart(7), out);
}
// favicons and app icons
await render(`${B}/smartsched-tile-small.svg`, `${P}/icons/icon-16.png`, { w: 16 });
await render(`${B}/smartsched-tile-small.svg`, `${P}/icons/icon-32.png`, { w: 32 });
await render(`${B}/smartsched-tile-small.svg`, `${P}/icons/icon-48.png`, { w: 48 });
await render(`${B}/smartsched-tile.svg`, `${P}/icons/icon-192.png`, { w: 192 });
await render(`${B}/smartsched-tile.svg`, `${P}/icons/icon-512.png`, { w: 512 });
await render(`${B}/smartsched-tile-maskable.svg`, `${P}/icons/icon-maskable-512.png`, { w: 512 });
await render(`${B}/smartsched-tile-maskable.svg`, `${P}/apple-touch-icon.png`, { w: 180, flatten: "#0A63D1" });
// brand PNG exports
for (const t of ["light", "dark", "mono-black", "mono-white"]) {
  await render(`${B}/smartsched-lockup-${t}.svg`, `${B}/png/smartsched-lockup-${t}.png`, { h: 192 });
  await render(`${B}/smartsched-mark-${t}.svg`, `${B}/png/smartsched-mark-${t}-512.png`, { w: 512 });
}
await render(`${B}/smartsched-tile.svg`, `${B}/png/smartsched-tile-512.png`, { w: 512 });
for (const t of ["light", "dark"]) await render(`${B}/readme-header-${t}.svg`, `${B}/readme-header-${t}.png`, { w: 1280, palette: true });
