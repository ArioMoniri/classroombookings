// E2EB-F03 (fix-j-2026-10-18): an empty install never shows a dead end. The heatmap without any term shows one
// needs card ("Henüz dönem yok" + İçe aktar) instead of its controls; find-room and Hızlı rezervasyon without a
// bookable term say why and name the next step.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const perms = vi.hoisted(() => ({ edit: true }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, can: () => perms.edit }) }));
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: null, terms: [], isLoading: false }) }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/analytics/heatmap",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

import { HeatmapView } from "@/components/analytics/heatmap-view";
import { NoBookingTerm } from "./no-booking-term";

const wrap = (node: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );

describe("empty install next steps (E2EB-F03)", () => {
  it("the heatmap with no term shows the needs card, not its controls", () => {
    wrap(<HeatmapView />);
    expect(screen.getByTestId("adaptive-no-terms")).toHaveTextContent("Henüz dönem yok");
    expect(screen.getByTestId("adaptive-no-terms").querySelector("a[href=\"/import\"]")).toHaveTextContent("İçe aktar");
    expect(screen.queryByTestId("heat-controls")).toBeNull();
    expect(screen.queryByText("Önce bir dönem seçin.")).toBeNull();
  });

  it("no bookable term: a planner gets 'Dosyalardan kur'", () => {
    perms.edit = true;
    wrap(<NoBookingTerm />);
    expect(screen.getByTestId("no-booking-term")).toHaveTextContent("Rezervasyon yapılabilecek bir dönem yok");
    expect(screen.getByTestId("no-booking-term-setup")).toHaveAttribute("href", "/onboarding");
    expect(screen.getByTestId("no-booking-term-setup")).toHaveTextContent("Dosyalardan kur");
  });

  it("no bookable term: everyone else is told who can set it up", () => {
    perms.edit = false;
    wrap(<NoBookingTerm />);
    expect(screen.getByTestId("no-booking-term")).toHaveTextContent("yöneticiniz");
    expect(screen.queryByTestId("no-booking-term-setup")).toBeNull();
  });
});
