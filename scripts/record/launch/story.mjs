// The launch video's edit: which takes, which steps of each, in what layout, with which titles. render.mjs turns
// this into frames; launch.sh records the takes it names (TAKES) and encodes the deliverables.
//
// A scene: { id, kind: intro|chapter|take|outro, durMs (intro/chapter/outro), chapter: {n, label},
//   views: [{ take, steps: [first, last], trim: [{step, keepMs}], speed, camera }] (take scenes), layout,
//   captions: {stepIndex: "text"} (override a step's caption) }
// and render(ctx) → compositor layers for one output frame. Captions are English (README language); the UI is
// recorded in the language set by LAUNCH_UI_LANG (default en). Licence: same as the repository.
import { pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const brand = (f) => pathToFileURL(resolve(REPO, "docs/images/brand", f)).href;
export const BRAND = { lockup: brand("smartsched-lockup-light.svg"), mark: brand("smartsched-mark-light.svg"), repo: "github.com/ArioMoniri/classroombookings" };

/** The takes launch.sh records (record.mjs --engine frames): name = journey id + device suffix. */
export const TAKES = [
  { journey: "launch-import", device: "desktop" },
  { journey: "launch-run", device: "desktop" },
  { journey: "launch-reserve", device: "phone" },
  { journey: "approval-flow", device: "desktop" },
  { journey: "launch-admin", device: "desktop" },
];
export const takeName = (t, theme = "light", lang = process.env.LAUNCH_UI_LANG ?? "en") =>
  `${t.journey}-${theme}${lang === "en" ? "" : `-${lang}`}${t.device === "phone" ? "-phone" : ""}`;

// ---- geometry per format ---------------------------------------------------------------------------------------
const GEO = {
  landscape: {
    card: { x: 192, y: 92, w: 1536, h: 864 },
    capY: 980, capFont: 28, chipX: 192, chipY: 30, chipFont: 22,
    phone: { x: 1188, y: 150, w: 400 * 1.0, h: 844 * (400 / 390) },
    phoneText: { x: 190, y: 330, w: 820 },
    split: { card: { x: 96, y: 200, w: 1216, h: 684 }, phone: { x: 1430, y: 160, w: 390, h: 844 } },
    lottie: { x: 880, y: 260, w: 896, h: 504 }, chapterText: { x: 150, y: 400, w: 680 },
  },
  vertical: {
    card: { x: 40, y: 560, w: 1000, h: 800 },
    capY: 1440, capFont: 32, capWrap: true, capW: 940, chipX: 40, chipY: 120, chipFont: 28,
    phone: { x: 214, y: 300, w: 652, h: 844 * (652 / 390) },
    phoneCapY: 1760,
    split: null,
    lottie: { x: 40, y: 760, w: 1000, h: 562 }, chapterText: { x: 60, y: 330, w: 960 },
  },
  // README feature clips: one take, the card fills the frame, the caption under it
  clip: { size: [1600, 960], card: { x: 80, y: 32, w: 1440, h: 810 }, capY: 868, capFont: 30, chipX: 100, chipY: 52, chipFont: 22 },
  // phone clips: the phone in its frame, the caption under it
  "phone-clip": { size: [720, 1280], phone: { x: 120, y: 92, w: 480, h: 844 * (480 / 390) }, phoneCapY: 1188, capFont: 24, capWrap: true, capW: 660, chipX: 24, chipY: 20, chipFont: 18 },
};
GEO.landscape.size = [1920, 1080];
GEO.vertical.size = [1080, 1920];

const FEATURES = ["CP-SAT timetables", "Exam planning", "Run reports", "Room booking", "Approvals", "Calendar sync", "AI with guardrails", "Turkish + English"];
const layer = (L, tf, alpha) => ({ ...L, transform: tf, opacity: alpha });
const html = (cls, h, style) => ({ kind: "html", cls, html: h, style });

function titleBlock(x, y, w, title, sub, size, a) {
  return html("title", `${title}<small style="font-size:${Math.round(size * 0.45)}px;margin-top:${Math.round(size * 0.35)}px">${sub}</small>`,
    { left: `${x}px`, top: `${y}px`, width: `${w}px`, fontSize: `${size}px`, opacity: String(a) });
}

function takeScene(def, fmt) {
  const g = GEO[fmt];
  return {
    ...def,
    kind: "take",
    render(c) {
      const out = [];
      const layout = def.layout ?? "desktop";
      if (layout === "desktop") {
        const p = c.parts?.[0] ?? this.parts[0];
        const v = c.viewState(p, c.local, g.card, "screen");
        out.push(layer(v.L, c.tf, c.alpha));
        c.preload.push(...v.nexts);
        const cap = c.captionFor(this, p, v.recT);
        if (cap) { c.caps.push(cap); out.push(c.captionLayer(cap, c.alpha, g)); }
        const k = c.keysFor(p, v.recT);
        if (k) out.push(html("keys", k.html, { left: `${g.card.x + 28}px`, top: `${g.card.y + g.card.h - 76}px`, opacity: String(k.a * c.alpha) }));
      } else if (layout === "phone") {
        const p = this.parts[0];
        const box = { ...g.phone };
        const v = c.viewState(p, c.local, box, "phone");
        out.push(layer(v.L, c.tf, c.alpha));
        c.preload.push(...v.nexts);
        const cap = c.captionFor(this, p, v.recT);
        if (fmt === "landscape") {
          const t = g.phoneText;
          out.push(titleBlock(t.x, t.y, t.w, def.headline, def.subline, 64, c.alpha));
          if (cap) {
            c.caps.push(cap);
            out.push({ ...c.captionLayer(cap, c.alpha, g), style: { ...c.captionLayer(cap, c.alpha, g).style, left: `${t.x}px`, transform: "none", top: `${t.y + 260}px` } });
          }
        } else if (cap) {
          c.caps.push(cap);
          out.push(c.captionLayer(cap, c.alpha, { ...g, capY: g.phoneCapY, capWrap: true, capW: g.capW ?? 940 }));
        }
      }
      const chip = c.chipLayer(this, c.alpha, g);
      if (chip) out.push(chip);
      return out;
    },
  };
}

/** A README clip: one take (or a step range of it), no intro; `format` clip (desktop) or phone-clip. */
function buildClip({ format, take, steps, title }) {
  const phone = format === "phone-clip";
  return {
    size: GEO[format].size,
    crossfadeMs: 0,
    lotties: [],
    scenes: [{ ...takeScene({ id: "clip", layout: phone ? "phone" : "desktop", chapter: title ? { n: "▶", label: title } : null, views: [{ take, steps, leadMs: 500, tailMs: 300 }] }, format), overlapNext: false }],
    camera: {
      desktop: { maxZoom: 1.5, minZoom: 1.12, stiffness: 90, bridgeMs: 1600, leadMs: 600, tailMs: 900, fill: 0.7 },
      phone: { zoom: false },
    },
  };
}

export function buildStory({ format = "landscape", story = "launch", take, steps, title } = {}) {
  if (story === "clip") return buildClip({ format, take, steps, title });
  const g = GEO[format];
  const T = Object.fromEntries(TAKES.map((t) => [t.journey, takeName(t)]));
  const lottieFrames = { "hero-solver": 180, "file-to-rules": 150, "nl-to-rules": 150, "precheck-fix": 120 };
  const chapter = (id, name, n, label, title, sub, durMs = 2600) => ({
    id, kind: "chapter", durMs, chapter: { n, label },
    render(c) {
      const fr = Math.min(lottieFrames[name] - 1, (c.local / 1000) * 30 * (lottieFrames[name] / 30 / (durMs / 1000 + 0.6)));
      const a = c.alpha;
      const t = g.chapterText;
      const lift = (1 - c.easeOut(c.local / 600)) * 24;
      return [
        { kind: "lottie", name, frame: fr, box: g.lottie, opacity: a, transform: `translateY(${lift.toFixed(1)}px) ${c.tf}` },
        titleBlock(t.x, t.y + lift, t.w, title, sub, format === "vertical" ? 72 : 60, a),
        c.chipLayer(this, a, g),
      ];
    },
  });
  const scenes = [
    {
      id: "intro", kind: "intro", durMs: 4600,
      render(c) {
        const a = c.alpha;
        const u = c.local / 1000;
        const fr = Math.min(179, u * 30 * 1.35);
        const logoA = c.easeOut((u - 0.15) / 0.6) * a;
        const tagA = c.easeOut((u - 0.9) / 0.7) * a;
        const L = format === "vertical"
          ? { logo: { x: 140, y: 380, w: 800 }, lot: { x: 40, y: 760, w: 1000, h: 562 }, tag: { y: 1420, size: 44, w: 900 } }
          : { logo: { x: 600, y: 64, w: 720 }, lot: { x: 432, y: 232, w: 1056, h: 594 }, tag: { y: 872, size: 38, w: 1400 } };
        const rise = (1 - c.easeOut(u / 0.9)) * 40;
        return [
          html("logo", `<img src="${BRAND.lockup}" style="width:100%">`, { left: `${L.logo.x}px`, top: `${L.logo.y + rise * 0.5}px`, width: `${L.logo.w}px`, opacity: String(logoA) }),
          { kind: "lottie", name: "hero-solver", frame: fr, box: L.lot, opacity: c.easeOut(u / 0.5) * a, transform: `translateY(${rise.toFixed(1)}px) scale(${(0.96 + 0.04 * c.easeOut(u / 0.9)).toFixed(4)})` },
          html("title", `Timetables that keep every rule.<br>Rooms booked in a few taps.`, { left: "50%", transform: "translateX(-50%)", textAlign: "center", top: `${L.tag.y}px`,
            width: `${L.tag.w}px`, fontSize: `${L.tag.size}px`, fontWeight: "600", opacity: String(tagA) }),
        ];
      },
    },
    chapter("ch-import", "file-to-rules", "1", "Import", "Start from the planning office's own workbooks", "Weekly grids, planning lists, exam lists and the room master, as they are."),
    takeScene({ id: "import", chapter: { n: "1", label: "Import" }, views: [{ take: T["launch-import"] }] }, format),
    takeScene({ id: "solve", chapter: { n: "2", label: "Solve" }, captions: { 0: "A real solver run on the autumn term's data" }, views: [{ take: T["launch-run"], steps: [0, 1] }] }, format),
    chapter("ch-report", "precheck-fix", "3", "Explain", "Nothing is dropped silently", "The run report says what could not be placed, why, and what would fix it.", 2400),
    takeScene({ id: "report", chapter: { n: "3", label: "Explain" }, views: [{ take: T["launch-run"], steps: [2, 3] }] }, format),
    takeScene({ id: "publish", chapter: { n: "4", label: "Publish" }, views: [{ take: T["launch-run"], steps: [4, 5] }] }, format),
    takeScene({ id: "reserve", layout: "phone", chapter: { n: "5", label: "Book" }, headline: "Book a room<br>in a few taps", subline: "On the phone, for staff and academics. Free rooms only, checked by the server.",
      views: [{ take: T["launch-reserve"] }] }, format),
    takeScene({ id: "approve", chapter: { n: "6", label: "Approve" }, views: [{ take: T["approval-flow"], steps: [2, 4] }] }, format),
    takeScene({ id: "admin", chapter: { n: "7", label: "Run it" }, views: [{ take: T["launch-admin"] }] }, format),
    {
      id: "outro", kind: "outro", durMs: 4200, overlapNext: false,
      render(c) {
        const u = c.local / 1000;
        const a = c.fin;
        const s = (d) => c.easeOut((u - d) / 0.6) * a;
        const V = format === "vertical";
        const lw = V ? 820 : 760;
        return [
          html("logo", `<img src="${BRAND.lockup}" style="width:100%">`, { left: `${(c.W - lw) / 2}px`, top: `${V ? 640 : 300}px`, width: `${lw}px`, opacity: String(s(0)) }),
          html("title", `University timetabling, exams and room booking.`, { left: "50%", transform: "translateX(-50%)", textAlign: "center", top: `${V ? 900 : 500}px`, width: `${V ? 960 : 1500}px`,
            fontSize: `${V ? 46 : 44}px`, fontWeight: "600", opacity: String(s(0.35)) }),
          ...(V
            ? [html("chip", `<b style="width:34px;height:34px;font-size:18px">★</b>Open source · AGPL-3.0`, { left: "50%", transform: "translateX(-50%)", top: "1060px", fontSize: "30px", padding: "10px 24px 10px 12px", whiteSpace: "nowrap", opacity: String(s(0.7)) }),
               html("title", BRAND.repo, { left: "50%", transform: "translateX(-50%)", textAlign: "center", top: "1150px", width: "1000px", fontSize: "32px", fontWeight: "600", color: "#1E3A8A", opacity: String(s(0.9)) })]
            : [html("chip", `<b style="width:34px;height:34px;font-size:18px">★</b>Open source · AGPL-3.0 · ${BRAND.repo}`, { left: "50%", transform: "translateX(-50%)", top: "610px", fontSize: "28px", padding: "10px 24px 10px 12px", whiteSpace: "nowrap", opacity: String(s(0.7)) })]),
          html("title", FEATURES.map((f) => `<span style="display:inline-block;margin:6px 8px;padding:8px 18px;border-radius:999px;background:rgba(255,255,255,.7);border:1px solid rgba(15,23,42,.08)">${f}</span>`).join(""),
            { left: "50%", transform: "translateX(-50%)", textAlign: "center", top: `${V ? 1260 : 720}px`, width: `${V ? 980 : 1500}px`, fontSize: `${V ? 26 : 24}px`, fontWeight: "500", color: "#334155", opacity: String(s(1.0)) }),
        ];
      },
    },
  ];
  return {
    size: g.size,
    scenes,
    crossfadeMs: 500,
    lotties: ["hero-solver", "file-to-rules", "precheck-fix"],
    camera: {
      // desktop: Screen Studio-like zoom on the action, never past 1.7x (2x capture keeps text sharp up to 2x)
      desktop: { maxZoom: format === "vertical" ? 1.6 : 1.5, minZoom: 1.12, stiffness: 90, bridgeMs: 1600, leadMs: 600, tailMs: 900, fill: format === "vertical" ? 0.8 : 0.7 },
      phone: { zoom: false },
    },
  };
}

/** README feature clips (docs/images/recordings, the names clips.json uses): launch.sh clips records each journey once
 * (frames engine, 1440x810 @2x or the phone at @3x), renders the full take (<take>.mp4) and one clip per id. */
export const CLIPS = [
  { id: "reserve-slot", journey: "reserve-panel", clip: "reserve-slot", device: "desktop" },
  { id: "reserve-drag", journey: "reserve-panel", clip: "reserve-drag", device: "desktop" },
  { id: "find-room", journey: "find-room", clip: "find-room", device: "desktop" },
  { id: "audit-undo", journey: "audit-undo", clip: "audit-undo", device: "desktop" },
  { id: "calendar-move", journey: "calendar-move", clip: "calendar-move", device: "desktop" },
  { id: "precheck-fix", journey: "studio-rule-fix", clip: "precheck-fix", device: "desktop" },
  { id: "reserve-phone", journey: "launch-reserve", clip: null, device: "phone" },
  { id: "approval-request", journey: "approval-flow", clip: "approval-request", device: "desktop" },
  { id: "approval-approve", journey: "approval-flow", clip: "approval-approve", device: "desktop" },
];
