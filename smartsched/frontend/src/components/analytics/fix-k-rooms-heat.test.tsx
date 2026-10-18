// E2EB-F21 (FIX-K): an imported term with nothing published says "Yayımlanmış program yok", not "Genel doluluk %0"
// beside the real counts of the pre-occupied cells.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import fixture from "./__fixtures__/heat-bahar-w3.json";

const data = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("@/lib/api/analytics", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/analytics")>()),
  useRoomHeatmap: (q: unknown) => ({ data: q ? data.current : undefined, isError: false, isFetching: false, isLoading: false, refetch: vi.fn() }),
}));
import { RoomsHeat } from "./rooms-heat";

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <RoomsHeat query={{ term_id: 1, group_by: "building", scope: "week", bookings: true, blocks: true, rooms: false }} group="" onGroup={() => undefined} />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("room heatmap headline", () => {
  it("live board without a published run: 'Yayımlanmış program yok'", () => {
    data.current = { ...fixture, runs: [] };
    wrap();
    expect(screen.getByTestId("heat-overall")).toHaveTextContent("Yayımlanmış program yok");
  });
  it("with a published run: the percentage", () => {
    data.current = fixture;
    wrap();
    expect(screen.getByTestId("heat-overall")).toHaveTextContent(/Genel doluluk %/);
  });
});
