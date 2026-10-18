/**
 * Flow-loop round 2, lane A (T-R2-04 R2-A-01 / R2-S-07 / R2-M-13; T-R2-08 R2-A-14): the phone tab bar uses short
 * tab-only labels (nav.tab.*) that fit a 74 px / 59 px column, truncates as a safety net and keeps the badge inside the
 * item; the academician's /moderation/me crumb is "Taleplerim" alone. Same harness as shell-r1.test.tsx.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate, type MessageKey } from "@/lib/i18n";

const nav = vi.hoisted(() => ({ pathname: "/my-bookings" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { breadcrumbs } from "./breadcrumbs";
import { TabBar } from "./tab-bar";
import { useGlobalShortcuts } from "./use-global-shortcuts";

function Shortcuts() {
  useGlobalShortcuts();
  return null;
}

const ACADEMICIAN = ["book_single.create", "book_recur.create", "room.view"];
const PLANNER = [...ACADEMICIAN, "planning.view", "planning.edit"];

function stubFetch(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "akademisyen@uni.edu.tr", username: "akademisyen", full_name: "A. T.", role: "TEACHER", permissions });
      if (path === "/api/v1/requests/meetings") return json({ items: [], total: 139, page: 1, page_size: 1 });
      if (path === "/api/v1/approvals/inbox") return json([]);
      if (path === "/api/v1/health") return json({ version: "1.4.0" });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/runs" || path === "/api/v1/terms") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
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

describe("T-R2-04: tab-bar labels fit their column", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("a teacher's tabs read the short tab-only labels, and the label span wraps to two lines as the safety net", async () => {
    nav.pathname = "/my-bookings";
    stubFetch(ACADEMICIAN);
    wrap(<TabBar />);
    await waitFor(() => expect(tabs().length).toBeGreaterThanOrEqual(3));
    const names = tabs().map((a) => a.getAttribute("aria-label"));
    // W3-SLOT follow-up: "Rezerve et" (/reserve, the quick reservation) is the teacher's first tab
    expect(names).toEqual(["Rezerve et", "Takvim", "Benim", "Talepler"]); // F-MA-2: ≤ 8-letter words fit a 58 px column // the grid tab reads "Takvim", never confused with "Rezerve et"
    expect(tabs()[0]).toHaveAttribute("href", "/reserve");
    for (const a of tabs()) {
      const label = a.querySelector("[data-slot=tab-label]")!;
      // F-MA-2 (fix-b-2026-10-18): two centred lines, never an ellipsis (MOBILE.md M-09)
      expect(label).toHaveClass("min-w-0", "max-w-full", "line-clamp-2", "text-center");
      expect(label).not.toHaveClass("truncate");
      expect(a.textContent!.trim().startsWith(a.getAttribute("aria-label")!)).toBe(true);
    }
    // the tab-only keys are shorter than the sidebar words in both languages
    for (const [tab, full] of [["nav.tab.reserve", "quickReserve.title"], ["nav.tab.bookings", "crbs.nav.bookings"], ["nav.tab.myBookings", "crbs.nav.myBookings"], ["nav.tab.findRoom", "wave1.nav.findRoom"]] as [MessageKey, MessageKey][])
      for (const l of ["tr", "en"] as const) expect(translate(l, tab).length).toBeLessThan(translate(l, full).length + 1);
  });

  it("the planner's Talepler badge is anchored inside the item (right edge), clamps at 99+ and follows the label", async () => {
    nav.pathname = "/requests";
    stubFetch(PLANNER);
    wrap(<TabBar />);
    await waitFor(() => expect(screen.getByTestId("tab-badge")).toHaveTextContent("99+"));
    const badge = screen.getByTestId("tab-badge");
    expect(badge.className).toMatch(/right-\[/);
    expect(badge.className).not.toMatch(/left-\[calc\(50%/);
    const item = badge.closest("a")!;
    expect(item.textContent!.trim().startsWith("Talepler")).toBe(true);
  });
});

describe("T-R2-08: the academician's Taleplerim crumb", () => {
  const tr = (key: MessageKey, vars?: Record<string, string | number>) => translate("tr", key, vars);
  it("/moderation/me without planning.view is 'Taleplerim' alone; the planner's trail is unchanged; Geçmişim keeps its pair", () => {
    expect(breadcrumbs("/moderation/me", tr, { planner: false }).map((c) => c.label)).toEqual(["Taleplerim"]);
    expect(breadcrumbs("/moderation", tr, { planner: false }).map((c) => c.label)).toEqual(["Taleplerim"]);
    expect(breadcrumbs("/moderation/me", tr, { planner: true }).map((c) => c.label)).toEqual(["Moderasyon", "Taleplerim"]);
    expect(breadcrumbs("/moderation/me", tr).map((c) => c.label)).toEqual(["Moderasyon", "Taleplerim"]);
    expect(breadcrumbs("/moderation/people/157", tr, { planner: false, ownPersonId: 157 }).map((c) => c.label)).toEqual(["Taleplerim", "Geçmişim"]);
  });
  it("top-bar passes the planning permission into the crumb context", () => {
    expect(readFileSync(join(process.cwd(), "src/components/shell/top-bar.tsx"), "utf8")).toMatch(/planner = perms \? can\("planning\.view"\)/);
  });
});

describe("global shortcuts arm on mount (e2e gate: Shift+? flake)", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sets html[data-shortcuts=armed] as soon as the listener is attached and ? opens the sheet before any data loaded", async () => {
    stubFetch(ACADEMICIAN);
    const { unmount } = wrap(<Shortcuts />);
    expect(document.documentElement.getAttribute("data-shortcuts")).toBe("armed");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", shiftKey: true }));
    const { useUiStore } = await import("@/stores/ui");
    expect(useUiStore.getState().shortcutsOpen).toBe(true);
    unmount();
    expect(document.documentElement.getAttribute("data-shortcuts")).toBeNull();
  });
});
