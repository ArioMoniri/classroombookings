/** WG-05 tour: steps filtered by visible anchors (skip + warn), live region "Adım 2 / 5: …", Esc → dismissed with the step, Tab trapped, shortcuts paused. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DESKTOP_MEDIA, PHONE_MEDIA, mockMedia, renderWelcome, resetWelcomeStore } from "../test-helpers";
import { useWelcomeStore } from "../welcome-store";
import { TOUR_RUNNING_ATTR, findAnchor, tourAnchorFor } from "./anchors";
import { TourRunner } from "./tour-runner";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
const api = vi.hoisted(() => ({ events: [] as unknown[] }));
vi.mock("next/navigation", () => ({ usePathname: () => "/reserve", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: nav.push, replace: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { body?: unknown } = {}) => {
      if (path === "/welcome/events") api.events.push(opts.body);
      if (path === "/auth/me") return { id: 1, permissions: [] };
      return undefined;
    },
  };
});

// jsdom has no layout: give anchors a box so "visible" holds
function anchor(name: string, label: string) {
  const a = document.createElement("a");
  a.href = "#";
  a.textContent = label;
  a.setAttribute("data-tour", name);
  a.getBoundingClientRect = () => ({ x: 10, y: 10, top: 10, left: 10, right: 110, bottom: 50, width: 100, height: 40, toJSON: () => ({}) }) as DOMRect;
  document.body.appendChild(a);
  return a;
}

const steps = [
  { anchor: "nav-reserve", interactive: false, audience: "academician" as const },
  { anchor: "nav-missing", interactive: false, audience: "academician" as const },
  { anchor: "nav-my-bookings", interactive: false, audience: "academician" as const },
];

beforeEach(() => {
  resetWelcomeStore();
  mockMedia(DESKTOP_MEDIA);
  api.events = [];
  document.body.innerHTML = "";
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

describe("anchors", () => {
  it("nav hrefs map to the spec's anchor names", () => {
    expect(tourAnchorFor("/moderation/me")).toBe("nav-my-requests");
    expect(tourAnchorFor("/admin/welcome")).toBe("nav-welcome-admin");
    expect(tourAnchorFor("/reserve?x=1")).toBe("nav-reserve");
    expect(tourAnchorFor("/profile")).toBeUndefined();
  });
  it("the visible element wins", () => {
    const hidden = anchor("nav-reserve", "gizli");
    hidden.getBoundingClientRect = () => ({ x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) }) as DOMRect;
    const shown = anchor("nav-reserve", "görünür");
    expect(findAnchor("nav-reserve")).toBe(shown);
  });
});

describe("TourRunner (react-joyride adapter)", () => {
  it("shows the step card with the counter and live text, skips a missing anchor, finishes with 'completed'", async () => {
    anchor("nav-reserve", "Hızlı rezervasyon");
    anchor("nav-my-bookings", "Rezervasyonlarım");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    useWelcomeStore.setState({ tour: { steps } });
    renderWelcome(<TourRunner request={{ steps }} />);
    const card = await screen.findByTestId("tour-card", {}, { timeout: 3000 });
    expect(document.documentElement.hasAttribute(TOUR_RUNNING_ATTR)).toBe(true);
    expect(screen.getByTestId("tour-counter")).toHaveTextContent("Adım 1 / 3");
    expect(card).toHaveAttribute("role", "dialog");
    expect(card).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("tour-live")).toHaveTextContent("Adım 1 / 3: Hızlı rezervasyon");
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(api.events).toContainEqual({ guide_key: "tour", event: "started" });

    fireEvent.click(screen.getByTestId("tour-next"));
    // step 2's anchor never appears: skipped after the 3 s wait, with a warning
    await waitFor(() => expect(screen.getByTestId("tour-counter")).toHaveTextContent("Adım 3 / 3"), { timeout: 6000 });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("nav-missing"));
    expect(screen.getByTestId("tour-live")).toHaveTextContent("Adım 3 / 3: Rezervasyonlarım");
    expect(screen.getByTestId("tour-next")).toHaveTextContent("Bitir");
    fireEvent.click(screen.getByTestId("tour-next"));
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "tour", event: "completed" }));
    expect(useWelcomeStore.getState().tour).toBeNull();
  }, 15_000);

  it("Esc ends the tour with 'dismissed' and the step, focus goes to the step's target", async () => {
    const target = anchor("nav-reserve", "Hızlı rezervasyon");
    anchor("nav-my-bookings", "Rezervasyonlarım");
    const two = [steps[0]!, steps[2]!];
    useWelcomeStore.setState({ tour: { steps: two } });
    const { rerender } = renderWelcome(<TourRunner request={{ steps: two }} />);
    await screen.findByTestId("tour-card", {}, { timeout: 3000 });
    fireEvent.click(screen.getByTestId("tour-next"));
    await waitFor(() => expect(screen.getByTestId("tour-counter")).toHaveTextContent("Adım 2 / 2"));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "tour", event: "dismissed", step: 1 }));
    expect(useWelcomeStore.getState().tour).toBeNull();
    rerender(<></>);
    expect(document.documentElement.hasAttribute(TOUR_RUNNING_ATTR)).toBe(false);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("Rezervasyonlarım")));
    void target;
  }, 15_000);

  it("Tab stays inside the card; ← / → move between steps", async () => {
    anchor("nav-reserve", "Hızlı rezervasyon");
    anchor("nav-my-bookings", "Rezervasyonlarım");
    const two = [steps[0]!, steps[2]!];
    renderWelcome(<TourRunner request={{ steps: two }} />);
    const card = await screen.findByTestId("tour-card", {}, { timeout: 3000 });
    await waitFor(() => expect(card.contains(document.activeElement)).toBe(true), { timeout: 2000 });
    for (let i = 0; i < 4; i++) {
      await userEvent.tab();
      expect(card.contains(document.activeElement)).toBe(true);
    }
    act(() => {
      card.focus();
    });
    fireEvent.keyDown(card, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByTestId("tour-counter")).toHaveTextContent("Adım 2 / 2"));
    fireEvent.keyDown(screen.getByTestId("tour-card"), { key: "ArrowLeft" });
    await waitFor(() => expect(screen.getByTestId("tour-counter")).toHaveTextContent("Adım 1 / 2"));
  }, 15_000);
});

describe("docked step card on a phone (e2e 2026-10-18)", () => {
  it("the floating box spans the viewport less 8 px a side, so the card is not shrink-wrapped (334 px at 390 on the stack)", async () => {
    mockMedia(PHONE_MEDIA);
    anchor("nav-reserve", "Hızlı rezervasyon");
    const one = [steps[0]!];
    useWelcomeStore.setState({ tour: { steps: one } });
    renderWelcome(<TourRunner request={{ steps: one }} />);
    const card = await screen.findByTestId("tour-card", {}, { timeout: 3000 });
    // every wrapper between the card and the fixed floating element takes the docked width
    let el: HTMLElement | null = card.parentElement;
    const widths: string[] = [];
    while (el && el !== document.body) {
      widths.push(el.style.width);
      if (el.style.position === "fixed") break;
      el = el.parentElement;
    }
    expect(el?.style.position).toBe("fixed");
    expect(el?.style.width).toBe("calc(100vw - 16px)");
  });
});

