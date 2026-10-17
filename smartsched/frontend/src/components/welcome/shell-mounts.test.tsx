/**
 * The guide's mount points in the shell (WG-04…WG-07): the provider and the page slot in the app shell, `data-tour`
 * anchors on the nav entries and the user menu, the "Başlarken" pill in the sidebar footer, the Yardım group in the
 * user menu, the ⌘K commands, the phone "Daha" rows, the "Yeni" badge, and the shortcuts paused while a tour runs.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { makeState, mockMedia, resetWelcomeStore } from "./test-helpers";
import { TOUR_RUNNING_ATTR } from "./tour/anchors";

const nav = vi.hoisted(() => ({ pathname: "/reserve" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from "@/components/shell/app-shell";

const TEACHER = ["book_single.create", "book_recur.create", "room.view"];
let welcome: unknown = makeState();

function stubFetch(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "ayse@uni.edu.tr", username: "ayse", full_name: "Ayşe Tekin", role: "TEACHER", permissions });
      if (path === "/api/v1/welcome") return json(welcome);
      if (path === "/api/v1/welcome/events") return new Response(null, { status: 204 });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/approvals/inbox") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="tr">
        <AppShell>
          <h1>Hızlı rezervasyon</h1>
        </AppShell>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const checklist = { items: [{ key: "profile", done: true }, { key: "first_booking", done: false }, { key: "channel", done: false }], hidden: false };

beforeEach(() => {
  resetWelcomeStore();
  // cmdk scrolls the selected item into view (jsdom has no layout)
  Element.prototype.scrollIntoView = vi.fn();
  nav.pathname = "/reserve";
  welcome = makeState({ checklist, hints: [{ key: "hint.quick_reserve" }] });
  useUiStore.setState({ paletteOpen: false, drawerOpen: false, sidebarCollapsed: false });
  mockMedia((q) => q.includes("min-width: 1024px"));
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute(TOUR_RUNNING_ATTR);
});

describe("welcome guide in the shell", () => {
  it("nav entries and the user menu carry their data-tour anchors; the sidebar footer has the pill; the home card and the 'Yeni' badge show", async () => {
    stubFetch(TEACHER);
    renderShell();
    const aside = await screen.findByRole("complementary", {}, { timeout: 15_000 });
    await waitFor(() => expect(aside.querySelector('[data-tour="nav-reserve"]')).not.toBeNull(), { timeout: 15_000 });
    expect(aside.querySelector('[data-tour="nav-my-bookings"]')).not.toBeNull();
    expect(aside.querySelector('[data-tour="nav-my-requests"]')).not.toBeNull();
    expect(aside.querySelector('[data-tour="user-menu"]')).not.toBeNull();
    expect(await within(aside).findByTestId("checklist-pill", {}, { timeout: 15_000 })).toHaveTextContent("1 / 3");
    expect(await screen.findByTestId("checklist-home-card")).toBeInTheDocument();
    expect(within(aside).getByTestId("new-badge-quick_reserve")).toHaveTextContent("Yeni");
  }, 30_000);

  it("the user menu's Yardım group restarts the guide and opens the checklist", async () => {
    stubFetch(TEACHER);
    renderShell();
    const aside = await screen.findByRole("complementary", {}, { timeout: 15_000 });
    await within(aside).findByTestId("checklist-pill", {}, { timeout: 15_000 });
    await userEvent.click(within(aside).getByTestId("user-menu"));
    expect(await screen.findByText("Yardım")).toBeInTheDocument();
    expect(screen.getByTestId("help-checklist")).toHaveTextContent("Başlarken listesi (1 / 3)");
    expect(screen.getByTestId("help-whats-new")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("help-restart-tour"));
    expect(await screen.findByTestId("welcome-sheet", {}, { timeout: 5000 })).toBeInTheDocument();
  }, 30_000);

  it("⌘K lists 'Turu yeniden başlat' and 'Başlarken listesi'", async () => {
    stubFetch(TEACHER);
    renderShell();
    const aside = await screen.findByRole("complementary", {}, { timeout: 15_000 });
    await within(aside).findByTestId("checklist-pill", {}, { timeout: 15_000 });
    act(() => useUiStore.getState().setPaletteOpen(true));
    const input = await screen.findByPlaceholderText(/./, { selector: "input" });
    await userEvent.type(input, ">tur");
    expect(await screen.findByText("Turu yeniden başlat")).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, ">başlarken");
    expect(await screen.findByText("Başlarken listesi")).toBeInTheDocument();
  }, 30_000);

  it("the phone 'Daha' sheet starts with the checklist row, then Yardım", async () => {
    mockMedia((q) => q.includes("max-width") || q.includes("coarse"));
    stubFetch(TEACHER);
    renderShell();
    await screen.findByTestId("checklist-home-card", {}, { timeout: 15_000 });
    act(() => useUiStore.getState().setDrawerOpen(true));
    const row = await screen.findByTestId("drawer-checklist");
    expect(row).toHaveAccessibleName("Başlarken, 3 adımdan 1 tanesi tamam");
    expect(screen.getByTestId("drawer-welcome")).toContainElement(screen.getAllByTestId("help-restart-tour")[0]!);
  }, 30_000);

  it("while a tour runs, the global shortcuts and ⌘K are paused", async () => {
    stubFetch(TEACHER);
    renderShell();
    await waitFor(() => expect(document.documentElement.getAttribute("data-shortcuts")).toBe("armed"), { timeout: 15_000 });
    document.documentElement.setAttribute(TOUR_RUNNING_ATTR, "");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(useUiStore.getState().paletteOpen).toBe(false);
    document.documentElement.removeAttribute(TOUR_RUNNING_ATTR);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(useUiStore.getState().paletteOpen).toBe(true);
  }, 30_000);
});
