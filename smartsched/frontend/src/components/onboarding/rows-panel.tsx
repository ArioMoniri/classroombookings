"use client";
/**
 * AI-route rows (P19-A2, 2026-10-15 contract): every row the model read stays pending until a person decides.
 * GET /council/jobs/{id}/rows?method=ai&state=pending; POST …/rows/decisions {decisions, confirm}. Bulk approval:
 * at most `bulk_max` (50) visible rows and only with an explicit confirmation; low-confidence rows are decided one
 * at a time (they cannot be selected for the bulk action). Provenance (file · sheet/page · row) and the
 * Doğrudan / YZ badge sit on every row (phase19-intake I1/I4).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button, IconButton } from "@/components/ui/button";
import { BusyButton } from "@/components/ui/busy-label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { councilApi, type CouncilRow, type RowDecisionIn } from "@/lib/api/council";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { useOnboardingCopy } from "./copy";
import { MethodBadge } from "./method-badge";

export const rowsKey = (jobId: number) => ["council-rows", jobId] as const;

function provenance(r: CouncilRow): string {
  const p = r.provenance;
  return [p.file, p.sheet ?? (p.page != null ? `s.${p.page}` : null), p.row != null ? `R${p.row}` : p.line != null ? `L${p.line}` : null].filter((x) => x != null && x !== "").join(" · ");
}
function summary(r: CouncilRow): string {
  const v = r.values;
  const pick = ["course", "course_code", "code", "section", "day", "start", "room", "name", "program"].map((k) => v[k]).filter((x) => typeof x === "string" || typeof x === "number");
  return pick.slice(0, 4).join(" · ") || String(r.entity ?? "");
}

export function RowsPanel({ jobId, onChanged }: { jobId: number; onChanged: () => void }) {
  const { n, locale } = useI18n();
  const c = useOnboardingCopy();
  const qc = useQueryClient();
  const rows = useQuery({ queryKey: rowsKey(jobId), queryFn: () => councilApi.rows(jobId, { method: "ai", state: "pending", limit: 200 }) });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const items = useMemo(() => rows.data?.items ?? [], [rows.data]);
  const max = rows.data?.bulk_max ?? 50;
  const bulkable = items.filter((r) => !r.low_confidence).slice(0, max);

  const decide = async (decisions: RowDecisionIn[], confirm = false) => {
    setBusy(true);
    try {
      await councilApi.decideRows(jobId, decisions, confirm);
      setSelected(new Set());
      await qc.invalidateQueries({ queryKey: rowsKey(jobId) });
      onChanged();
    } catch (e) {
      toast.error(problemText(e, locale) ?? (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  if (rows.isLoading) return <Skeleton className="h-24 rounded-xl" />;
  if (!rows.data || rows.data.total === 0) return null;
  const allOn = bulkable.length > 0 && bulkable.every((r) => selected.has(r.id));
  return (
    <Card data-testid="onboarding-rows">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {c.rowsTitle}
          <span className="type-callout font-normal text-label-2 tnum" data-testid="rows-pending">{c.rowsPending(rows.data.total)}</span>
        </CardTitle>
        <p className="type-callout text-label-2">{c.rowsHint}</p>
      </CardHeader>
      <CardContent className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 type-callout text-label-1">
            <Checkbox checked={allOn} onCheckedChange={(v) => setSelected(v ? new Set(bulkable.map((r) => r.id)) : new Set())} />
            {n(bulkable.length)} / {n(items.length)}
          </label>
          <Button size="sm" className="ml-auto" disabled={busy || selected.size === 0} onClick={() => (selected.size > 1 ? setConfirming(true) : void decide([...selected].map((id) => ({ row_id: id, action: "accept" }))))} data-testid="rows-accept-selected">
            <Check aria-hidden /> {c.acceptSelected(selected.size)}
          </Button>
        </div>
        <ul className="grid">
          {items.map((r) => (
            <li key={r.id} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 py-1.5 edge-hairline-b" data-testid="council-row" data-low={r.low_confidence || undefined}>
              <Checkbox aria-label={c.select(r.id)} disabled={r.low_confidence} checked={selected.has(r.id)} onCheckedChange={(v) => setSelected((s) => { const next = new Set(s); if (v) next.add(r.id); else next.delete(r.id); return next; })} />
              <MethodBadge method={r.method} confidence={r.confidence} />
              {r.low_confidence ? <span className="type-caption text-status-warning-fg">{c.lowConfidence}</span> : null}
              <span className="min-w-0 flex-1 truncate type-callout text-label-1">{summary(r)}</span>
              <span className="max-w-[40%] truncate type-footnote text-label-2" title={`${c.provenance}: ${provenance(r)}`}>{provenance(r)}</span>
              <span className="flex items-center gap-1">
                <IconButton size="sm" variant="ghost" label={`${c.accept} ${r.id}`} disabled={busy} onClick={() => void decide([{ row_id: r.id, action: "accept" }])}><Check aria-hidden /></IconButton>
                <IconButton size="sm" variant="ghost" label={`${c.reject} ${r.id}`} disabled={busy} onClick={() => void decide([{ row_id: r.id, action: "reject" }])}><X aria-hidden /></IconButton>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
      <Dialog open={confirming} onOpenChange={(o) => !busy && setConfirming(o)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{c.acceptSelected(selected.size)}</DialogTitle>
            <DialogDescription>{c.bulkConfirm(selected.size)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setConfirming(false)}>{c.cancel}</Button>
            <BusyButton busy={busy} busyLabel={c.confirm} onClick={() => void decide([...selected].map((id) => ({ row_id: id, action: "accept" })), true)} data-testid="rows-bulk-confirm">
              {c.confirm}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
