/**
 * AUX-10 (docs/design/v3/auth.md §11.3–§11.4): the sign-in hero. It plays once (frames 0 → 140) only at ≥ 1024 px, after
 * idle + 300 ms, then holds the poster frame. Reduced motion or Save-Data → the poster PNG. Hidden < 1024, in forced
 * colours and when not mounted (the 2FA step). Decorative: aria-hidden, pointer-events none.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { I18nProvider } from "@/lib/i18n/provider";
import { createHeroDriver, HERO_DELAY_MS, HERO_FPS, HERO_SEGMENT, heroClock, heroLoaders, SignInHero } from "./signin-hero";
import { SignInShell } from "./signin-shell";

type MockProps = { src: { layers: { nm?: string }[] }; loop?: boolean; autoplay?: boolean; segment?: readonly [number, number]; subscriptions?: { complete?: () => void; ready?: () => void }; lottieRef?: { current: unknown } };

/** A hand-driven animation clock: `frame(t)` runs the pending requestAnimationFrame callback at time t (ms). */
function manualClock() {
  let pending: ((t: number) => void) | null = null;
  vi.spyOn(heroClock, "raf").mockImplementation((cb: (t: number) => void) => {
    pending = cb;
    return 1;
  });
  vi.spyOn(heroClock, "caf").mockImplementation(() => {
    pending = null;
  });
  return {
    frame: (t: number) => {
      const cb = pending;
      pending = null;
      cb?.(t);
    },
    pending: () => pending !== null,
  };
}
const lot = vi.hoisted(() => ({ props: null as unknown, renders: 0, handle: { pause: () => undefined, seek: (target: unknown) => void target } }));
vi.mock("lottie-react", () => ({
  LottieLight: (p: MockProps) => {
    lot.props = p;
    lot.renders += 1;
    if (p.lottieRef) p.lottieRef.current = lot.handle;
    return <div data-testid="lottie-mock" />;
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
// a store, as next-themes' context is: a theme change re-renders its readers (the hero is memoised, so a bare
// rerender with a changed module variable would not reach it)
const themeState = vi.hoisted(() => ({
  resolved: "light" as "light" | "dark" | undefined,
  listeners: new Set<() => void>(),
  set(v: "light" | "dark" | undefined) {
    this.resolved = v;
    this.listeners.forEach((l) => l());
  },
}));
vi.mock("next-themes", async () => {
  const { useSyncExternalStore } = await import("react");
  const subscribe = (cb: () => void) => {
    themeState.listeners.add(cb);
    return () => void themeState.listeners.delete(cb);
  };
  return {
    useTheme: () => {
      const resolvedTheme = useSyncExternalStore(subscribe, () => themeState.resolved);
      return { resolvedTheme, theme: "system", setTheme: () => undefined };
    },
  };
});

let media: Record<string, boolean> = {};
function setMedia(m: Record<string, boolean>) {
  media = m;
  window.matchMedia = (query: string) =>
    ({ matches: !!media[query], media: query, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList;
}
const WIDE = "(min-width: 1024px)";
const original = window.matchMedia;

describe("createHeroDriver (AUX-10: the hero yields to input)", () => {
  function make() {
    let pending: ((t: number) => void) | null = null;
    const seek = vi.fn();
    const pause = vi.fn();
    const onDone = vi.fn();
    const busy = { input: false };
    const d = createHeroDriver({ seek, pause, onDone, raf: (cb) => ((pending = cb), 1), caf: () => (pending = null), inputPending: () => busy.input });
    const frame = (t: number) => {
      const cb = pending;
      pending = null;
      cb?.(t);
    };
    return { d, seek, pause, onDone, frame, busy, pending: () => pending !== null };
  }
  it("steps whole frames at 30 fps from the first frame's time and seeks only when the frame changes", () => {
    const { d, seek, frame } = make();
    d.start();
    frame(100);
    frame(110);
    frame(120);
    expect(seek.mock.calls).toEqual([[0]]);
    frame(100 + 1000);
    expect(seek).toHaveBeenLastCalledWith(30);
  });
  it("skips the frame after an input event or while the browser reports pending input, at most 4 frames in a row", () => {
    const { d, seek, frame, busy } = make();
    d.start();
    frame(0);
    seek.mockClear();
    d.noteInput();
    frame(100);
    expect(seek).not.toHaveBeenCalled();
    busy.input = true;
    frame(117);
    frame(134);
    frame(151);
    expect(seek).not.toHaveBeenCalled();
    frame(168);
    expect(seek).toHaveBeenLastCalledWith(5);
  });
  it("ends on the poster frame, pauses, reports done once and asks for no more frames", () => {
    const { d, seek, pause, onDone, frame, pending } = make();
    d.start();
    frame(0);
    frame(4600);
    frame(5000);
    expect(seek).toHaveBeenLastCalledWith(140);
    expect(pause).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(pending()).toBe(false);
  });
  it("stop() cancels the next frame", () => {
    const { d, frame, seek, pending } = make();
    d.start();
    frame(0);
    d.stop();
    expect(pending()).toBe(false);
    frame(1000);
    expect(seek).toHaveBeenCalledTimes(1);
  });
});

describe("SignInHero (auth.md §11.3)", () => {
  beforeEach(() => {
    lot.props = null;
    themeState.resolved = "light";
    document.documentElement.removeAttribute("data-motion");
    Object.defineProperty(navigator, "connection", { value: undefined, configurable: true });
  });
  afterEach(() => {
    window.matchMedia = original;
    vi.restoreAllMocks();
  });

  it("plays one pass of frames 0→140 at ≥ 1024 px after idle + 300 ms, decorative, then holds the poster frame", async () => {
    setMedia({ [WIDE]: true });
    const player = vi.spyOn(heroLoaders, "player");
    const t0 = performance.now();
    render(<SignInHero />);
    const hero = screen.getByTestId("signin-hero");
    expect(hero).toHaveAttribute("aria-hidden", "true");
    expect(hero.className).toContain("pointer-events-none");
    expect(hero.className).toContain("forced-colors:hidden");
    expect(hero.className).not.toMatch(/backdrop-blur|glass-(thin|regular|thick|chrome)/);
    // nothing loads in the first frames: the form wins
    expect(player).not.toHaveBeenCalled();
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    expect(performance.now() - t0).toBeGreaterThanOrEqual(HERO_DELAY_MS - 5);
    expect(player).toHaveBeenCalledTimes(1);
    const p = lot.props as MockProps;
    expect(HERO_SEGMENT).toEqual([0, 140]);
    expect(p.segment).toEqual([0, 140]);
    expect(p.loop).toBe(false);
    // AUX-10 typing fix: the hero's own clock steps the frames (so it can yield to typing), not lottie's autoplay
    expect(p.autoplay).toBe(false);
    // the opaque page-colour background layer is dropped over the tint frame
    expect(p.src.layers.some((l) => l.nm === "background")).toBe(false);
    expect(hero).toHaveAttribute("data-state", "playing");
    const clock = manualClock();
    const pause = vi.spyOn(lot.handle, "pause");
    const seek = vi.spyOn(lot.handle, "seek");
    act(() => p.subscriptions?.ready?.());
    act(() => clock.frame(1000));
    expect(seek).toHaveBeenLastCalledWith({ frame: 0 });
    act(() => clock.frame(2000));
    expect(seek).toHaveBeenLastCalledWith({ frame: HERO_FPS });
    expect(hero).toHaveAttribute("data-state", "playing");
    act(() => clock.frame(1000 + (140 / HERO_FPS) * 1000));
    expect(hero).toHaveAttribute("data-state", "done");
    expect(pause).toHaveBeenCalled();
    expect(seek).toHaveBeenLastCalledWith({ frame: 140 });
    // held: no further frames are asked for (never loops)
    expect(clock.pending()).toBe(false);
  });

  it("a keystroke while it plays: the hero skips its work in that frame and catches up on time (one pass ≤ 5 s)", async () => {
    setMedia({ [WIDE]: true });
    render(<SignInHero />);
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    const p = lot.props as MockProps;
    const clock = manualClock();
    const seek = vi.spyOn(lot.handle, "seek");
    act(() => p.subscriptions?.ready?.());
    act(() => clock.frame(0));
    act(() => clock.frame(500));
    expect(seek).toHaveBeenLastCalledWith({ frame: 15 });
    seek.mockClear();
    // the identifier field gets a key: the frame that handles it draws nothing of the hero
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
    });
    act(() => clock.frame(533));
    expect(seek).not.toHaveBeenCalled();
    // the next frame draws where the time says, not where the skipped frame was (no delay builds up)
    act(() => clock.frame(550));
    expect(seek).toHaveBeenLastCalledWith({ frame: 16 });
    act(() => clock.frame(140 / HERO_FPS * 1000));
    expect(screen.getByTestId("signin-hero")).toHaveAttribute("data-state", "done");
  });

  it("typing in the form never re-renders the hero (it is memoised, its props are stable)", async () => {
    setMedia({ [WIDE]: true });
    lot.renders = 0;
    const wrapLocal = (node: ReactNode) => (
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">{node}</I18nProvider>
      </QueryClientProvider>
    );
    const { rerender } = render(wrapLocal(<SignInShell hero testId="p"><p>a</p></SignInShell>));
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    const before = lot.renders;
    for (const text of ["ay", "ays", "ayse"]) rerender(wrapLocal(<SignInShell hero testId="p"><p>{text}</p></SignInShell>));
    expect(lot.renders).toBe(before);
  });

  it("below 1024 px renders nothing and never requests the Lottie bundle", async () => {
    setMedia({ [WIDE]: false });
    const player = vi.spyOn(heroLoaders, "player");
    render(<SignInHero />);
    expect(screen.queryByTestId("signin-hero")).toBeNull();
    await new Promise((r) => setTimeout(r, HERO_DELAY_MS + 100));
    expect(player).not.toHaveBeenCalled();
  });

  it("in forced colours renders nothing", () => {
    setMedia({ [WIDE]: true, "(forced-colors: active)": true });
    render(<SignInHero />);
    expect(screen.queryByTestId("signin-hero")).toBeNull();
  });

  it.each([
    ["the OS reduced-motion query", () => setMedia({ [WIDE]: true, "(prefers-reduced-motion: reduce)": true })],
    ["the in-app Reduce motion switch", () => {
      setMedia({ [WIDE]: true });
      document.documentElement.dataset.motion = "reduced";
    }],
    ["Save-Data", () => {
      setMedia({ [WIDE]: true });
      Object.defineProperty(navigator, "connection", { value: { saveData: true, addEventListener: () => undefined, removeEventListener: () => undefined }, configurable: true });
    }],
  ])("%s shows the static poster PNG and loads no player", async (_label, arrange) => {
    arrange();
    const player = vi.spyOn(heroLoaders, "player");
    render(<SignInHero />);
    const hero = screen.getByTestId("signin-hero");
    expect(hero).toHaveAttribute("data-state", "poster");
    const img = hero.querySelector("img");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("alt", "");
    await new Promise((r) => setTimeout(r, HERO_DELAY_MS + 100));
    expect(player).not.toHaveBeenCalled();
    expect(screen.queryByTestId("lottie-mock")).toBeNull();
  });

  it("a theme switch after the pass started shows the new theme's poster instead of replaying", async () => {
    setMedia({ [WIDE]: true });
    const data = vi.spyOn(heroLoaders.data, "dark");
    const { rerender } = render(<SignInHero />);
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    act(() => themeState.set("dark"));
    rerender(<SignInHero />);
    const hero = screen.getByTestId("signin-hero");
    expect(hero).toHaveAttribute("data-state", "poster");
    expect(screen.queryByTestId("lottie-mock")).toBeNull();
    expect(hero.querySelector("img")?.getAttribute("src")).toContain("dark");
    expect(data).not.toHaveBeenCalled();
  });

  it("the theme is read when the pass starts (next-themes resolves after mount): dark plays the dark file", async () => {
    setMedia({ [WIDE]: true });
    themeState.resolved = undefined;
    const dark = vi.spyOn(heroLoaders.data, "dark");
    const { rerender } = render(<SignInHero />);
    act(() => themeState.set("dark"));
    rerender(<SignInHero />);
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    expect(dark).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("signin-hero")).toHaveAttribute("data-state", "playing");
  });

  it("falls back to the poster when the player fails to load", async () => {
    setMedia({ [WIDE]: true });
    vi.spyOn(heroLoaders, "player").mockRejectedValue(new Error("chunk"));
    render(<SignInHero />);
    await waitFor(() => expect(screen.getByTestId("signin-hero")).toHaveAttribute("data-state", "poster"), { timeout: 3000 });
  });

  it("unmounting before the delay cancels the load (the 2FA step replaces /login)", async () => {
    setMedia({ [WIDE]: true });
    const player = vi.spyOn(heroLoaders, "player");
    const { unmount } = render(<SignInHero />);
    unmount();
    await new Promise((r) => setTimeout(r, HERO_DELAY_MS + 100));
    expect(player).not.toHaveBeenCalled();
  });
});

describe("SignInShell hero mount (scene area)", () => {
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>
  );
  afterEach(() => {
    window.matchMedia = original;
  });

  it("/login passes `hero`: the hero sits in the scene, outside the sheet", () => {
    setMedia({ [WIDE]: true });
    render(wrap(<SignInShell hero testId="p"><p>form</p></SignInShell>));
    const hero = screen.getByTestId("signin-hero");
    expect(screen.getByTestId("signin-sheet").contains(hero)).toBe(false);
  });

  it("the 2FA step and setup (no `hero` prop) show no hero", () => {
    setMedia({ [WIDE]: true });
    render(wrap(<SignInShell testId="verify-page"><p>code</p></SignInShell>));
    expect(screen.queryByTestId("signin-hero")).toBeNull();
  });
});
