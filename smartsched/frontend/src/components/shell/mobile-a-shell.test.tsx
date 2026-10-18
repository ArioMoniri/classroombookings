/**
 * Mobile audit A (2026-10-17) fix 14: on a phone narrower than 360 px (320 px reflow, small Android phones) the five
 * tab-bar items get the search circle's width and lose their side padding, so "Benimkiler" and "Taleplerim" are not
 * cut off; search moves to the top bar there. Same harness as shell-r2.test.tsx.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/my-bookings",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { TabBar } from "./tab-bar";

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "p.t@smartsched.local", username: "pt", full_name: "P. T.", role: "TEACHER", permissions: ["book_single.create", "room.view"] });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/approvals/inbox") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("mobile-a fix 14: the tab bar below 360 px", () => {
  it("hides the search circle and drops the items' side padding below 360 px", async () => {
    stubFetch();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nProvider initialLocale="tr">
          <TabBar />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const nav = await screen.findByRole("navigation", { name: "Sekmeler" });
    await waitFor(() => expect(within(nav).getAllByRole("link").length).toBeGreaterThanOrEqual(3));
    expect(screen.getByTestId("open-palette-mobile")).toHaveClass("max-[22.5rem]:hidden");
    // F-MA-2 (fix-b-2026-10-18): no side padding at any width now (the label gets the whole column)
    for (const a of within(nav).getAllByRole("link")) expect(a).toHaveClass("px-0");
  });
});
