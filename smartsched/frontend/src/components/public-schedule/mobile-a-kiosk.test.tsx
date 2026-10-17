/**
 * Mobile audit A (2026-10-17), fixes 2, 10, 11 on the public day view:
 *  2  the date row's space is held while the backend's "today" is unknown, so the list does not jump down when it
 *     arrives (CLS 0.77 on /public/buildings/A, 0.11 on /public/rooms/A101);
 * 10  in landscape the frame keeps the notch inset on the sides (sm:px-8 used to override it);
 * 11  the building headings on /public are 44 px tap targets.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({ usePathname: () => "/public", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/public-schedule", async (orig) => {
  const real = await orig<typeof import("@/lib/api/public-schedule")>();
  return { ...real, usePublicIndex: () => ({ isLoading: false, isError: false, dataUpdatedAt: 0, data: { buildings: [{ code: "A", name: "A Blok", rooms: [{ code: "A101", name: "A 101", building: "A", capacity: 58 }] }] } }) };
});

import { KioskFrame } from "./kiosk";
import { PublicIndexView } from "./public-views";

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

describe("mobile-a: kiosk frame", () => {
  it("holds the date row's height while today is unknown", () => {
    wrap(<KioskFrame title="A Blok" today={null} date={null} onDate={() => undefined}>x</KioskFrame>);
    expect(screen.getByTestId("kiosk-nav-placeholder")).toHaveClass("min-h-11");
    expect(screen.queryByTestId("kiosk-prev")).toBeNull();
  });

  it("shows the date row, and no placeholder, once today is known", () => {
    wrap(<KioskFrame title="A Blok" today="2026-10-22" date={null} onDate={() => undefined}>x</KioskFrame>);
    expect(screen.getByTestId("kiosk-prev")).toBeInTheDocument();
    expect(screen.queryByTestId("kiosk-nav-placeholder")).toBeNull();
  });

  it("keeps the side notch insets on wide screens", () => {
    wrap(<KioskFrame title="A Blok" today={null} date={null} onDate={() => undefined}>x</KioskFrame>);
    const k = screen.getByTestId("kiosk");
    expect(k).toHaveClass("sm:pl-[max(2rem,env(safe-area-inset-left))]", "sm:pr-[max(2rem,env(safe-area-inset-right))]");
    expect(k).not.toHaveClass("sm:px-8");
  });
});

describe("mobile-a: /public index", () => {
  it("has no date row and 44 px building links", () => {
    wrap(<PublicIndexView />);
    expect(screen.queryByTestId("kiosk-nav-placeholder")).toBeNull();
    expect(screen.getByTestId("public-building-A")).toHaveClass("inline-flex", "min-h-11");
  });
});
