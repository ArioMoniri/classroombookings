// rows = backgrounds; columns = true-size renders (16, 24, 32) of tile + mark, then 8x zooms of the 16 and 24 px
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(new URL("../../../../smartsched/frontend/package.json", import.meta.url));
const sharp = require("sharp");
const [B, out] = process.argv.slice(2);
const bgs = [["#ffffff", "light"], ["#eef0f4", "light"], ["#f7f8fa", "light"], ["#dee1e6", "light"], ["#0d0e12", "dark"], ["#1b1c21", "dark"], ["#35363a", "dark"]];
const rend = async (f, s) => sharp(fs.readFileSync(f), { density: 72 * s / 192 * 2 }).resize(s, s).png().toBuffer();
const comps = []; let y = 0; const RH = 216;
for (const [bg, th] of bgs) {
  comps.push({ input: { create: { width: 1240, height: RH, channels: 4, background: bg } }, left: 0, top: y });
  let x = 16;
  const items = [];
  for (const s of [16, 24, 32]) items.push([await rend(`${B}/smartsched-tile-small.svg`, s), s]);
  for (const s of [16, 24, 32]) items.push([await rend(`${B}/smartsched-mark-small-${th}.svg`, s), s]);
  for (const [png, s] of items) { comps.push({ input: png, left: x, top: y + 16 }); x += s + 12; }
  x += 16;
  for (const [png, s] of [items[0], items[1], items[3], items[4]]) {
    const z = 8; const big = await sharp(png).resize(s * z, s * z, { kernel: "nearest" }).png().toBuffer();
    comps.push({ input: big, left: x, top: y + 8 }); x += s * z + 16;
  }
  y += RH;
}
await sharp({ create: { width: 1240, height: y, channels: 4, background: "#fff" } }).composite(comps).png().toFile(out);
console.log("wrote", out);
