"use client";
/**
 * The welcome sheet's hero (WG-09; welcome-guide.md §8.1 "Lottie hero", §8.2). Replaces WG-04's static `SheetHero`.
 *
 * Purpose: "this is what SmartSched does for you", told once, while the person reads the title.
 * - Clip per audience: the new `quick-reserve` (a day, a slot, a room, a receipt) for academicians, staff, department
 *   admins and approvers; `hero-solver` for viewers, `file-to-rules` for planners, `precheck-fix` for admins.
 * - It waits for the sheet to settle (240 ms), then loads the player + the clip (code-split, never in the first
 *   load), fades the player in over the empty frame (frame 0 is the clip's plain background), plays ONE pass
 *   0 → poster frame (≤ 3 s; WCAG 2.2.2 does not apply under 5 s, and it stops anyway) and holds the poster frame.
 * - At most once per page load: re-opening the sheet (Help › Turu yeniden başlat) shows the poster.
 * - Reduced motion (OS or the in-app switch), Save-Data, a load failure, or a theme switch mid-play → the static
 *   poster PNG; under reduced motion and Save-Data nothing is requested.
 * Decorative: `aria-hidden`, `pointer-events: none`, no glass (the sheet is the blurred surface; no glass on glass).
 * Sizes as before: 132 px tall on phones, 150 px from 640 px, hidden in short landscape.
 *
 * Source: SmartSched Lottie set `docs/lottie/*-{light,dark}.json` (AGPL-3.0, same as the repository), copied to
 * src/assets/lottie; player `lottie-react` (MIT), light build (svg renderer, no expressions).
 */
import type { LottieHandle } from "lottie-react";
import { motion } from "motion/react";
import Image, { type StaticImageData } from "next/image";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState, useSyncExternalStore, type ComponentType } from "react";
import fileToRulesDark from "@/assets/lottie/file-to-rules-dark-poster.png";
import fileToRulesLight from "@/assets/lottie/file-to-rules-light-poster.png";
import heroSolverDark from "@/assets/lottie/hero-solver-dark-poster.png";
import heroSolverLight from "@/assets/lottie/hero-solver-light-poster.png";
import precheckFixDark from "@/assets/lottie/precheck-fix-dark-poster.png";
import precheckFixLight from "@/assets/lottie/precheck-fix-light-poster.png";
import quickReserveDark from "@/assets/lottie/quick-reserve-dark-poster.png";
import quickReserveLight from "@/assets/lottie/quick-reserve-light-poster.png";
import type { Audience } from "@/lib/api/welcome";
import { useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { WELCOME_SHEET_SETTLE_MS, welcomeMotion } from "./motion";

type Theme = "light" | "dark";
export type HeroClip = "quick-reserve" | "hero-solver" | "file-to-rules" | "precheck-fix";
type ClipKey = `${HeroClip}-${Theme}`;

export const HERO_CLIP: Record<Audience, HeroClip> = {
  academician: "quick-reserve",
  staff: "quick-reserve",
  dept_admin: "quick-reserve",
  approver: "quick-reserve",
  viewer: "hero-solver",
  planner: "file-to-rules",
  admin: "precheck-fix",
};

/** Poster frames (docs/lottie/README.md): one pass ends and rests here. */
export const HERO_POSTER_FRAME: Record<HeroClip, number> = {
  "quick-reserve": 86,
  "hero-solver": 140,
  "file-to-rules": 128,
  "precheck-fix": 96,
};

const POSTER: Record<ClipKey, StaticImageData> = {
  "quick-reserve-light": quickReserveLight,
  "quick-reserve-dark": quickReserveDark,
  "hero-solver-light": heroSolverLight,
  "hero-solver-dark": heroSolverDark,
  "file-to-rules-light": fileToRulesLight,
  "file-to-rules-dark": fileToRulesDark,
  "precheck-fix-light": precheckFixLight,
  "precheck-fix-dark": precheckFixDark,
};

type PlayerProps = {
  src: object;
  autoplay?: boolean;
  loop?: boolean;
  segment?: readonly [number, number];
  subscriptions?: { complete?: () => void };
  lottieRef?: React.Ref<LottieHandle>;
  rendererSettings?: { preserveAspectRatio?: string };
  className?: string;
};
type Player = ComponentType<PlayerProps>;

/** Code-split loaders (nothing here is in a first load). Called through the object so tests can observe them. */
export const heroLoaders = {
  player: (): Promise<Player> => import("lottie-react").then((m) => m.LottieLight as unknown as Player),
  data: {
    "quick-reserve-light": () => import("@/assets/lottie/quick-reserve-light.json") as Promise<unknown>,
    "quick-reserve-dark": () => import("@/assets/lottie/quick-reserve-dark.json") as Promise<unknown>,
    "hero-solver-light": () => import("@/assets/lottie/hero-solver-light.json") as Promise<unknown>,
    "hero-solver-dark": () => import("@/assets/lottie/hero-solver-dark.json") as Promise<unknown>,
    "file-to-rules-light": () => import("@/assets/lottie/file-to-rules-light.json") as Promise<unknown>,
    "file-to-rules-dark": () => import("@/assets/lottie/file-to-rules-dark.json") as Promise<unknown>,
    "precheck-fix-light": () => import("@/assets/lottie/precheck-fix-light.json") as Promise<unknown>,
    "precheck-fix-dark": () => import("@/assets/lottie/precheck-fix-dark.json") as Promise<unknown>,
  } satisfies Record<ClipKey, () => Promise<unknown>>,
};

/** Once per page load (module state, not storage: a reload may play it again). */
let playedThisLoad = false;
/** Tests only: forget that the hero played. */
export function resetHeroPlayedForTests() {
  playedThisLoad = false;
}

type Connection = { saveData?: boolean; addEventListener?: (t: "change", f: () => void) => void; removeEventListener?: (t: "change", f: () => void) => void };
const connection = (): Connection | undefined => (typeof navigator === "undefined" ? undefined : (navigator as Navigator & { connection?: Connection }).connection);
const REDUCED_DATA = "(prefers-reduced-data: reduce)";

function useSaveData(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const c = connection();
      c?.addEventListener?.("change", onChange);
      const mql = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(REDUCED_DATA) : null;
      mql?.addEventListener?.("change", onChange);
      return () => {
        c?.removeEventListener?.("change", onChange);
        mql?.removeEventListener?.("change", onChange);
      };
    },
    () => connection()?.saveData === true || (typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(REDUCED_DATA).matches),
    () => false,
  );
}

