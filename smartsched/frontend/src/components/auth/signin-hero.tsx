"use client";
/**
 * The sign-in hero (docs/design/v3/auth.md §11.3–§11.4; AUX-10). Amends sign-in.md §3.1 item 4 at the owner's request.
 *
 * Purpose: while the person signs in, the scene quietly shows what SmartSched does (a room × period grid filling,
 * one clash resolved, 100/100), then holds that picture. It never competes with the form:
 * - only at ≥ 1024 px, never in forced colours, and only where it is mounted (`/login`, not the 2FA step);
 * - it starts after first paint + `requestIdleCallback` + 300 ms; the player and JSON load only then;
 * - **one pass** of frames 0 → 140 (4.67 s at 30 fps, under the WCAG 2.2.2 5 s limit), then it pauses and seeks
 *   to the poster frame 140 and holds there (no loop);
 * - entry: the tint frame fades in (opacity 0 → 1, `dur.slow` 240 ms, `ease.out`) with a 4 px rise, once the
 *   first frame is ready, so it never pops in half-drawn;
 * - reduced motion (OS or the in-app switch) or Save-Data → the static poster PNG, no player request, and under
 *   reduced motion no entry motion either;
 * - a theme switch mid-play shows the new theme's poster instead of replaying.
 * Decorative: `aria-hidden`, `pointer-events: none`; the frame is a translucent tint with no backdrop-filter (the
 * sheet stays the only blurred surface: no glass on glass).
 *
 * Source: SmartSched Lottie set `docs/lottie/hero-solver-{light,dark}.json` (AGPL-3.0, same as the repo), copied to
 * src/assets/lottie; player `lottie-react` (MIT), light build (svg renderer, no expressions).
 */
import type { LottieHandle } from "lottie-react";
import { motion } from "motion/react";
import Image, { type StaticImageData } from "next/image";
import { useTheme } from "next-themes";
import { memo, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ComponentType } from "react";
import heroDarkPoster from "@/assets/lottie/hero-solver-dark-poster.png";
import heroLightPoster from "@/assets/lottie/hero-solver-light-poster.png";
import { dur, ease, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";

type Theme = "light" | "dark";
type LottieJson = { layers: { nm?: string }[]; [key: string]: unknown };
type PlayerProps = {
  src: object;
  autoplay?: boolean;
  loop?: boolean;
  segment?: readonly [number, number];
  subscriptions?: { ready?: () => void; complete?: () => void };
  lottieRef?: React.Ref<LottieHandle>;
  className?: string;
};
type Player = ComponentType<PlayerProps>;

/** One pass, start → poster frame (docs/lottie/README.md: hero-solver poster frame 140). */
export const HERO_SEGMENT = [0, 140] as const;
/** After idle, so the form is interactive first (§11.3 "When it plays"). */
export const HERO_DELAY_MS = 300;
/** The file's frame rate (docs/lottie/README.md): frame 140 is reached 4.67 s after the first frame. */
export const HERO_FPS = 30;
/** At most this many frames in a row are skipped while the browser reports pending input. */
const MAX_SKIP = 4;
/**
 * The hero draws nothing until this long after the last input event. Decision 2026-10-19 (owner: "typing stays under
 * 50 ms frames"): skipping only the frame that handled a keystroke still drew the scene between keys, and one drawn
 * lottie frame alone is 45-70 ms of main-thread work on a CPU-only renderer (CI, low-end laptops), so every frame
 * drawn while someone typed was a long frame. The scene now holds while the person types (a held key holds it too)
 * and catches up by time afterwards: the frame number comes from the clock, so the pass still ends at 4.67 s.
 */
export const HERO_INPUT_HOLD_MS = 250;
/** Events that mean "the person is using the form": the hero draws nothing in the frame that handles one. */
const INPUT_EVENTS = ["keydown", "beforeinput", "input", "pointerdown", "compositionupdate"] as const;

/** The animation clock (an object so tests can drive it by hand). */
export const heroClock = {
  raf: (cb: (t: number) => void): number => window.requestAnimationFrame(cb),
  caf: (id: number): void => window.cancelAnimationFrame(id),
};

type Scheduling = { scheduling?: { isInputPending?: () => boolean } };
const browserInputPending = () => (navigator as Navigator & Scheduling).scheduling?.isInputPending?.() === true;

export type HeroDriver = { start: () => void; noteInput: () => void; stop: () => void };

/**
 * AUX-10 typing fix (fix-b-2026-10-18): the longest frame while typing was 55-70 ms because lottie drew the scene in
 * the same frame that handled the keystroke. The hero now runs its own clock instead of lottie's autoplay: each
 * animation frame works out the frame number from the elapsed time (whole frames at 30 fps) and seeks there, EXCEPT
 * within HERO_INPUT_HOLD_MS of an input event (or while the browser reports pending input), when it draws nothing of
 * the hero. The next drawn frame is where the time says, so holding never delays the pass (one pass stays 4.67 s).
 */
export function createHeroDriver(o: {
  seek: (frame: number) => void;
  pause: () => void;
  onDone: () => void;
  /** after the first seek: the scene is on screen */
  onFirstFrame?: () => void;
  raf?: (cb: (t: number) => void) => number;
  caf?: (id: number) => void;
  inputPending?: () => boolean;
}): HeroDriver {
  const raf = o.raf ?? heroClock.raf;
  const caf = o.caf ?? heroClock.caf;
  const inputPending = o.inputPending ?? browserInputPending;
  const end = HERO_SEGMENT[1];
  let t0: number | null = null;
  let last = -1;
  let input = false;
  let lastInput = -Infinity;
  let skipped = 0;
  let id: number | null = null;
  let finished = false;
  const tick = (t: number) => {
    id = null;
    if (finished) return;
    if (t0 === null) t0 = t;
    if (input) {
      // the frame that handles an input event starts the hold
      input = false;
      lastInput = t;
    }
    if (t - lastInput < HERO_INPUT_HOLD_MS || (inputPending() && skipped < MAX_SKIP)) {
      if (t - lastInput >= HERO_INPUT_HOLD_MS) skipped += 1;
      id = raf(tick);
      return;
    }
    skipped = 0;
    const frame = Math.min(end, Math.floor(((t - t0) * HERO_FPS) / 1000));
    if (frame !== last) {
      const first = last === -1;
      last = frame;
      o.seek(frame);
      if (first) o.onFirstFrame?.();
    }
    if (frame >= end) {
      // settle: hold exactly on the poster frame, never loop
      finished = true;
      o.pause();
      o.onDone();
      return;
    }
    id = raf(tick);
  };
  return {
    start: () => {
      if (id === null && !finished) id = raf(tick);
    },
    noteInput: () => {
      input = true;
    },
    stop: () => {
      finished = true;
      if (id !== null) caf(id);
      id = null;
    },
  };
}

/** Code-split loaders; nothing here is in the initial bundle. Called through the object so tests can observe them. */
export const heroLoaders = {
  player: (): Promise<Player> => import("lottie-react").then((m) => m.LottieLight as unknown as Player),
  data: {
    light: () => import("@/assets/lottie/hero-solver-light.json") as Promise<unknown>,
    dark: () => import("@/assets/lottie/hero-solver-dark.json") as Promise<unknown>,
  } satisfies Record<Theme, () => Promise<unknown>>,
};

const POSTER: Record<Theme, StaticImageData | string> = { light: heroLightPoster, dark: heroDarkPoster };

const WIDE = "(min-width: 1024px)";
const FORCED = "(forced-colors: active)";
const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const REDUCED_DATA = "(prefers-reduced-data: reduce)";

function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => undefined;
      const mql = window.matchMedia(query);
      mql.addEventListener?.("change", onChange);
      return () => mql.removeEventListener?.("change", onChange);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}

