# SmartSched animations (Lottie)

Four original, text-free Lottie animations that explain SmartSched in the README. GitHub cannot play
Lottie JSON inline, so the README embeds the rendered **GIFs**. The JSON sources stay here so the app can
play them later with a Lottie player.

All values come from [`docs/design/tokens.md`](../design/tokens.md): page background, surfaces, status
colours (feasible / infeasible / warning), the eight-slot faculty palette, radii 8/12/14/16, and the
`--ease-out` / `--ease-in-out` / `--ease-emphasized` curves. Each light and dark variant uses its own token
values (they are not inverted). Every single tween is ≤ 9 frames (300 ms at 30 fps, `--dur-max`), and
`build/audit.mjs` enforces this.

| Animation | Canvas / length | What it shows | Poster frame |
|---|---|---|---|
| `hero-solver-{light,dark}.json` | 960×540, 6 s loop, 180 f | Empty room × period grid (8 × 6 rounded cells, room labels and period ticks as skeleton bars). 20 class blocks in faculty colours fly in with a stagger and snap into place (scale 90 → 103 → 100) while the progress bar steps up. The 21st block lands on a taken cell: red dashed outline, red tint, x-octagon badge and an "error shake". It then slides two cells right into a free slot, marked by a blue drop-ok outline and a green check. The progress bar turns green and a **100/100** badge pops (check icon plus digits drawn as strokes). Blocks fade out, leaving the empty grid, so the loop is seamless. | 140 |
| `nl-to-rules-{light,dark}.json` | 720×405, 5 s, 150 f | A chat bubble shows bouncing typing dots, then grows into a three-line message. Each line gets a coloured highlight, and a rule card slides from that line into a stack of dashed slots. Each card has a matching coloured **source chip** and a **Must / Try** segmented toggle (lock icon / tilde icon) that animates on: Must, Try, Must. | 125 |
| `file-to-rules-{light,dark}.json` | 720×405, 5 s, 150 f | A spreadsheet icon drops (with a squash) into a dashed dropzone, which shows its hover state. The sheet parks in the corner and five rows appear. A blue scan line sweeps the rows, and the three that hold rules get a blue outline. Those rows peel off and grow into rule cards with a file-source chip and a drawn **check mark**. The two non-rule rows dim. | 128 |
| `precheck-fix-{light,dark}.json` | 720×405, 4 s, 120 f | A readiness gauge starts low and **red**, with an x-octagon at its centre. In a list of three warnings, each "Fix" button is pressed and its warning triangle turns into a green check. The gauge steps 30 → 56 → 80 → 100 and goes red → **amber** → **green**, with matching icon swaps and a final pulse. | 96 |

Rendered outputs live in [`docs/images/lottie/`](../images/lottie/): `<name>-<theme>.gif` (infinite loop,
30 fps), `<name>-<theme>.mp4` (H.264, yuv420p, faststart; the 720×405 clips are cropped to 720×404 because
yuv420p needs even sizes, and the dropped row is background) and `<name>-<theme>-poster.png` (2× still
of the poster frame).

## Embedding in the README (theme-aware)

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/lottie/hero-solver-dark.gif">
  <img alt="SmartSched fills a room-by-period grid with classes, resolves a double booking, and reaches a 100/100 hard score"
       src="docs/images/lottie/hero-solver-light.gif" width="960">
</picture>
```

For a static fallback on reduced-motion systems, add sources before the GIF sources, for example
`<source media="(prefers-reduced-motion: reduce) and (prefers-color-scheme: dark)" srcset="…-dark-poster.png">`.
The browser evaluates the `media` attribute. GitHub's own "autoplay animated images" accessibility setting
also pauses GIFs, but check how it behaves on the live page before relying on it.

## Regenerate (exact commands)

From the repository root. Build dependencies are **not** installed in the repo. Use a scratch npm project:

```bash
# 1. one-off: build deps in a scratch dir (any path outside the repo)
mkdir -p /tmp/lottie-build && (cd /tmp/lottie-build && npm init -y >/dev/null && npm i lottie-web@5.13.0 playwright-core@1.55.1)

# 2. write the 8 JSON files (pure Node >= 20, no dependencies)
node docs/lottie/build/generate.mjs

# 3. check the motion rule (every changing tween <= 300 ms); exits 1 on violation
node docs/lottie/build/audit.mjs