type Loaded = { key: ClipKey; Player: Player; data: object };
type HeroState = "waiting" | "playing" | "done" | "poster";

export function WelcomeHero({ audience, className }: { audience: Audience; className?: string }) {
  const { resolvedTheme } = useTheme();
  const hydrated = useHydrated();
  const reduce = useReduce();
  const saveData = useSaveData();
  const theme: Theme = hydrated && resolvedTheme === "dark" ? "dark" : "light";
  const clip = HERO_CLIP[audience];
  const key: ClipKey = `${clip}-${theme}`;
  const frame = HERO_POSTER_FRAME[clip];

  // decided once per mount: play only if motion is welcome and nothing has played in this page load
  const [mayPlay] = useState(() => !playedThisLoad);
  const [startedKey, setStartedKey] = useState<ClipKey | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  const [done, setDone] = useState(false);
  const handle = useRef<LottieHandle>(null);
  const wantsMotion = hydrated && mayPlay && !reduce && !saveData;

  useEffect(() => {
    if (!wantsMotion || startedKey) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      playedThisLoad = true;
      setStartedKey(key);
      Promise.all([heroLoaders.player(), heroLoaders.data[key]()])
        .then(([Player, mod]) => {
          if (!cancelled) setLoaded({ key, Player, data: ((mod as { default?: object }).default ?? mod) as object });
        })
        .catch(() => {
          if (!cancelled) setFailed(true);
        });
    }, WELCOME_SHEET_SETTLE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [wantsMotion, startedKey, key]);

  // the poster whenever the clip cannot (or must not) play: reduced motion / Save-Data / played before / failed /
  // the theme changed after it started (no replay)
  const showPlayer = wantsMotion && !failed && loaded !== null && loaded.key === key;
  const waiting = wantsMotion && !failed && (startedKey === null || startedKey === key) && !showPlayer;
  const state: HeroState = showPlayer ? (done ? "done" : "playing") : waiting ? "waiting" : "poster";

  return (
    <div
      aria-hidden
      data-testid="welcome-hero"
      data-clip={clip}
      data-state={state}
      className={cn("pointer-events-none relative h-[132px] w-full shrink-0 overflow-hidden rounded-2xl bg-fill-3 sm:h-[150px] [@media(max-height:480px)]:hidden", className)}
    >
      {!hydrated || state === "waiting" ? null : showPlayer && loaded ? (
        <motion.div className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={welcomeMotion.heroIn}>
          <loaded.Player
            src={loaded.data}
            autoplay
            loop={false}
            segment={[0, frame]}
            lottieRef={handle}
            rendererSettings={{ preserveAspectRatio: "xMidYMid slice" }}
            subscriptions={{
              complete: () => {
                handle.current?.pause();
                handle.current?.seek({ frame });
                setDone(true);
              },
            }}
            className="size-full"
          />
        </motion.div>
      ) : (
        <Image src={POSTER[key]} alt="" fill sizes="(max-width: 640px) 100vw, 576px" className="object-cover" />
      )}
    </div>
  );
}
