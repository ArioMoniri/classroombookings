/**
 * WG-09 motion pass on the surfaces WG-F built (welcome-guide.md §8.1): the sheet opens in 240 ms (not the shared
 * 270–280 ms springs) and carries the audience's Lottie hero; under reduced motion nothing on the sheet, the
 * checklist or the badges starts offset, scaled or transparent (end state at once); the tour's step card scales in
 * from `@starting-style` and drops that under reduced motion.
 */
import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChecklistPanel } from "./checklist/checklist-list";
import { buildChecklist, buildSheet } from "./model";
import { DESKTOP_MEDIA, makeState, mockMedia, PHONE_MEDIA, renderWelcome, resetWelcomeStore } from "./test-helpers";
import { TourCard, TourCardContext } from "./tour/tour-card";
import { resetHeroPlayedForTests } from "./welcome-hero";
import { WelcomeSheet } from "./welcome-sheet";

vi.setConfig({ testTimeout: 20_000 });
vi.mock("next/navigation", () => ({ usePathname: () => "/reserve", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("lottie-react", () => ({ LottieLight: () => <div data-testid="lottie-mock" /> }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return { ...real, request: async (path: string) => (path === "/auth/me" ? { id: 7, full_name: "Ayşe Tekin", role: "TEACHER", permissions: [] } : null) };
});

const original = window.matchMedia;
beforeEach(() => {
  resetWelcomeStore();
  resetHeroPlayedForTests();
  document.documentElement.removeAttribute("data-motion");
});
afterEach(() => {
  window.matchMedia = original;
  document.documentElement.removeAttribute("data-motion");
});

const sheet = (state = makeState()) => <WelcomeSheet open model={buildSheet(state)!} state={state} tourEnabled checklistEnabled onAction={() => undefined} />;
/** an inline style that starts a surface offset, scaled or invisible */
const OFFSET = /translate|scale\((?!1\))|opacity:\s*0(?![.\d])/;

describe("welcome sheet motion", () => {
  it("desktop: the dialog opens on --dur-slow (240 ms) for both the scale and the phone slide; the hero is the audience's clip", async () => {
    mockMedia(DESKTOP_MEDIA);
    renderWelcome(sheet(), { state: makeState() });
    const content = await screen.findByTestId("welcome-sheet");
    expect(content.className).toContain("[--spring-glass-morph-ms:var(--dur-slow)]");
    expect(content.className).toContain("[--spring-sheet-ms:var(--dur-slow)]");
    const hero = screen.getByTestId("welcome-hero");
    expect(hero).toHaveAttribute("aria-hidden", "true");
    expect(hero).toHaveAttribute("data-clip", "quick-reserve");
  });

  it("desktop, reduced motion: the cards are at rest on the first frame (no offset, no fade)", async () => {
    document.documentElement.dataset.motion = "reduced";
    mockMedia(DESKTOP_MEDIA);
    renderWelcome(sheet(), { state: makeState() });
    const cards = await screen.findByTestId("welcome-cards");
    for (const li of Array.from(cards.querySelectorAll("li"))) expect(li.getAttribute("style") ?? "", "card li").not.toMatch(OFFSET);
    expect(screen.getByTestId("welcome-hero")).toHaveAttribute("data-state", "poster");
  });

  it("desktop, motion on: the cards start 8 px low and transparent (first reveal)", async () => {
    mockMedia(DESKTOP_MEDIA);
    renderWelcome(sheet(), { state: makeState() });
    const cards = await screen.findByTestId("welcome-cards");
    const first = cards.querySelector("li")!;
    expect(first.getAttribute("style") ?? "").toMatch(/opacity:\s*0/);
  });

  it("phone, reduced motion: the pager card is not offset", async () => {
    document.documentElement.dataset.motion = "reduced";
    mockMedia(PHONE_MEDIA);
    renderWelcome(sheet(), { state: makeState() });
    const content = await screen.findByTestId("welcome-sheet");
    expect(content).toHaveAttribute("data-variant", "pager");
    const group = content.querySelector('[aria-roledescription]')!;
    expect(group.firstElementChild?.getAttribute("style") ?? "").not.toMatch(/translate/);
  });
});

describe("checklist motion under reduced motion", () => {
  it("ticks, the bar and the all-done disc show their end state at once", async () => {
    document.documentElement.dataset.motion = "reduced";
    mockMedia(DESKTOP_MEDIA);
    const state = makeState({
      checklist: {
        items: [
          { key: "profile", done: true },
          { key: "first_booking", done: true },
          { key: "channel", done: true },
          { key: "calendar", done: true },
          { key: "requests_seen", done: true, manual: true },
        ],
        hidden: false,
      },
    });
    const model = buildChecklist(state, new Set())!;
    renderWelcome(<ChecklistPanel model={model} />, { state });
    const done = await screen.findByTestId("checklist-all-done");
    expect(done.innerHTML).not.toMatch(/scale\((?!1\))|opacity:\s*0(?![.\d])/);
    const rows = screen.getByTestId("checklist-rows");
    // the drawn check paths are complete (no partial dash offset)
    for (const p of Array.from(rows.querySelectorAll("path"))) expect(p.getAttribute("stroke-dashoffset") ?? "0").toMatch(/^0(px)?$/);
  });
});

describe("tour step card motion", () => {
  it("scales in from @starting-style in --dur-fast, from the bottom edge when docked; none under reduced motion", () => {
    const target = document.createElement("button");
    document.body.appendChild(target);
    const value = { step: { id: "nav-reserve", target, title: "Rezervasyon", body: "Boş bir saati seçin.", interactive: false }, controls: { index: 0, total: 3, next: () => undefined, back: () => undefined, end: () => undefined }, docked: true, bodyId: "b" };
    renderWelcome(
      <TourCardContext.Provider value={value}>
        <TourCard />
      </TourCardContext.Provider>,
    );
    const card = screen.getByTestId("tour-card");
    expect(card.className).toContain("starting:scale-[.98]");
    expect(card.className).toContain("duration-(--dur-fast)");
    expect(card.className).toContain("origin-bottom");
    expect(card.className).toContain("motion-reduce:transition-none");
    target.remove();
  });
});
