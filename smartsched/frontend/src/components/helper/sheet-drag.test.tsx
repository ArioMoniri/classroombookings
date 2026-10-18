/**
 * HX-19 (audit m11, helper.md §7, motion.md §3.21): the phone helper sheet's drag-to-dismiss and exit timing.
 * - A 44 px labelled grab handle (not a Tab stop: keyboard users keep ✕ and Esc); a tap on it closes.
 * - Release past 30 % of the height or a downward flick closes, the focus returns to the opener; otherwise it springs
 *   back (springs.sheet with the release velocity) — instantly under reduced motion.
 * - Exits are ≤ 200 ms and never slower than the enter (springs.sheet ≈ 270 ms); reduced motion closes instantly.
 */
import { act, fireEvent, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi, type HelperStatus } from "@/lib/api/helper";
import { cssSpring, dur, ease } from "@/lib/motion";
import { HelperSheet } from "./helper-sheet";
import { useHelperStore } from "./helper-store";
import { calcGeneratorDuration, spring } from "motion";
import { helperSheetEnter, helperSheetExit, useHelperSheetDrag } from "./sheet-drag";
import { renderHelper, resetHelperStore } from "./test-helpers";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ can: () => true, perms: [] }),
  useMeFull: () => ({ data: { id: 1, permissions: [] }, isLoading: false }),
}));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));

function media(desktop: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: q.includes("min-width: 1024px") ? desktop : false,
    media: q,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const status: HelperStatus = { mode: "index", enabled: true, reason: null, provider_kind: null, provider_label: null, fallback_active: false, message: null } as unknown as HelperStatus;

let now = 0;
beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  vi.restoreAllMocks();
  delete document.documentElement.dataset.motion;
  now = 0;
  vi.spyOn(helperApi, "status").mockResolvedValue(status);
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
  vi.spyOn(helperApi, "memory").mockResolvedValue({ institution_enabled: true, enabled: false, notes: 0, max_notes: 20, max_chars: 200, retention_days: 180, history_days: 30 });
});
afterEach(() => {
  delete document.documentElement.dataset.motion;
});

async function openPhoneSheet() {
  media(false);
  const view = renderHelper(
    <>
      <button type="button">Ara veya sor</button>
      <main id="main" tabIndex={-1} />
      <HelperSheet />
    </>,
  );
  const opener = view.getByText("Ara veya sor");
  opener.focus();
  act(() => useHelperStore.getState().openSheet({ opener }));
  const sheet = await screen.findByTestId("helper-sheet");
  vi.spyOn(sheet, "getBoundingClientRect").mockReturnValue({ height: 800, width: 390, top: 0, left: 0, right: 390, bottom: 800, x: 0, y: 0, toJSON: () => ({}) } as DOMRect);
  const handle = screen.getByTestId("helper-handle");
  return { opener, sheet, handle };
}

/** Drag the handle from y 100 by `dy` px; the last move is `lastMs` after the one before it. */
function drag(handle: HTMLElement, dy: number, { totalMs = 600, lastMs = 200 } = {}) {
  const clock = vi.spyOn(performance, "now").mockImplementation(() => now);
  now = 0;
  fireEvent.pointerDown(handle, { pointerId: 1, button: 0, clientY: 100 });
  now = totalMs - lastMs;
  fireEvent.pointerMove(handle, { pointerId: 1, clientY: 100 + dy / 2 });
  now = totalMs;
  fireEvent.pointerMove(handle, { pointerId: 1, clientY: 100 + dy });
  fireEvent.pointerUp(handle, { pointerId: 1, clientY: 100 + dy });
  fireEvent.click(handle);
  // jsdom's requestAnimationFrame (focus return) needs the real clock once the gesture is over
  clock.mockRestore();
}