# 4. render frames with lottie-web (svg renderer) in headless Chromium, then GIF + MP4 + poster via ffmpeg
export LOTTIE_BUILD_DEPS=/tmp/lottie-build
export CHROMIUM=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell   # or any Chrome/Chromium binary
docs/lottie/build/render.sh                 # all four, both themes
docs/lottie/build/render.sh hero-solver     # just one
GIF_FPS=20 docs/lottie/build/render.sh      # smaller GIFs if a budget is ever exceeded
```

What the steps do:

- `build/generate.mjs` is a small Lottie DSL (rect / ellipse / path / fill / stroke / trim / group, keyframes
  with token easings). Each scene is a function of the theme object, so light and dark are generated from
  one definition. Output is bodymovin schema 5.12 with one `background` layer (the token page background)
  and a `content` precomp that fades out at the end of the loop.
- `build/render.mjs` loads the JSON with `lottie.loadAnimation({ renderer: "svg" })`, steps
  `anim.goToAndStop(frame, true)` for every frame, and screenshots the container. It **fails on any console
  error or warning** and also takes `--scale 2` and `--frames 0,90`.
- `build/render.sh` builds the GIF with two-pass `palettegen` (128 colours, `stats_mode=diff`) and
  `paletteuse` (`dither=none`, `diff_mode=rectangle`, which keeps flat UI colours exact) and `-loop 0`.
  It also writes `libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart` and the 2× poster.

Budgets: hero GIF ≤ 2.5 MB, the others ≤ 1.5 MB each. Current sizes are about 0.37 MB for the hero and
0.13–0.22 MB for the others, at the full 30 fps.

## Licence

Original work for SmartSched, made from simple geometric shapes only: no fonts, text layers, images,
icon packs or third-party Lottie files. The icons (check, x-octagon, warning triangle, lock, tilde,
sparkle, spreadsheet) are drawn from scratch in `generate.mjs`. It is released under the **same licence as
the repository, AGPL-3.0** (see [`/LICENSE.txt`](../../LICENSE.txt)). lottie-web (MIT) and playwright-core
(Apache-2.0) are build-time tools only and are not shipped or vendored.

## Using the JSON in the app later

The admin panel (Next.js 15, `motion`, tokens in `globals.css`) can play the same files. Copy the chosen
JSON into `smartsched/frontend/src/assets/lottie/` and the posters into `smartsched/frontend/public/lottie/`
(frontend-engineer owns both directories), then choose a player:

- **`lottie-react`** (MIT, wraps lottie-web). Simplest option for plain JSON:

  ```tsx
  "use client";
  import dynamic from "next/dynamic";
  import { useReducedMotion } from "motion/react";
  import { useTheme } from "next-themes";
  import heroLight from "@/assets/lottie/hero-solver-light.json";
  import heroDark from "@/assets/lottie/hero-solver-dark.json";
  const Lottie = dynamic(() => import("lottie-react"), { ssr: false });

  export function HeroSolver() {
    const reduce = useReducedMotion();
    const { resolvedTheme } = useTheme();
    const theme = resolvedTheme === "dark" ? "dark" : "light";
    if (reduce) {
      return <img src={`/lottie/hero-solver-${theme}-poster.png`} alt="Schedule solved, hard score 100/100" width={960} height={540} />;
    }
    return <Lottie animationData={theme === "dark" ? heroDark : heroLight} loop autoplay aria-hidden
                   rendererSettings={{ preserveAspectRatio: "xMidYMid meet" }} />;
  }
  ```

- **`@lottiefiles/dotlottie-react`** (MIT, WASM ThorVG renderer, supports `.lottie` bundles and themes).
  Use `<DotLottieReact src="/lottie/hero-solver-light.json" loop autoplay />` (JSON served from `public/`).
  You could pack both variants into one `.lottie` as two animations. dotLottie *themes* would need
  slot ids (`sid`) on the colour properties, and `generate.mjs` does not emit those yet.

Rules for in-app use (tokens.md §0.3 and §6):

1. **`prefers-reduced-motion: reduce` falls back to the poster PNG** (or to frame `posterFrame` through
   `goToAndStop(n, true)`) with no autoplay. Never loop decorative motion for reduced-motion users.
2. Pick the variant from the resolved theme (`next-themes`), not with a CSS filter. To show the animation on
   a surface other than `--bg`, delete or hide the `background` layer (layer name `background`).
3. Decorative in context: `aria-hidden` on the player and a real text label next to it. When it carries
   meaning on its own (for example an empty state), give the poster `<img>` an `alt` instead.
4. Pause when off-screen (`IntersectionObserver` → `anim.pause()`), and do not autoplay more than one
   loop on a page at a time.
5. These files use no expressions, effects, mattes, images or text layers, only shapes, trim paths and one
   precomp. That is the most portable subset. They are verified in the lottie-web svg and canvas renderers;
   dotLottie (ThorVG) has not been tested yet.

## Verification done

- All 8 JSONs load in lottie-web 5.13.0 with **no console errors or warnings**, using the svg renderer
  (every frame) and the canvas renderer (every 7th frame).
- `build/audit.mjs` reports the longest tween as 9 frames (300 ms) in every file.
- Loop seams are clean: frame 0 and the last frame are pixel-identical (ImageMagick `compare -metric AE`
  = 0) in all 8 renders.
- GIFs report `Iterations: 0` (infinite loop), with 3/3/4 cs frame delays (exactly 30 fps on average).
- Frames were inspected by eye in both themes: at entry, mid-flight, the conflict, the resolution and the
  final state.
