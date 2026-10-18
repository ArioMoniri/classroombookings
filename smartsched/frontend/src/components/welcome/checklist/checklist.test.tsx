/** WG-06 checklist: progress text and progressbar values, the server's done wins, rows' accessible state, mark done, hide, the pill. */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { welcomeKeys } from "@/lib/api/welcome";
import { DESKTOP_MEDIA, makeState, mockMedia, renderWelcome, resetWelcomeStore } from "../test-helpers";
import { useWelcomeStore } from "../welcome-store";
import { ChecklistHomeCard } from "./checklist-home-card";
import { ChecklistPill } from "./checklist-pill";

// the first test pays the cold transform of the shell modules on a shared, loaded host
vi.setConfig({ testTimeout: 20_000 });

const api = vi.hoisted(() => ({ events: [] as unknown[] }));
vi.mock("next/navigation", () => ({ usePathname: () => "/reserve", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { body?: unknown } = {}) => {
      if (path === "/welcome/events") api.events.push(opts.body);
      if (path === "/auth/me") return { id: 1, permissions: [] };
      if (path === "/welcome") throw new real.HttpError(503, "down");
      return undefined;
    },
  };
});

const state = (over: Record<string, unknown> = {}) =>
  makeState({
    checklist: {
      items: [
        { key: "profile", done: true },
        { key: "first_booking", done: false },
        { key: "channel", done: false },
        { key: "calendar", done: true },
        { key: "requests_seen", done: false, manual: true },
      ],
      hidden: false,
      ...over,
    },
  });

beforeEach(() => {
  resetWelcomeStore();
  mockMedia(DESKTOP_MEDIA);
  api.events = [];
});

describe("checklist", () => {
  it("home card: '5 adımdan 2'si tamam', progressbar values, rows named with their state", () => {
    renderWelcome(<ChecklistHomeCard />, { state: state() });
    expect(screen.getByTestId("checklist-progress-text")).toHaveTextContent("5 adımdan 2 tanesi tamam");
    const bar = screen.getByTestId("checklist-progress");
    expect(bar).toHaveAttribute("role", "progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "5");
    expect(screen.getByRole("link", { name: "Profilinizi tamamlayın, tamamlandı" })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("link", { name: "İlk rezervasyonunuzu yapın, yapılacak" })).toHaveAttribute("href", "/reserve");
    expect(screen.getByTestId("checklist-item-profile")).toHaveAttribute("data-done", "true");
  });

  it("'Bitti olarak işaretle' only on view-only items; it posts item_done", async () => {
    renderWelcome(<ChecklistHomeCard />, { state: state() });
    expect(screen.queryByTestId("checklist-mark-first_booking")).toBeNull();
    fireEvent.click(screen.getByTestId("checklist-mark-requests_seen"));
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "checklist", event: "item_done", item: "requests_seen" }));
    expect(screen.getByTestId("checklist-item-requests_seen")).toHaveAttribute("data-done", "true");
  });

  it("a tick from the server announces '{öğe} tamamlandı' once", async () => {
    const { qc } = renderWelcome(<ChecklistHomeCard />, { state: state() });
    qc.setQueryData(welcomeKeys.state, state({ items: [{ key: "profile", done: true }, { key: "first_booking", done: true }, { key: "channel", done: false }, { key: "calendar", done: true }, { key: "requests_seen", done: false, manual: true }] }));
    await waitFor(() => expect(screen.getByTestId("checklist-live")).toHaveTextContent("İlk rezervasyonunuzu yapın tamamlandı"));
    expect(screen.getByTestId("checklist-progress-text")).toHaveTextContent("5 adımdan 3 tanesi tamam");
  });

  it("'Gizle' posts hidden; a hidden or switched-off list renders nothing", async () => {
    const { unmount } = renderWelcome(<ChecklistHomeCard />, { state: state() });
    fireEvent.click(screen.getByTestId("checklist-hide"));
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "checklist", event: "hidden" }));
    unmount();
    renderWelcome(<ChecklistHomeCard />, { state: state({ hidden: true }) });
    expect(screen.queryByTestId("checklist-home-card")).toBeNull();
  });

  it("switched off: nothing", () => {
    renderWelcome(<ChecklistPill />, { state: makeState({ enabled: { sheet: true, tour: true, checklist: false, hints: true } }) });
    expect(screen.queryByTestId("checklist-pill")).toBeNull();
  });

  it("the sidebar pill: 'Başlarken 2 / 5', 'Sıradaki', aria-expanded, opens the panel", async () => {
    renderWelcome(<ChecklistPill />, { state: state() });
    const pill = screen.getByTestId("checklist-pill");
    expect(pill).toHaveAccessibleName("Başlarken, 5 adımdan 2 tanesi tamam");
    expect(pill).toHaveTextContent("Sıradaki: İlk rezervasyonunuzu yapın");
    expect(pill).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(pill);
    expect(await screen.findByTestId("checklist-panel")).toBeInTheDocument();
    expect(useWelcomeStore.getState().checklistOpen).toBe(true);
    expect(pill).toHaveAttribute("aria-expanded", "true");
  });

  it("all done: the success state", () => {
    renderWelcome(<ChecklistPill />, { state: state({ items: [{ key: "profile", done: true }, { key: "first_booking", done: true }] }) });
    fireEvent.click(screen.getByTestId("checklist-pill"));
    expect(screen.getByTestId("checklist-all-done")).toHaveTextContent("Hepsi tamam. Listeyi gizleyebilirsiniz.");
  });
});