type Connection = { saveData?: boolean; addEventListener?: (t: "change", f: () => void) => void; removeEventListener?: (t: "change", f: () => void) => void };
const connection = (): Connection | undefined => (typeof navigator === "undefined" ? undefined : (navigator as Navigator & { connection?: Connection }).connection);

function useSaveData(): boolean {
  const query = useMedia(REDUCED_DATA);
  const header = useSyncExternalStore(
    (onChange) => {
      const c = connection();
      c?.addEventListener?.("change", onChange);
      return () => c?.removeEventListener?.("change", onChange);
    },
    () => connection()?.saveData === true,
    () => false,
  );
  return query || header;
}

/** The opaque page-colour background layer would hide the tint frame; drop it (as EmptyState does). */
function withoutBackground(mod: unknown): LottieJson {
  const json = ((mod as { default?: LottieJson }).default ?? mod) as LottieJson;
  return { ...json, layers: json.layers.filter((layer) => layer.nm !== "background") };
}

const FRAME = "relative aspect-video w-full overflow-hidden rounded-2xl bg-(--mat-thin) glass-edge";

function Poster({ theme }: { theme: Theme }) {
  return <Image src={POSTER[theme]} alt="" fill sizes="640px" className="object-cover" priority={false} />;
}

type Loaded = { Player: Player; data: LottieJson };

