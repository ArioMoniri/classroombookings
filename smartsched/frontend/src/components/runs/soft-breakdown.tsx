"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const CAT = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)", "var(--cat-4)", "var(--cat-5)", "var(--cat-6)", "var(--cat-7)", "var(--cat-8)"];

const KNOWN = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;
type Known = (typeof KNOWN)[number];
const isKnown = (k: string): k is Known => (KNOWN as readonly string[]).includes(k);

function labelFor(kind: string, t: (k: `generate.weight.${Known}`) => string): string {
  return isKnown(kind) ? t(`generate.weight.${kind}`) : kind.replace(/_/g, " ");
}

/** Stacked bar of points lost per soft-constraint family + legend list; table twin toggle (dataviz rule). */
export function SoftBreakdown({ score, breakdown, weights, className }: { score: number | null; breakdown: Record<string, number>; weights?: Record<string, number>; className?: string }) {
  const { t, n } = useI18n();
  const [table, setTable] = useState(false);
  const entries = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium text-muted-foreground">{t("runs.softScore")}</p>
        <p className="text-2xl font-bold tabular-nums">{score ?? "—"} <span className="text-sm font-normal text-muted-foreground">/ 100</span></p>
      </div>
      {!table ? (
        <div className="mt-2 flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full" role="img" aria-label={entries.map(([k, v]) => `${labelFor(k, t)}: ${v}`).join(", ")}>
          {entries.map(([k, v], i) => (
            <div key={k} style={{ width: `${(v / total) * 100}%`, background: CAT[i % CAT.length] }} title={`${labelFor(k, t)} · ${n(v)}`} />
          ))}
        </div>
      ) : null}
      {table ? (
        <table className="mt-2 w-full text-xs">
          <thead className="text-muted-foreground"><tr><th scope="col" className="text-left font-medium">{t("runs.objective")}</th><th scope="col" className="text-right font-medium">pts</th><th scope="col" className="text-right font-medium">w</th></tr></thead>
          <tbody>{entries.map(([k, v]) => <tr key={k}><th scope="row" className="py-0.5 text-left font-normal">{labelFor(k, t)}</th><td className="text-right tabular-nums">{n(v)}</td><td className="text-right tabular-nums">{weights?.[k] ?? "—"}</td></tr>)}</tbody>
        </table>
      ) : (
        <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
          {entries.map(([k, v], i) => (
            <li key={k} className="flex items-center gap-1.5 truncate">
              <span className="size-2 shrink-0 rounded-sm" style={{ background: CAT[i % CAT.length] }} aria-hidden />
              <span className="truncate text-muted-foreground">{labelFor(k, t)}</span>
              <span className="ml-auto tabular-nums">{n(v)}</span>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="mt-1 text-[11px] text-muted-foreground underline-offset-2 hover:underline" onClick={() => setTable((v) => !v)}>
        {table ? "Chart" : "Table"}
      </button>
    </div>
  );
}
