"""SmartSched brand generator (stdlib + fontTools + uharfbuzz). Writes hand-tuned SVGs.

Construction (one sentence): an S drawn on a 5 x 5 period grid (u = 32), split into two identical
blocks rotated 180 degrees that sit side by side in the middle period row, a half-period gap apart.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from geom import rounded_poly, fmt

U = 32          # one period
RB = 48         # bowl radius (outer); inner = RB - U = 16 (concentric)
RT = 8          # terminal corner radius (u/4)
RG = 2          # corner radius at the join
GAP = 16        # half a period
OVR = 3         # optical overshoot of round bowls past the flat terminals (~2 % of glyph width)

def piece(x0, y0, gap=GAP, inset=0.0, c=None):
    """Top piece. Polygon is clockwise (screen coords). inset > 0 thins every edge (reversed version)."""
    c = c if c is not None else x0 + 2.5 * U
    h = c - gap / 2
    pts = [(x0 - OVR, y0), (x0 + 5 * U, y0), (x0 + 5 * U, y0 + U), (x0 + U, y0 + U), (x0 + U, y0 + 2 * U),
           (h, y0 + 2 * U), (h, y0 + 3 * U), (x0 - OVR, y0 + 3 * U)]
    rr = [RB, RT, RT, RB - U, RB - U, RG, RG, RB]
    convex = [True, True, True, False, False, True, True, True]
    if gap == 0:  # small-size cut: the half-arm runs to the centre and merges with its twin
        pts[5] = (c, y0 + 2 * U); pts[6] = (c, y0 + 3 * U); rr[5] = rr[6] = 0
    if inset:
        n = len(pts); new = []
        for i in range(n):
            p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
            def nrm(a, b):
                dx, dy = b[0] - a[0], b[1] - a[1]; L = (dx * dx + dy * dy) ** .5
                return (-dy / L, dx / L)
            n1, n2 = nrm(p0, p1), nrm(p1, p2)
            new.append((p1[0] + inset * (n1[0] + n2[0]), p1[1] + inset * (n1[1] + n2[1])))
        if gap == 0:  # keep the merge seam closed
            new[5] = (c, new[5][1]); new[6] = (c, new[6][1])
        pts = new
        rr = [r - inset if cv else r + inset for r, cv in zip(rr, convex)]
        if gap == 0: rr[5] = rr[6] = 0
    return pts, rr

def rot(pts, cx, cy):
    return [(2 * cx - x, 2 * cy - y) for x, y in pts]

def glyph_paths(x0, y0, gap=GAP, inset=0.0):
    cx, cy = x0 + 2.5 * U, y0 + 2.5 * U
    p, r = piece(x0, y0, gap, inset)
    return rounded_poly(p, r), rounded_poly(rot(p, cx, cy), r)

# ---------- wordmark (Inter Display SemiBold, OFL 1.1, outlined) ----------
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
CAP = 96  # cap height = one bowl = 3 periods

def wordmark_path(x, baseline, text="SmartSched", track=-0.005):
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    blob = hb.Blob.from_file_path(FONT); face = hb.Face(blob); font = hb.Font(face)
    buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True, "calt": True})
    tt = TTFont(FONT); gs = tt.getGlyphSet(); order = tt.getGlyphOrder()
    upm = tt["head"].unitsPerEm; s = CAP / tt["OS/2"].sCapHeight
    pen_x = 0.0; d = ""
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        sp = SVGPathPen(gs, ntos=lambda v: fmt(v))
        tp = TransformPen(sp, (s, 0, 0, -s, x + (pen_x + pos.x_offset) * s, baseline - pos.y_offset * s))
        gs[name].draw(tp)
        d += sp.getCommands()
        pen_x += pos.x_advance + track * upm
    width = (pen_x - track * upm) * s
    return d, width

# ---------- colour ----------
C = {
    "blue": "#0A63D1", "blue_dk": "#4DA0FF",       # liquid-glass.md 5.2 default accent (light / dark)
    "ink": "#1D1D1F", "ink_dk": "#F5F5F7",         # --label-1 light / dark
    "navy": "#0B3F86",                              # deep piece tone (light), 8.9:1 on white
    "sky": "#A9D0FF",                               # deep piece tone (dark)
    "tile": "#0A63D1", "on_tile": "#FFFFFF", "on_tile_2": "#BFDCFF",
}

def svg_doc(vb, body, title="SmartSched", extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-labelledby="t"{extra}>'
            f'<title id="t">{title}</title>{body}</svg>\n')

def two(d1, d2, c1, c2):
    if c1 == c2:
        return f'<path fill="{c1}" d="{d1}{d2}"/>'
    return f'<path fill="{c1}" d="{d1}"/><path fill="{c2}" d="{d2}"/>'

SCHEMES = {
    # name: (piece1, piece2, word, inset)
    "light": (C["blue"], C["navy"], C["ink"], 0.0),
    "dark": (C["blue_dk"], C["sky"], C["ink_dk"], 0.75),
    "mono-black": ("#000000", "#000000", "#000000", 0.0),
    "mono-white": ("#FFFFFF", "#FFFFFF", "#FFFFFF", 0.75),
    "mono": ("currentColor", "currentColor", "currentColor", 0.0),
}

def build(out_brand, out_public):
    os.makedirs(out_brand, exist_ok=True); os.makedirs(out_public, exist_ok=True)
    written = {}
    def w(path, s):
        open(path, "w").write(s); written[path] = len(s.encode())
    # mark: 192 x 192, glyph 16..176 (half-period padding)
    for sch, (c1, c2, cw, ins) in SCHEMES.items():
        d1, d2 = glyph_paths(16, 16, GAP, ins)
        w(f"{out_brand}/smartsched-mark-{sch}.svg", svg_doc("0 0 192 192", two(d1, d2, c1, c2)))
        s1, s2 = glyph_paths(16, 16, 0, ins)
        w(f"{out_brand}/smartsched-mark-small-{sch}.svg", svg_doc("0 0 192 192", two(s1, s2, c1, c2)))
    # wordmark + lockup
    wd, ww = wordmark_path(0, 144)
    wd_l, _ = wordmark_path(224, 144)
    wm_w = ww + 16
    lk_w = 224 + ww + 16
    meta = {"wordmark_width": round(ww, 2), "lockup_width": round(lk_w, 2)}
    for sch, (c1, c2, cw, ins) in SCHEMES.items():
        w(f"{out_brand}/smartsched-wordmark-{sch}.svg",
          svg_doc(f"-8 48 {fmt(wm_w)} 96", f'<path fill="{cw}" d="{wd}"/>'))
        d1, d2 = glyph_paths(16, 16, GAP, ins)
        w(f"{out_brand}/smartsched-lockup-{sch}.svg",
          svg_doc(f"0 0 {fmt(lk_w)} 192", two(d1, d2, c1, c2) + f'<path fill="{cw}" d="{wd_l}"/>'))
    # app tile: 256, radius 64 (25 %), glyph 48..208 (62.5 %)
    def tile(gap, bg=C["tile"], fg=C["on_tile"], fg2=C["on_tile"], square=False):
        d1, d2 = glyph_paths(48, 48, gap)
        bgshape = f'<rect width="256" height="256" fill="{bg}"/>' if square else f'<rect width="256" height="256" rx="64" fill="{bg}"/>'
        return svg_doc("0 0 256 256", bgshape + two(d1, d2, fg, fg2))
    w(f"{out_brand}/smartsched-tile.svg", tile(GAP))
    w(f"{out_brand}/smartsched-tile-small.svg", tile(0))
    # maskable: glyph inside the 80 % safe circle on a full-bleed square
    d1, d2 = glyph_paths(48, 48, GAP)
    w(f"{out_brand}/smartsched-tile-maskable.svg",
      svg_doc("0 0 256 256", f'<rect width="256" height="256" fill="{C["tile"]}"/>'
              f'<g transform="translate(128 128) scale(.8) translate(-128 -128)">{two(d1, d2, "#FFFFFF", "#FFFFFF")}</g>'))
    # SVG favicon: small cut tile, same in light and dark (the tile carries its own contrast)
    w(f"{out_public}/favicon.svg", tile(0))
    json.dump(meta, open(f"{out_brand}/.meta.json", "w"))
    return written, meta

if __name__ == "__main__":
    written, meta = build(sys.argv[1], sys.argv[2])
    for p, n in sorted(written.items()):
        print(f"{n:6d}  {p}")
    print(meta)

# ---------- README header ----------
def header(theme):
    W, H = 1280, 320
    if theme == "light":
        bg, line, cell, ev1, ev2 = "#F4F6F9", "#141824", ".06", "#0A63D1", "#0B3F86"
        c1, c2, cw, ins = C["blue"], C["navy"], C["ink"], 0.0
        cell_fill, line_op, ev_op = "#0A63D1", ".08", ".16"
    else:
        bg, line = "#11161D", "#FFFFFF"
        c1, c2, cw, ins = C["blue_dk"], C["sky"], C["ink_dk"], 0.75
        cell_fill, line_op, ev_op = "#4DA0FF", ".1", ".2"
        ev1, ev2 = "#4DA0FF", "#A9D0FF"
    lh = 112; k = lh / 192
    _, ww = wordmark_path(0, 144)
    lk_w = 224 + ww + 16
    tx = (W - lk_w * k) / 2; ty = (H - lh) / 2
    d1, d2 = glyph_paths(16, 16, GAP, ins)
    wd, _ = wordmark_path(224, 144)
    # placed classes on the period grid (col, row, span): edges only, the vignette keeps the centre calm
    events = [(0, 1, 2, ev1), (1, 7, 2, ev2), (3, 0, 1, ev2), (16, 1, 2, ev1), (17, 6, 2, ev2), (15, 8, 1, ev1),
              (2, 4, 1, ev1), (18, 3, 1, ev2)]
    px, py, cw_, ch_ = 64, 32, 56, 24
    ox, oy = 32, 16
    evd = {}
    for col, row, span, col_c in events:
        x = ox + col * px; y = oy + row * py
        evd.setdefault(col_c, "")
        evd[col_c] += rounded_poly([(x, y), (x + span * px - 8, y), (x + span * px - 8, y + ch_), (x, y + ch_)], 6)
    ev_svg = "".join(f'<path fill="{c}" fill-opacity="{ev_op}" d="{d}"/>' for c, d in evd.items())
    body = (
        f'<defs><pattern id="g" width="{px}" height="{py}" patternUnits="userSpaceOnUse" x="{ox}" y="{oy}">'
        f'<rect width="{cw_}" height="{ch_}" rx="6" fill="{cell_fill}" fill-opacity="{".05" if theme == "light" else ".06"}"/></pattern>'
        f'<radialGradient id="v" cx="640" cy="160" r="560" gradientUnits="userSpaceOnUse" gradientTransform="matrix(1 0 0 .42 0 92.8)">'
        f'<stop offset=".42" stop-color="{bg}"/><stop offset="1" stop-color="{bg}" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="c"><rect width="{W}" height="{H}" rx="24"/></clipPath></defs>'
        f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{bg}"/>'
        f'<rect width="{W}" height="{H}" fill="url(#g)"/>{ev_svg}<rect width="{W}" height="{H}" fill="url(#v)"/></g>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="23.5" fill="none" stroke="{line}" stroke-opacity="{line_op}"/>'
        f'<g transform="translate({fmt(tx)} {fmt(ty)}) scale({fmt(k)})">{two(d1, d2, c1, c2)}<path fill="{cw}" d="{wd}"/></g>'
    )
    return svg_doc(f"0 0 {W} {H}", body, title="SmartSched", extra=f' width="{W}" height="{H}"')

# ---------- React component ----------
def component():
    g1, g2 = glyph_paths(16, 16, GAP)
    s1, s2 = glyph_paths(16, 16, 0)
    r1, r2 = glyph_paths(16, 16, GAP, 0.75)
    rs1, rs2 = glyph_paths(16, 16, 0, 0.75)
    wd, ww = wordmark_path(0, 144)
    wdl, _ = wordmark_path(224, 144)
    lk_w = 224 + ww + 16
    return f'''// SmartSched brand mark. Original work (docs/design/brand.md). Generated geometry: do not hand-edit the
// path data; regenerate from the brand source instead. Wordmark outlines: Inter Display SemiBold (SIL OFL 1.1).
//
// Construction: an S on a 5 x 5 period grid (u = 32), split into two identical blocks rotated 180 degrees
// that sit side by side in the middle period row, half a period apart. Colours are the fixed brand colours,
// not the user's accent preset (liquid-glass.md 5.2), so the mark looks the same under every accent.
import type {{ SVGProps }} from "react";
import {{ cn }} from "@/lib/utils";

export type LogoVariant = "mark" | "tile" | "wordmark" | "lockup";
/** auto: follows the `.dark` class (next-themes). mono: one colour, inherits `currentColor`. */
export type LogoTheme = "auto" | "light" | "dark" | "mono";

export type LogoProps = Omit<SVGProps<SVGSVGElement>, "children" | "viewBox"> & {{
  variant?: LogoVariant;
  /** Rendered height in px (width follows the aspect ratio). Default 32. */
  size?: number;
  theme?: LogoTheme;
  /** Accessible name. Default "SmartSched". */
  label?: string;
  /** Hide from assistive tech when visible text next to it already names the product. */
  decorative?: boolean;
  /** "auto" switches to the gapless small-size cut below 48 px. */
  cut?: "auto" | "small" | "regular";
}};

const P = {{
  mark: ["{g1}", "{g2}"],
  small: ["{s1}", "{s2}"],
  markRev: ["{r1}", "{r2}"],
  smallRev: ["{rs1}", "{rs2}"],
}} as const;
const WORD = "{wd}";
const WORD_IN_LOCKUP = "{wdl}";
const LOCKUP_W = {fmt(lk_w)};
const WORD_W = {fmt(ww + 16)};

/** Brand colours (docs/design/brand.md section 4). */
export const BRAND_COLORS = {{
  blue: "{C['blue']}", navy: "{C['navy']}", ink: "{C['ink']}",
  blueDark: "{C['blue_dk']}", skyDark: "{C['sky']}", inkDark: "{C['ink_dk']}",
  tile: "{C['tile']}", onTile: "{C['on_tile']}",
}} as const;

type Fills = {{ a: string; b: string; word: string; cls?: [string, string, string] }};
function fills(theme: LogoTheme): Fills {{
  const c = BRAND_COLORS;
  switch (theme) {{
    case "light": return {{ a: c.blue, b: c.navy, word: c.ink }};
    case "dark": return {{ a: c.blueDark, b: c.skyDark, word: c.inkDark }};
    case "mono": return {{ a: "currentColor", b: "currentColor", word: "currentColor" }};
    default:
      return {{
        a: c.blue, b: c.navy, word: c.ink,
        cls: ["fill-[{C['blue']}] dark:fill-[{C['blue_dk']}]", "fill-[{C['navy']}] dark:fill-[{C['sky']}]", "fill-[{C['ink']}] dark:fill-[{C['ink_dk']}]"],
      }};
  }}
}}

export function Logo({{
  variant = "mark", size = 32, theme = "auto", label = "SmartSched", decorative = false, cut = "auto", className, ...rest
}}: LogoProps) {{
  const small = cut === "small" || (cut === "auto" && size < 48);
  const f = fills(theme);
  const a11y = decorative
    ? ({{ "aria-hidden": true, focusable: false }} as const)
    : ({{ role: "img", "aria-label": label }} as const);
  const common = {{ xmlns: "http://www.w3.org/2000/svg", height: size, className: cn("shrink-0", className), "data-variant": variant, ...a11y, ...rest }};

  if (variant === "tile") {{
    const [a, b] = small ? P.small : P.mark;
    return (
      <svg {{...common}} width={{size}} viewBox="0 0 256 256" data-cut={{small ? "small" : "regular"}}>
        <rect width="256" height="256" rx="64" fill={{BRAND_COLORS.tile}} />
        <path fill={{BRAND_COLORS.onTile}} transform="translate(32 32)" d={{a + b}} />
      </svg>
    );
  }}

  // dark and auto-in-dark use the 0.75-unit thinned cut (white on dark reads heavier); the difference is
  // sub-pixel below 64 px, so `auto` keeps the regular cut and only the explicit dark theme swaps it.
  const rev = theme === "dark";
  const [a, b] = small ? (rev ? P.smallRev : P.small) : rev ? P.markRev : P.mark;
  const pieces = (
    <>
      <path fill={{f.cls ? undefined : f.a}} className={{f.cls?.[0]}} d={{a}} />
      <path fill={{f.cls ? undefined : f.b}} className={{f.cls?.[1]}} d={{b}} />
    </>
  );
  const word = (d: string) => <path fill={{f.cls ? undefined : f.word}} className={{f.cls?.[2]}} d={{d}} />;

  if (variant === "mark") {{
    return <svg {{...common}} width={{size}} viewBox="0 0 192 192" data-cut={{small ? "small" : "regular"}}>{{pieces}}</svg>;
  }}
  if (variant === "wordmark") {{
    return <svg {{...common}} width={{(size * WORD_W) / 96}} viewBox={{`-8 48 ${{WORD_W}} 96`}}>{{word(WORD)}}</svg>;
  }}
  return (
    <svg {{...common}} width={{(size * LOCKUP_W) / 192}} viewBox={{`0 0 ${{LOCKUP_W}} 192`}} data-cut={{small ? "small" : "regular"}}>
      {{pieces}}
      {{word(WORD_IN_LOCKUP)}}
    </svg>
  );
}}
'''

if __name__ == "__main__" and len(sys.argv) > 3:
    out_brand, _, comp = sys.argv[1], sys.argv[2], sys.argv[3]
    for t in ("light", "dark"):
        s = header(t); open(f"{out_brand}/readme-header-{t}.svg", "w").write(s); print(len(s.encode()), "header", t)
    s = component(); open(comp, "w").write(s); print(len(s.encode()), comp)