/** Loads after idle + 300 ms, enters, plays 0 → 140 once, then holds frame 140. */
function HeroPlayer({ theme, onState, onStart }: { theme: Theme; onState: (s: "playing" | "done" | "poster") => void; onStart: (t: Theme) => void }) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  const handle = useRef<LottieHandle>(null);
  const driver = useRef<HeroDriver | null>(null);
  // stable props: a re-render of the player never re-subscribes or restarts anything
  const subscriptions = useMemo(
    () => ({
      ready: () => {
        driver.current?.stop();
        driver.current = createHeroDriver({
          seek: (frame) => handle.current?.seek({ frame }),
          pause: () => handle.current?.pause(),
          onDone: () => onState("done"),
          // "playing" from the first drawn frame: building the SVG tree and its first raster are the scene's one
          // heavy moment (pod e2e #125: a 52 ms frame on a 2-vCPU software renderer); they are the entrance
          onFirstFrame: () => onState("playing"),
        });
        driver.current.start();
      },
    }),
    [onState],
  );
  // any keystroke, text input or tap: the frame that handles it draws nothing of the hero (passive, capture)
  const lastInputAt = useRef(-Infinity);
  useEffect(() => {
    const note = () => {
      lastInputAt.current = performance.now();
      driver.current?.noteInput();
    };
    const opts = { capture: true, passive: true } as const;
    for (const type of INPUT_EVENTS) document.addEventListener(type, note, opts);
    return () => {
      for (const type of INPUT_EVENTS) document.removeEventListener(type, note, opts);
      driver.current?.stop();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let idle: number | undefined;
    const start = () => {
      timer = setTimeout(() => {
        onStart(theme);
        Promise.all([heroLoaders.player(), heroLoaders.data[theme]()])
          .then(async ([Player, mod]) => {
            // building the scene (lottie's SVG tree and its first raster) is the hero's heaviest moment: never in the
            // middle of someone typing. It waits for a quiet HERO_INPUT_HOLD_MS like every drawn frame does
            // (owner decision 2026-10-19, "make the app lighter, not the budget looser")
            while (!cancelled && performance.now() - lastInputAt.current < HERO_INPUT_HOLD_MS) {
              await new Promise((r) => setTimeout(r, HERO_INPUT_HOLD_MS - (performance.now() - lastInputAt.current)));
            }
            if (cancelled) return;
            setLoaded({ Player, data: withoutBackground(mod) });
          })
          .catch(() => {
            if (cancelled) return;
            setFailed(true);
            onState("poster");
          });
      }, HERO_DELAY_MS);
    };
    if (typeof window.requestIdleCallback === "function") idle = window.requestIdleCallback(start, { timeout: 2000 });
    else timer = setTimeout(start, 0);
    return () => {
      cancelled = true;
      if (idle !== undefined) window.cancelIdleCallback?.(idle);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [theme, onState, onStart]);

  if (failed) {
    return (
      <motion.div className={FRAME} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: dur.slow, ease: ease.out }}>
        <Poster theme={theme} />
      </motion.div>
    );
  }
  const { Player, data } = loaded ?? {};
  return (
    // hidden (opacity 0) until the first frame exists; the frame holds no backdrop-filter, so fading it is safe
    <motion.div className={FRAME} initial={{ opacity: 0, y: 4 }} animate={loaded ? { opacity: 1, y: 0 } : { opacity: 0, y: 4 }} transition={{ duration: dur.slow, ease: ease.out }}>
      {Player && data ? (
        // autoplay off: createHeroDriver steps the frames from `ready` to the poster frame (one pass, no loop)
        <Player src={data} autoplay={false} loop={false} segment={HERO_SEGMENT} lottieRef={handle} className="size-full" subscriptions={subscriptions} />
      ) : null}
    </motion.div>
  );
}

/**
 * Mounted by `SignInShell` (scene area, right of the sheet) on `/login` only. Memoised (no props): the sheet's
 * re-renders never reach it (AUX-10: no hero work on a keystroke).
 */
export const SignInHero = memo(function SignInHero() {
  const hydrated = useHydrated();
  const wide = useMedia(WIDE);
  const forced = useMedia(FORCED);
  const osReduce = useMedia(REDUCED_MOTION);
  const appReduce = useReduce();
  const saveData = useSaveData();
  const { resolvedTheme } = useTheme();
  const theme: Theme = resolvedTheme === "dark" ? "dark" : "light";
  const [playState, setPlayState] = useState<"loading" | "playing" | "done" | "poster">("loading");
  // the theme the pass started in (captured at load time: next-themes resolves only after mount); a switch
  // afterwards shows the new theme's poster instead of replaying
  const [playTheme, setPlayTheme] = useState<Theme | null>(null);

  if (!hydrated || !wide || forced) return null;
  const reduce = osReduce || appReduce;
  const still = reduce || saveData || (playTheme !== null && theme !== playTheme);
  const state = still ? "poster" : playState;
  return (
    <div
      aria-hidden="true"
      data-testid="signin-hero"
      data-state={state}
      className="pointer-events-none absolute right-8 bottom-8 w-[min(calc(52vw-120px),640px)] select-none max-lg:hidden forced-colors:hidden"
    >
      {still ? (
        reduce ? (
          <div className={FRAME}>
            <Poster theme={theme} />
          </div>
        ) : (
          <motion.div className={FRAME} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: dur.slow, ease: ease.out }}>
            <Poster theme={theme} />
          </motion.div>
        )
      ) : (
        <HeroPlayer theme={theme} onState={setPlayState} onStart={setPlayTheme} />
      )}
    </div>
  );
});