describe("HB18-F08: the open settles inside the 300 ms motion-audit ceiling", () => {
  // motion runs a spring as one WAAPI animation lasting until the spring is at rest: springs.sheet with the default
  // rest thresholds lasted 550 ms on opacity 0 → 1 and 650 ms on y 844 → 0 (the audit's "500 ms finite animation")
  const settle = (from: number, to: number, t: Record<string, unknown>) => calcGeneratorDuration(spring({ keyframes: [from, to], ...(t as object) }));
  it("desktop: opacity on a ≤ 180 ms tween, x 24 → 0 on the sheet spring within 300 ms", () => {
    const t = helperSheetEnter({ reduce: false, desktop: true }) as Record<string, Record<string, unknown>>;
    expect(t.opacity).toMatchObject({ duration: dur.fast });
    expect(settle(24, 0, t.x!)).toBeLessThanOrEqual(300);
  });
  it("phone: y 100 % (844 px) → 0 within 300 ms, the same spring shape", () => {
    const t = helperSheetEnter({ reduce: false, desktop: false }) as Record<string, Record<string, unknown>>;
    expect(settle(844, 0, t.y!)).toBeLessThanOrEqual(300);
    expect(t.y).toMatchObject({ type: "spring", stiffness: 300, damping: 30 });
  });
  it("reduced motion: the reduced tween", () => {
    expect(helperSheetEnter({ reduce: true, desktop: true })).toMatchObject({ duration: expect.any(Number) });
  });
});

describe("HX-19 exit timing", () => {
  const enter = cssSpring.sheet.ms / 1000;
  it.each([
    ["close", false],
    ["drag", false],
    ["close", true],
  ] as const)("%s exit (desktop %s) is ≤ 200 ms and faster than the enter, on tokens", (kind, desktop) => {
    const exit = helperSheetExit(kind, { reduce: false, desktop });
    const t = exit.transition as { duration: number; ease: readonly number[] };
    expect(t.duration).toBeLessThanOrEqual(0.2);
    expect(t.duration).toBeLessThan(enter);
    expect(Object.values(dur)).toContain(t.duration);
    expect([ease.in, ease.out]).toContainEqual(t.ease);
  });
  it("phone: the button / Esc exit slides down with --ease-in; the drag exit continues the flick with --ease-out", () => {
    expect(helperSheetExit("close", { reduce: false, desktop: false })).toMatchObject({ y: "100%", transition: { duration: dur.base, ease: ease.in } });
    expect(helperSheetExit("drag", { reduce: false, desktop: false })).toMatchObject({ y: "100%", transition: { duration: dur.fast, ease: ease.out } });
    expect(helperSheetExit("close", { reduce: false, desktop: true })).toMatchObject({ x: 24, opacity: 0, transition: { duration: dur.fast, ease: ease.in } });
  });
  it("reduced motion: every close is instant and has no travel", () => {
    for (const kind of ["close", "drag"] as const)
      for (const desktop of [true, false]) {
        const exit = helperSheetExit(kind, { reduce: true, desktop });
        expect(exit.transition).toMatchObject({ duration: 0 });
        expect(exit).not.toHaveProperty("x");
        expect(exit).not.toHaveProperty("y");
      }
  });
});

