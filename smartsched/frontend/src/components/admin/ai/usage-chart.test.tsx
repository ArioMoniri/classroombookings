import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { UsageRow } from "@/lib/api/ai-admin";

vi.mock("@/components/charts/chart-lazy", () => ({
  LazyBarChart: (p: { data: unknown[]; series: readonly string[]; xKey: string; stackType?: string; partialLast: boolean; config: Record<string, { colors: { light: string[] } }> }) => (
    <div
      data-testid="bar"
      data-points={p.data.length}
      data-series={p.series.join(",")}
      data-x={p.xKey}
      data-stack={p.stackType}
      data-partial={String(p.partialLast)}
      data-colors={p.series.map((s) => p.config[s]!.colors.light[0]).join(",")}
    />
  ),
}));
// labels come from the feature registry (GET /ai/admin/usage/summary): fixed here
vi.mock("./ai-kit", async (orig) => ({ ...(await orig<typeof import("./ai-kit")>()), useAiLabels: () => ({ feature: (s: string) => ({ chat: "Sohbet", rules: "Kurallar", intake: "İçe aktarma", explain: "Açıklama", vision: "Görsel" })[s] ?? s }) }));

import { DailyChart } from "./usage-chart";

const row = (key: string, features: Record<string, number>): UsageRow => ({ key, calls: 1, tokens: Object.values(features).reduce((a, b) => a + b, 0), cost_usd: 0, refused: 0, features }) as UsageRow;
const rows = [
  row("2026-10-12", { chat: 300, rules: 100 }),
  row("2026-10-13", { chat: 200, intake: 50, explain: 10, vision: 5, guard: 5 }),
  row("2026-10-14", { chat: 100, rules: 900 }),
];

describe("DailyChart on the ChartCard shell (CH-05)", { timeout: 20_000 }, () => {
  it("stacks the active features in the fixed order with their own colours; table + CSV columns are the features + total", () => {
    render(<DailyChart rows={rows} loading={false} />);
    const fig = screen.getByRole("figure", { name: "Günlük token kullanımı" });
    expect(fig).toHaveAccessibleDescription(/^Bu dönemde 1,67\sB token; en çok Kurallar/);
    const bar = screen.getByTestId("bar");
    expect(bar).toHaveAttribute("data-stack", "stacked");
    expect(bar).toHaveAttribute("data-series", "chat,rules,intake,explain,vision,other");
    expect(bar).toHaveAttribute("data-colors", "var(--cat-1),var(--cat-2),var(--cat-3),var(--cat-4),var(--cat-5),var(--label-3)");
    const heads = within(within(fig).getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Gün", "Sohbet", "Kurallar", "İçe aktarma", "Açıklama", "Görsel", "Diğer", "Toplam"]);
    expect(screen.getByTestId("chart-legend-ai-daily-tokens")).toHaveTextContent("SohbetKurallarİçe aktarmaAçıklamaGörselDiğer");
  });

  it("F-CH-4: five features are five named columns + Toplam (no Diğer); the CSV header says so", () => {
    render(<DailyChart rows={[row("2026-10-12", { chat: 5, rules: 4, explain: 3, booking_nl: 2, voice_stt: 1 }), row("2026-10-13", { chat: 5 }), row("2026-10-14", { rules: 1 })]} loading={false} />);
    const fig = screen.getByRole("figure", { name: "Günlük token kullanımı" });
    expect(screen.getByTestId("bar")).toHaveAttribute("data-series", "chat,rules,explain,booking_nl,voice_stt");
    const heads = within(within(fig).getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Gün", "Sohbet", "Kurallar", "Açıklama", "booking_nl", "voice_stt", "Toplam"]);
  });

  it("a filtered-out series keeps the others' colours", () => {
    render(<DailyChart rows={[row("2026-10-12", { chat: 5, intake: 5 }), row("2026-10-13", { chat: 5 }), row("2026-10-14", { intake: 1 })]} loading={false} />);
    expect(screen.getByTestId("bar")).toHaveAttribute("data-series", "chat,intake");
    expect(screen.getByTestId("bar")).toHaveAttribute("data-colors", "var(--cat-1),var(--cat-3)");
  });

  it("the table toggle keeps the old test ids for the w3-ai flow", () => {
    render(<DailyChart rows={rows} loading={false} />);
    fireEvent.click(screen.getByTestId("chart-table-toggle-ai-daily-tokens"));
    expect(screen.getByTestId("chart-table-ai-daily-tokens")).not.toHaveClass("sr-only");
  });

  it("loading and empty states", () => {
    const { unmount } = render(<DailyChart rows={[]} loading />);
    expect(screen.getByRole("figure")).toHaveAttribute("aria-busy", "true");
    unmount();
    render(<DailyChart rows={[]} loading={false} />);
    expect(screen.getByText("Bu dönemde yapay zekâ kullanımı yok.")).toBeInTheDocument();
  });
});
