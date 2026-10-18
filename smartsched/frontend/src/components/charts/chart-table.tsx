"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.5, §9): the table twin. Always in the DOM: sr-only while the
// chart shows, visible after "Tabloyu göster". Same rows and columns as the CSV (`tableModel`). Original work.
import { cn } from "cn";
import type { TableModel } from "./chart-csv";

export function ChartTable({ id, caption, model, visible }: { id: string; caption: string; model: TableModel; visible: boolean }) {
  return (
    <div data-chart-table={id} data-testid={`chart-table-${id}`} className={cn(visible ? "max-h-80 overflow-auto" : "sr-only")}>
      <table className="w-full border-collapse type-footnote tabular-nums">
        <caption className={cn("text-left type-footnote text-label-2", visible ? "pb-2" : undefined)}>{caption}</caption>
        <thead>
          <tr>
            {model.head.map((h, i) => (
              <th key={i} scope="col" className={cn("border-b border-separator px-2 py-1.5 font-medium text-label-2", i === 0 ? "text-left" : "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {model.body.map((cells, r) => (
            <tr key={r}>
              {cells.map((c, i) =>
                i === 0 ? (
                  <th key={i} scope="row" className="border-b border-separator px-2 py-1.5 text-left font-normal text-label-1">
                    {c}
                  </th>
                ) : (
                  <td key={i} className="border-b border-separator px-2 py-1.5 text-right text-label-1">
                    {c}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
