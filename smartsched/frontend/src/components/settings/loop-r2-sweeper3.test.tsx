/** Flow-loop round 2, sweeper 3 (item 2): on /profile "Takvim eşitleme kurumunuzda kapalı." is a quiet note, not a
 * role=status live region: screen readers and the testers heard it announced like a toast on pages that never touched
 * calendar sync. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/profile",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string) => {
    if (path === "/calendar/sync") return { enabled: false, feeds: { tokens: [], url_templates: { mine: "", room: "", department: "" } }, connectors: [] };
    if (path === "/me/consents/calendar_sync") return [];
    throw new Error(`unexpected ${path}`);
  },
}));

import { CalendarConnectionsSection } from "./calendar-connections";

describe("sweeper 3: calendar sync off on /profile", () => {
  it("renders the 'off' note as plain text with no live region", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <CalendarConnectionsSection />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const off = await screen.findByTestId("calendar-connections-off");
    expect(off).toHaveTextContent("Takvim eşitleme kurumunuzda kapalı");
    expect(off).not.toHaveAttribute("role");
    expect(off).not.toHaveAttribute("aria-live");
    expect(off.closest("[role=status],[role=alert],[aria-live]")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
