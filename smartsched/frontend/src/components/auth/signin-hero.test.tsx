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
import { HERO_DELAY_MS, HERO_SEGMENT, heroLoaders, SignInHero } from "./signin-hero";
import { SignInShell } from "./signin-shell";

type MockProps = { src: { layers: { nm?: string }[] }; loop?: boolean; autoplay?: boolean; segment?: readonly [number, number]; subscriptions?: { complete?: () => void }; lottieRef?: { current: unknown } };
const lot = vi.hoisted(() => ({ props: null as unknown, handle: { pause: () => undefined, seek: (target: unknown) => void target } }));
vi.mock("lottie-react", () => ({
  LottieLight: (p: MockProps) => {
    lot.props = p;
    if (p.lottieRef) p.lottieRef.current = lot.handle;
    return <div data-testid="lottie-mock" />;
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
const themeState = vi.hoisted(() => ({ resolved: "light" as "light" | "dark" | undefined }));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: themeState.resolved, theme: "system", setTheme: () => undefined }) }));

let media: Record<string, boolean> = {};
function setMedia(m: Record<string, boolean>) {
  media = m;
  window.matchMedia = (query: string) =>
    ({ matches: !!media[query], media: query, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList;
}
const WIDE = "(min-width: 1024px)";
const original = window.matchMedia;

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
    expect(p.autoplay).toBe(true);
    // the opaque page-colour background layer is dropped over the tint frame
    expect(p.src.layers.some((l) => l.nm === "background")).toBe(false);
    expect(hero).toHaveAttribute("data-state", "playing");
    const pause = vi.spyOn(lot.handle, "pause");
    const seek = vi.spyOn(lot.handle, "seek");
    act(() => p.subscriptions?.complete?.());
    expect(hero).toHaveAttribute("data-state", "done");
    expect(pause).toHaveBeenCalled();
    expect(seek).toHaveBeenCalledWith({ frame: 140 });
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
    themeState.resolved = "dark";
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
    themeState.resolved = "dark";
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
