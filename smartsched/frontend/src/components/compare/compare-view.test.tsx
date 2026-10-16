/** The comparison page on the real Bahar week 3 pair (#5 vs #6): headline, metrics with words, class buckets. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import fixture from "./__fixtures__/compare-bahar-w3.json";

const search = vi.hoisted(() => ({ value: "a=5&b=6" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search.value),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/runs/compare",
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string) => {
    if (path === "/analytics/compare") return fixture;
    if (path === "/runs") return [];
    if (path === "/terms") return [];
    if (path === "/auth/me") return { id: 1 };
    throw new Error(`unexpected ${path}`);
  },
}));

import { CompareView } from "./compare-view";

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <CompareView />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("CompareView", () => {
  it("shows the backend headline, both runs and every metric with a verdict word", async () => {
    renderView();
    expect(await screen.findByTestId("compare-headline")).toHaveTextContent("10 ders taşındı");
    expect(screen.getByTestId("compare-run-a")).toHaveTextContent("Bahar 3. hafta (A)");
    const metrics = screen.getAllByTestId("compare-metric");
    expect(metrics).toHaveLength(fixture.metrics.length);
    const gaps = metrics.find((m) => m.dataset.key === "gaps_per_week_total")!;
    expect(gaps).toHaveAttribute("data-verdict", "better");
    expect(within(gaps).getByText("B daha iyi")).toBeInTheDocument();
  });

  it("switches the class buckets (moved / only in A / only in B) with their counts", async () => {
    renderView();
    const moved = await screen.findByTestId("compare-filter-moved");
    expect(moved).toHaveTextContent("Taşınan 10");
    await userEvent.click(screen.getByTestId("compare-filter-only_in_a"));
    expect(screen.getAllByText("PHY 102 §1").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("compare-class-row").every((r) => r.dataset.bucket === "only_in_a")).toBe(true);
    expect(screen.getAllByText("yerleşmedi").length).toBeGreaterThan(0);
  });
});
