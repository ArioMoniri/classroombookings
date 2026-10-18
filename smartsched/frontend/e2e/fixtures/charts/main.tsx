// CH-03 fixture (e2e/charts-a11y.spec.ts): two ChartCards, never mounted on an app route.
import "@/app/globals.css";
import { createRoot } from "react-dom/client";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { LazyBarChart, LazyLineChart } from "@/components/charts/chart-lazy";
import { categoricalConfig, legendItems, singleConfig } from "@/components/charts/chart-tokens";

type Day = { day: string; chat: number; rules: number };
const days: Day[] = [
  ["2026-10-08", 20100, 10400],
  ["2026-10-09", 31000, 15200],
  ["2026-10-10", 12000, 9000],
  ["2026-10-11", 8000, 2000],
  ["2026-10-12", 41000, 22000],
  ["2026-10-13", 39000, 30000],
  ["2026-10-14", 37120, 45180],
].map(([day, chat, rules]) => ({ day: day as string, chat: chat as number, rules: rules as number }));
const dayColumns: ChartColumn<Day>[] = [
  { key: "day", label: "Gün", kind: "date" },
  { key: "chat", label: "Sohbet", kind: "number" },
  { key: "rules", label: "Kurallar", kind: "number" },
];
const series = [
  { key: "chat", label: "Sohbet" },
  { key: "rules", label: "Kurallar" },
];

type Minute = { t: string; rpm: number };
const minutes: Minute[] = Array.from({ length: 400 }, (_, i) => ({ t: `${String(Math.floor(i / 60) + 12).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}`, rpm: 40 + Math.round(10 * Math.sin(i / 9)) }));

function App() {
  return (
    <div style={{ display: "grid", gap: 32, maxWidth: 960 }}>
      <ChartCard<Day> id="fx-bar" title="Günlük token kullanımı" summary="Son 7 günde 321 bin token; en yoğun gün 14 Eki (82 bin)." state="ready" columns={dayColumns} rows={days} unit="token" legend={legendItems(series)} series={2}>
        {(ctx) => <LazyBarChart {...ctx} data={days} config={categoricalConfig(series)} xKey="day" series={["chat", "rules"]} stackType="stacked" />}
      </ChartCard>
      <ChartCard<Minute> id="fx-line" title="Dakikada istek" summary="Dakikada ort. 40 istek." state="ready" columns={[{ key: "t", label: "Saat" }, { key: "rpm", label: "İstek/dk", kind: "number" }]} rows={minutes} series={1}>
        {(ctx) => <LazyLineChart {...ctx} data={minutes} config={singleConfig("rpm", "İstek/dk")} xKey="t" series={["rpm"]} />}
      </ChartCard>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