describe("HX-19 phone drag-to-dismiss", () => {
  it("has a labelled 44 px handle that is not a Tab stop (✕ stays first, Esc still closes)", async () => {
    const { handle, sheet } = await openPhoneSheet();
    expect(handle.tagName).toBe("BUTTON");
    expect(handle).toHaveAccessibleName("Kapat (aşağı sürükleyin)");
    expect(handle.className).toContain("h-11");
    expect(handle.className).toContain("touch-none");
    expect(handle).toHaveAttribute("tabindex", "-1");
    expect(screen.getByTestId("helper-close")).toHaveAccessibleName("Kapat");
    fireEvent.keyDown(sheet, { key: "Escape" });
    await waitFor(() => expect(useHelperStore.getState().open).toBe(false));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Ara veya sor"));
  });

  it("a release past 30 % of the height closes it and the focus returns to the opener", async () => {
    const { opener } = await openPhoneSheet();
    drag(screen.getByTestId("helper-handle"), 300);
    expect(useHelperStore.getState().open).toBe(false);
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("a fast downward flick closes it even when short", async () => {
    const { handle } = await openPhoneSheet();
    drag(handle, 60, { totalMs: 60, lastMs: 20 });
    expect(useHelperStore.getState().open).toBe(false);
  });

  it("a short slow drag springs back and keeps the sheet open (the trailing click does not close it)", async () => {
    const { handle } = await openPhoneSheet();
    drag(handle, 120, { totalMs: 1200, lastMs: 400 });
    expect(useHelperStore.getState().open).toBe(true);
    expect(handle).not.toHaveAttribute("data-dragging");
  });

  it("an upward drag does nothing", async () => {
    const { handle } = await openPhoneSheet();
    drag(handle, -300, { totalMs: 60, lastMs: 20 });
    expect(useHelperStore.getState().open).toBe(true);
  });

  it("a tap (or a screen-reader activation) on the handle closes it", async () => {
    const { opener, handle } = await openPhoneSheet();
    fireEvent.click(handle);
    expect(useHelperStore.getState().open).toBe(false);
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("reduced motion: the drag still closes past the threshold", async () => {
    document.documentElement.dataset.motion = "reduced";
    const { handle } = await openPhoneSheet();
    drag(handle, 300);
    expect(useHelperStore.getState().open).toBe(false);
  });

  it("desktop has no handle", async () => {
    media(true);
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet({ opener: null }));
    await screen.findByTestId("helper-sheet");
    expect(screen.queryByTestId("helper-handle")).toBeNull();
  });
});

describe("HX-19 useHelperSheetDrag", () => {
  function setup(reduce: boolean) {
    const el = document.createElement("div");
    el.getBoundingClientRect = () => ({ height: 800 }) as DOMRect;
    const ref = { current: el };
    const onDismiss = vi.fn();
    vi.spyOn(performance, "now").mockImplementation(() => now);
    const { result } = renderHook(() => useHelperSheetDrag(ref, { reduce, onDismiss }));
    const target = { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn(), hasPointerCapture: () => true };
    const ev = (clientY: number) => ({ pointerId: 1, button: 0, pointerType: "touch", clientY, currentTarget: target }) as unknown as React.PointerEvent<HTMLButtonElement>;
    return { el, result, onDismiss, ev };
  }

  it("follows the finger 1:1 (no lag) and sets will-change only during the gesture", () => {
    const { el, result, ev } = setup(false);
    act(() => result.current.handle.onPointerDown(ev(100)));
    expect(el.style.willChange).toBe("transform");
    now = 50;
    act(() => result.current.handle.onPointerMove(ev(180)));
    expect(result.current.y.get()).toBe(80);
    now = 2000;
    act(() => result.current.handle.onPointerUp(ev(180)));
    expect(el.style.willChange).toBe("");
  });

  it("full motion: the snap-back is a spring from the release point (not a jump)", async () => {
    const { result, ev, onDismiss } = setup(false);
    act(() => result.current.handle.onPointerDown(ev(100)));
    now = 1000;
    act(() => result.current.handle.onPointerMove(ev(200)));
    now = 2000;
    act(() => result.current.handle.onPointerUp(ev(200)));
    expect(onDismiss).not.toHaveBeenCalled();
    expect(result.current.y.get()).not.toBe(0);
    await waitFor(() => expect(Number(result.current.y.get())).toBeCloseTo(0, 0), { timeout: 2000 });
  });

  it("reduced motion: the snap-back is instant", () => {
    const { result, ev } = setup(true);
    act(() => result.current.handle.onPointerDown(ev(100)));
    now = 1000;
    act(() => result.current.handle.onPointerMove(ev(200)));
    now = 2000;
    act(() => result.current.handle.onPointerUp(ev(200)));
    expect(result.current.y.get()).toBe(0);
  });

  it("a pointer cancel springs back and never dismisses", () => {
    const { result, ev, onDismiss } = setup(true);
    act(() => result.current.handle.onPointerDown(ev(100)));
    now = 10;
    act(() => result.current.handle.onPointerMove(ev(600)));
    act(() => result.current.handle.onPointerCancel(ev(600)));
    expect(onDismiss).not.toHaveBeenCalled();
    expect(result.current.y.get()).toBe(0);
  });
});
