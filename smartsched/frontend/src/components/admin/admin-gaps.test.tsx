/** UI gap audit 2026-10-08: the pure helpers and the shell banner behind the admin and shell fixes. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const nav = vi.hoisted(() => ({ pathname: "/admin" }));
const org = vi.hoisted(() => ({ data: undefined as Record<string, unknown> | undefined }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname, useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", async (orig) => ({ ...(await orig<typeof import("@/lib/api/crbs")>()), useOrgPublic: () => ({ data: org.data }) }));

import { weeksBetween } from "@/lib/api/crbs";
import { MaintenanceBanner } from "@/components/shell/app-shell";
import { allNavGroups } from "@/components/shell/nav-config";
import { holidayDays } from "./holidays-admin";

describe("holidayDays (CRBS holiday.field.duration: 1 + diff)", () => {
  it("counts both ends", () => {
    expect(holidayDays({ date_start: "2026-04-23", date_end: "2026-04-23" })).toBe(1);
    expect(holidayDays({ date_start: "2026-03-30", date_end: "2026-04-03" })).toBe(5);
    // across a month end (UTC day maths, no time-zone or summer-time drift)
    expect(holidayDays({ date_start: "2026-03-28", date_end: "2026-04-01" })).toBe(5);
  });
});

describe("weeksBetween (TermIn.week_count for a new session)", () => {
  it("rounds up to whole weeks, between 1 and 60", () => {
    expect(weeksBetween("2026-02-09", "2026-05-29")).toBe(16);
    expect(weeksBetween("2026-09-21", "2026-09-21")).toBe(1);
    expect(weeksBetween("2026-09-21", "2026-09-01")).toBe(1);
    expect(weeksBetween("2020-01-01", "2030-01-01")).toBe(60);
  });
});

describe("sidebar Users entry", () => {
  it("opens the full user screen, not the old settings tab", () => {
    const items = allNavGroups().flatMap((g) => g.items);
    const users = items.find((i) => i.labelKey === "nav.users");
    expect(users?.href).toBe("/admin/users");
    expect(items.some((i) => i.href.includes("tab=users"))).toBe(false);
  });
});

function renderBanner() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <MaintenanceBanner />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("MaintenanceBanner (CRBS layout.php: every page)", () => {
  beforeEach(() => {
    nav.pathname = "/admin";
    org.data = { maintenance_mode: true, maintenance_message: "Bu akşam 22:00'de bakım var." };
  });

  it("shows the organisation's message on any page", () => {
    nav.pathname = "/my-bookings";
    renderBanner();
    expect(screen.getByTestId("shell-maintenance")).toHaveTextContent("Bakım modu açık. Bu akşam 22:00'de bakım var.");
  });

  it("falls back to the default text", () => {
    org.data = { maintenance_mode: true, maintenance_message: null };
    renderBanner();
    expect(screen.getByTestId("shell-maintenance")).toHaveTextContent("Bakım modu açık.");
  });

  it("stays out of /bookings (its own 503 screen or bypass notice) and when maintenance is off", () => {
    nav.pathname = "/bookings";
    const { unmount } = renderBanner();
    expect(screen.queryByTestId("shell-maintenance")).toBeNull();
    unmount();
    nav.pathname = "/admin";
    org.data = { maintenance_mode: false };
    renderBanner();
    expect(screen.queryByTestId("shell-maintenance")).toBeNull();
  });
});
