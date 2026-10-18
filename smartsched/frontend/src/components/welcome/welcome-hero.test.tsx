/**
 * WG-09 (welcome-guide.md §8.1 "Lottie hero", §8.2): the welcome sheet's hero. Decorative (aria-hidden, no pointer
 * events, no glass). After the sheet settles (240 ms) it loads the player + the audience's clip and plays ONE pass
 * 0 → poster frame, then holds the poster frame. At most once per page load. Reduced motion (OS or in-app), Save-Data,
 * a load failure or a theme switch mid-play → the static poster PNG, and under reduced motion nothing is requested.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WELCOME_SHEET_SETTLE_MS } from "./motion";
import { HERO_CLIP, HERO_POSTER_FRAME, heroLoaders, resetHeroPlayedForTests, WelcomeHero } from "./welcome-hero";

type MockProps = { src: { layers: { nm?: string }[] }; loop?: boolean; autoplay?: boolean; segment?: readonly [number, number]; subscriptions?: { complete?: () => void }; lottieRef?: { current: unknown }; rendererSettings?: { preserveAspectRatio?: string } };
const lot = vi.hoisted(() => ({ props: null as unknown, handle: { pause: () => undefined, seek: (target: unknown) => void target } }));
vi.mock("lottie-react", () => ({
  LottieLight: (p: MockProps) => {
    lot.props = p;
    if (p.lottieRef) p.lottieRef.current = lot.handle;
    return <div data-testid="lottie-mock" />;
  },
}));
const themeState = vi.hoisted(() => ({ resolved: "light" as "light" | "dark" | undefined }));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: themeState.resolved, theme: "system", setTheme: () => undefined }) }));

const original = window.matchMedia;
function setMedia(m: Record<string, boolean>) {
  window.matchMedia = (query: string) =>
    ({ matches: !!m[query], media: query, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList;
}

describe("WelcomeHero (welcome-guide.md §8.2)", () => {
  beforeEach(() => {
    lot.props = null;
    themeState.resolved = "light";
    resetHeroPlayedForTests();
    document.documentElement.removeAttribute("data-motion");
    Object.defineProperty(navigator, "connection", { value: undefined, configurable: true });
    setMedia({});
  });
  afterEach(() => {
    window.matchMedia = original;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("maps audiences to clips: the new quick-reserve clip for academicians, staff, department admins and approvers", () => {
    expect(HERO_CLIP.academician).toBe("quick-reserve");
    expect(HERO_CLIP.staff).toBe("quick-reserve");
    expect(HERO_CLIP.dept_admin).toBe("quick-reserve");
    expect(HERO_CLIP.approver).toBe("quick-reserve");
    expect(HERO_CLIP.viewer).toBe("hero-solver");
    expect(HERO_CLIP.planner).toBe("file-to-rules");
    expect(HERO_CLIP.admin).toBe("precheck-fix");
    expect(HERO_POSTER_FRAME["quick-reserve"]).toBe(86);
  });

  it("plays one pass 0 → poster frame after the sheet settles, decorative, then holds the poster frame", async () => {
    const player = vi.spyOn(heroLoaders, "player");
    const data = vi.spyOn(heroLoaders.data, "quick-reserve-light");
    const t0 = performance.now();
    render(<WelcomeHero audience="academician" />);
    const hero = screen.getByTestId("welcome-hero");
    expect(hero).toHaveAttribute("aria-hidden", "true");
    expect(hero.className).toContain("pointer-events-none");
    expect(hero.className).not.toMatch(/backdrop-blur|glass-(thin|regular|thick|chrome)/);
    expect(hero).toHaveAttribute("data-clip", "quick-reserve");
    // nothing loads while the sheet is still opening
    expect(player).not.toHaveBeenCalled();
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    expect(performance.now() - t0).toBeGreaterThanOrEqual(WELCOME_SHEET_SETTLE_MS - 5);
    expect(player).toHaveBeenCalledTimes(1);
    expect(data).toHaveBeenCalledTimes(1);
    const p = lot.props as MockProps;
    expect(p.segment).toEqual([0, 86]);
    expect(p.loop).toBe(false);
    expect(p.autoplay).toBe(true);
    // cropped like the poster (object-cover), so the hand-off to the poster frame never jumps
    expect(p.rendererSettings?.preserveAspectRatio).toBe("xMidYMid slice");
    expect(hero).toHaveAttribute("data-state", "playing");
    const pause = vi.spyOn(lot.handle, "pause");
    const seek = vi.spyOn(lot.handle, "seek");
    act(() => p.subscriptions?.complete?.());
    expect(hero).toHaveAttribute("data-state", "done");
    expect(pause).toHaveBeenCalled();
    expect(seek).toHaveBeenCalledWith({ frame: 86 });
  });

  it("plays at most once per page load: the next open shows the poster and requests nothing", async () => {
    const first = render(<WelcomeHero audience="staff" />);
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    first.unmount();
    const player = vi.spyOn(heroLoaders, "player");
    render(<WelcomeHero audience="staff" />);
    const hero = screen.getByTestId("welcome-hero");
    expect(hero).toHaveAttribute("data-state", "poster");
    expect(hero.querySelector("img")).not.toBeNull();
    await new Promise((r) => setTimeout(r, WELCOME_SHEET_SETTLE_MS + 60));
    expect(player).not.toHaveBeenCalled();
  });

  it("reduced motion (in-app switch) → the poster at once, no player request, no entry motion", async () => {
    document.documentElement.dataset.motion = "reduced";
    const player = vi.spyOn(heroLoaders, "player");
    render(<WelcomeHero audience="academician" />);
    const hero = screen.getByTestId("welcome-hero");
    expect(hero).toHaveAttribute("data-state", "poster");
    const img = hero.querySelector("img");
    expect(img).not.toBeNull();
    expect(img!.getAttribute("src")).toContain("quick-reserve-light-poster");
    expect(hero.innerHTML).not.toMatch(/opacity:\s*0/);
    await new Promise((r) => setTimeout(r, WELCOME_SHEET_SETTLE_MS + 60));
    expect(player).not.toHaveBeenCalled();
  });

  it("reduced motion (OS query) → the poster, no player request", async () => {
    setMedia({ "(prefers-reduced-motion: reduce)": true });
    const player = vi.spyOn(heroLoaders, "player");
    render(<WelcomeHero audience="planner" />);
    expect(screen.getByTestId("welcome-hero")).toHaveAttribute("data-state", "poster");
    await new Promise((r) => setTimeout(r, WELCOME_SHEET_SETTLE_MS + 60));
    expect(player).not.toHaveBeenCalled();
  });

  it("Save-Data → the poster, no player request", async () => {
    Object.defineProperty(navigator, "connection", { value: { saveData: true }, configurable: true });
    const player = vi.spyOn(heroLoaders, "player");
    render(<WelcomeHero audience="admin" />);
    expect(screen.getByTestId("welcome-hero")).toHaveAttribute("data-state", "poster");
    await new Promise((r) => setTimeout(r, WELCOME_SHEET_SETTLE_MS + 60));
    expect(player).not.toHaveBeenCalled();
  });

  it("a failed load falls back to the poster", async () => {
    vi.spyOn(heroLoaders, "player").mockRejectedValue(new Error("chunk"));
    render(<WelcomeHero audience="viewer" />);
    const hero = screen.getByTestId("welcome-hero");
    await vi.waitFor(() => expect(hero).toHaveAttribute("data-state", "poster"), { timeout: 3000 });
    expect(hero.querySelector("img")).not.toBeNull();
  });

  it("a theme switch mid-play shows the new theme's poster instead of replaying", async () => {
    const view = render(<WelcomeHero audience="academician" />);
    await screen.findByTestId("lottie-mock", undefined, { timeout: 3000 });
    const player = vi.spyOn(heroLoaders, "player");
    themeState.resolved = "dark";
    view.rerender(<WelcomeHero audience="academician" />);
    const hero = screen.getByTestId("welcome-hero");
    expect(hero).toHaveAttribute("data-state", "poster");
    expect(hero.querySelector("img")!.getAttribute("src")).toContain("quick-reserve-dark-poster");
    expect(player).not.toHaveBeenCalled();
  });
});
