/**
 * Flow-loop round 1, lane A, T-R1-06 (R1-A-31, R1-A-37, R1-A-40): the phone tab bar marks "Diğer" current on its
 * routes and lists Taleplerim for an academician with the badge after the label; the user menu hides the keyboard
 * entry on touch; the shortcuts sheet prints the platform's modifier (Ctrl on Linux) and "g t" → Taleplerim.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";

const nav = vi.hoisted(() => ({ pathname: "/moderation/me" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { ShortcutsSheet } from "./shortcuts-sheet";
import { TabBar } from "./tab-bar";
import { UserMenu } from "./user-menu";

const ACADEMICIAN = ["book_single.create", "book_recur.create", "room.view"];
const APPROVER = [...ACADEMICIAN, "approvals.decide"];
const PLANNER = [...ACADEMICIAN, "planning.view", "planning.edit"];

function stubFetch(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "akademisyen@uni.edu.tr", username: "akademisyen", full_name: "A. T.", role: "TEACHER", permissions });
      if (path === "/api/v1/requests/meetings") return json({ items: [], total: 3, page: 1, page_size: 1 });
      if (path === "/api/v1/approvals/inbox") return json([{ id: 1 }, { id: 2 }]);
      if (path === "/api/v1/health") return json({ version: "1.4.0" });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/runs" || path === "/api/v1/terms") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

function mockPointer(coarse: boolean) {
  const real = window.matchMedia;
  vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ ...real(q), matches: q === "(pointer: coarse)" ? coarse : false, media: q }));
}

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const tabs = () => within(screen.getByRole("navigation", { name: "Sekmeler" })).getAllByRole("link");

describe("tab bar (MOBILE.md M-09)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("an academician gets Taleplerim as a tab, and it is the one current item on /moderation/me", async () => {
    nav.pathname = "/moderation/me";
    stubFetch(ACADEMICIAN);
    wrap(<TabBar />);
    await waitFor(() => expect(screen.getByTestId("tab-nav-moderation-me")).toBeInTheDocument());
    // the bookings tabs as before (Boş derslik bul and Onaylar stay under Diğer), plus Taleplerim
    // W3-SLOT follow-up: "Rezerve et" (/reserve) leads the bookings tabs
    expect(tabs().map((a) => a.getAttribute("href"))).toEqual(["/reserve", "/bookings", "/my-bookings", "/moderation/me"]);
    const navEl = screen.getByRole("navigation", { name: "Sekmeler" });
    const current = [...navEl.querySelectorAll("[aria-current]")];
    expect(current.map((e) => e.getAttribute("data-testid"))).toEqual(["tab-nav-moderation-me"]);
    // the label leads the accessible name and the text
    expect(screen.getByTestId("tab-nav-moderation-me")).toHaveAttribute("aria-label", "Taleplerim");
  });

  it("on a route without a tab (Profil) exactly one item is current: Diğer", async () => {
    nav.pathname = "/profile";
    stubFetch(ACADEMICIAN);
    wrap(<TabBar />);
    await waitFor(() => expect(screen.getByTestId("open-drawer")).toBeInTheDocument());
    const navEl = screen.getByRole("navigation", { name: "Sekmeler" });
    const current = [...navEl.querySelectorAll("[aria-current]")];
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute("data-testid", "open-drawer");
  });

  it("a planner's tab bar is unchanged (no Taleplerim; Talepler's count comes after its label)", async () => {
    nav.pathname = "/requests";
    stubFetch(PLANNER);
    wrap(<TabBar />);
    await waitFor(() => expect(screen.getByTestId("tab-nav-requests")).toBeInTheDocument());
    expect(tabs().map((a) => a.getAttribute("href"))).toEqual(["/dashboard", "/requests", "/generate", "/timetable"]);
    const requests = screen.getByTestId("tab-nav-requests");
    await waitFor(() => expect(within(requests).getByTestId("tab-badge")).toHaveTextContent("3"));
    // DOM order: label before badge, so innerText starts with the label
    expect(requests.textContent?.startsWith("Talepler")).toBe(true);
    expect(requests.textContent).toBe("Talepler3");
    expect(requests).toHaveAttribute("aria-label", "Talepler, 3 inceleme bekliyor");
  });

  it("an approver who can book has the same four tabs; /approvals is a Diğer route, so Diğer is current there", async () => {
    nav.pathname = "/approvals";
    stubFetch(APPROVER);
    wrap(<TabBar />);
    await waitFor(() => expect(screen.getByTestId("tab-nav-moderation-me")).toBeInTheDocument());
    expect(tabs()).toHaveLength(4);
    const navEl = screen.getByRole("navigation", { name: "Sekmeler" });
    expect([...navEl.querySelectorAll("[aria-current]")].map((e) => e.getAttribute("data-testid"))).toEqual(["open-drawer"]);
  });
});

describe("user menu on touch (R1-A-37)", () => {
  beforeEach(() => stubFetch(ACADEMICIAN));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("hides 'Klavye kısayolları' on a coarse pointer and keeps it on a fine one", async () => {
    mockPointer(true);
    wrap(<UserMenu compact />);
    await userEvent.click(screen.getByTestId("user-menu"));
    expect(await screen.findByTestId("user-menu-profile")).toBeInTheDocument();
    expect(screen.queryByTestId("user-menu-shortcuts")).toBeNull();
  });
  it("fine pointer", async () => {
    mockPointer(false);
    wrap(<UserMenu compact />);
    await userEvent.click(screen.getByTestId("user-menu"));
    expect(await screen.findByTestId("user-menu-shortcuts")).toBeInTheDocument();
  });
});

describe("shortcuts sheet (R1-A-40)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("prints Ctrl K on a non-Apple platform and lists g t → Taleplerim for an academician", async () => {
    stubFetch(ACADEMICIAN);
    useUiStore.getState().setShortcutsOpen(true);
    wrap(<ShortcutsSheet />);
    const sheet = await screen.findByTestId("shortcuts-sheet");
    const kbds = [...sheet.querySelectorAll("kbd")].map((k) => k.getAttribute("aria-label"));
    expect(kbds[0]).toBe("Ctrl + K");
    expect(sheet.textContent).not.toContain("⌘");
    await waitFor(() => expect(sheet.textContent).toContain("Taleplerim sayfasına git"));
    expect(kbds.concat([...sheet.querySelectorAll("kbd")].map((k) => k.getAttribute("aria-label")))).toContain("G sonra T");
    expect(sheet.textContent).not.toContain("Takvim sayfasına git");
    useUiStore.getState().setShortcutsOpen(false);
  });
});
