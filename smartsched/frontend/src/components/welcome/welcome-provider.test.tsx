/** WG-04 provider: no call on excluded routes, the server's `show` once per session, never on a deep link, never over another dialog, events. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DESKTOP_MEDIA, makeState, mockMedia, renderWelcome, resetWelcomeStore } from "./test-helpers";
import { WelcomeProvider } from "./welcome-provider";
import { useWelcomeStore } from "./welcome-store";

const nav = vi.hoisted(() => ({ pathname: "/reserve", search: "", push: vi.fn() }));
const api = vi.hoisted(() => ({ calls: [] as { path: string; method: string; body?: unknown }[], state: {} as Record<string, unknown> }));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
      api.calls.push({ path, method: opts.method ?? "GET", body: opts.body });
      if (path === "/auth/me") return { id: 7, full_name: "Ayşe Tekin", role: "TEACHER", permissions: ["book_single.create"], force_password_reset: false };
      if (path === "/welcome") return opts.schema ? opts.schema.parse(api.state) : api.state;
      if (path === "/welcome/events") return undefined;
      throw new Error(`unexpected ${path}`);
    },
  };
});

const events = () => api.calls.filter((c) => c.path === "/welcome/events").map((c) => c.body as { guide_key: string; event: string });
const welcomeCalls = () => api.calls.filter((c) => c.path === "/welcome");

beforeEach(() => {
  resetWelcomeStore();
  mockMedia(DESKTOP_MEDIA);
  api.calls = [];
  api.state = makeState({ show: { kind: "sheet", key: "sheet" } });
  nav.pathname = "/reserve";
  nav.search = "";
});

describe("WelcomeProvider", () => {
  it("first sign-in on a home page: the sheet once, with a 'shown' event", async () => {
    renderWelcome(<WelcomeProvider />);
    expect(await screen.findByTestId("welcome-sheet", {}, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() => expect(events()).toContainEqual({ guide_key: "sheet", event: "shown" }));
    expect(window.sessionStorage.getItem("ss.welcome.auto")).toBe("sheet");
  });

  it("'Sonra' writes snoozed and the session budget keeps it closed on the next page", async () => {
    const { unmount } = renderWelcome(<WelcomeProvider />);
    fireEvent.click(await screen.findByTestId("welcome-later", {}, { timeout: 3000 }));
    await waitFor(() => expect(events()).toContainEqual({ guide_key: "sheet", event: "snoozed" }));
    unmount();
    resetWelcomeStore();
    window.sessionStorage.setItem("ss.welcome.auto", "sheet");
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(welcomeCalls().length).toBeGreaterThan(1));
    await act(async () => new Promise((r) => setTimeout(r, 600)));
    expect(screen.queryByTestId("welcome-sheet")).toBeNull();
  });

  it.each(["/setup", "/login", "/welcome", "/reset-password", "/public/rooms/3"])("no GET /welcome on %s", async (p) => {
    nav.pathname = p;
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(api.calls.some((c) => c.path === "/auth/me")).toBe(true));
    await act(async () => new Promise((r) => setTimeout(r, 200)));
    expect(welcomeCalls()).toHaveLength(0);
  });

  it("no GET /welcome on a kiosk / embed page", async () => {
    nav.pathname = "/bookings";
    nav.search = "kiosk=1";
    renderWelcome(<WelcomeProvider />);
    await act(async () => new Promise((r) => setTimeout(r, 300)));
    expect(welcomeCalls()).toHaveLength(0);
  });

  it("a deep link (/approvals/123) is never interrupted, and first_route is sent", async () => {
    nav.pathname = "/approvals/123";
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(welcomeCalls()).toHaveLength(1));
    await act(async () => new Promise((r) => setTimeout(r, 600)));
    expect(screen.queryByTestId("welcome-sheet")).toBeNull();
  });

  it("waits while another dialog is open", async () => {
    const other = document.createElement("div");
    other.setAttribute("role", "dialog");
    other.setAttribute("aria-modal", "true");
    document.body.appendChild(other);
    renderWelcome(<WelcomeProvider />);
    await act(async () => new Promise((r) => setTimeout(r, 900)));
    expect(screen.queryByTestId("welcome-sheet")).toBeNull();
    other.remove();
    expect(await screen.findByTestId("welcome-sheet", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("switched off by the institution: nothing", async () => {
    api.state = makeState({ enabled: { sheet: false, tour: true, checklist: true, hints: true }, show: { kind: "sheet" } });
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(welcomeCalls()).toHaveLength(1));
    await act(async () => new Promise((r) => setTimeout(r, 600)));
    expect(screen.queryByTestId("welcome-sheet")).toBeNull();
  });

  it("'Bir daha gösterme' writes dismissed; a card writes completed and navigates", async () => {
    renderWelcome(<WelcomeProvider />);
    fireEvent.click(await screen.findByTestId("welcome-never", {}, { timeout: 3000 }));
    await waitFor(() => expect(events()).toContainEqual({ guide_key: "sheet", event: "dismissed" }));
    act(() => useWelcomeStore.getState().openSheet({ mode: "restart", kind: "sheet" }));
    fireEvent.click(await screen.findByTestId("welcome-card-my_bookings"));
    await waitFor(() => expect(events()).toContainEqual({ guide_key: "sheet", event: "completed" }));
    expect(nav.push).toHaveBeenCalledWith("/my-bookings");
  });

  it("an admin preview writes no events", async () => {
    api.state = makeState({ show: null });
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(welcomeCalls()).toHaveLength(1));
    act(() => useWelcomeStore.getState().openSheet({ mode: "preview", kind: "sheet", audience: "admin" }));
    expect(await screen.findByTestId("welcome-sheet-title")).toHaveTextContent("Yönetim paneline hoş geldiniz");
    fireEvent.click(screen.getByTestId("welcome-later"));
    await act(async () => new Promise((r) => setTimeout(r, 100)));
    expect(events()).toHaveLength(0);
  });

  it("opening a view-only item's page posts item_done once", async () => {
    nav.pathname = "/moderation/me";
    api.state = makeState({ show: null, checklist: { items: [{ key: "requests_seen", done: false, manual: true }], hidden: false } });
    renderWelcome(<WelcomeProvider />);
    await waitFor(() => expect(api.calls.filter((c) => c.path === "/welcome/events").map((c) => c.body)).toContainEqual({ guide_key: "checklist", event: "item_done", item: "requests_seen" }));
  });
});
