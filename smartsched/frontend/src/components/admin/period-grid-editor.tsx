"use client";
/**
 * RF-09: /admin/schedules "Ders saatleri", the clock times of the university's 18 periods (`GET`/`PUT`/`DELETE
 * /period-grid`, rf-b API.md §5). Exactly 18 rows: the count never changes (the solver and stored requests address
 * P1-P18), only the times. Turkish input (`08.30`) is sent as typed and read by the server; its Turkish refusal is
 * shown at the period (and field) it names. One primary action, "Kaydet"; "Varsayılana dön" sits under "Gelişmiş"
 * and asks first.
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { refusalBody, refusalCode, serverMessage } from "@/lib/api/error-text";
import { PERIOD_COUNT, periodGridApi, periodGridKey, periodOfMessage, usePeriodGrid, type PeriodGrid } from "@/lib/api/rf-admin";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Alert, ConfirmDialog, Loading } from "./kit";

type Row = { start: string; end: string };
type GridError = { period: number | null; field: "start" | "end" | null; message: string };

const rowsOf = (g: PeriodGrid | undefined): Row[] => (g?.periods ?? []).slice(0, PERIOD_COUNT).map((p) => ({ start: p.start, end: p.end }));

/** Which field of the named period a refusal is about (null: the whole row). */
export function errorField(code: string | null, messages: string, row: Row | undefined): "start" | "end" | null {
  if (code === "period_grid_time" && row) {
    const quoted = /'([^']*)'/.exec(messages)?.[1]?.trim();
    if (quoted !== undefined) {
      if (row.end.trim() === quoted && row.start.trim() !== quoted) return "end";
      if (row.start.trim() === quoted) return "start";
    }
    return null;
  }
  if (code === "period_grid_order") return /\bthe end\b|bitiş saati/i.test(messages) ? "end" : "start";
  return null;
}

export function PeriodGridEditor() {
  const grid = usePeriodGrid();
  // E2EA2-F03: the form remounts on a new answer, so the control to focus afterwards is kept up here
  const focusAfter = useRef<"save" | "p1" | null>(null);
  if (grid.isLoading) return <Loading />;
  if (!grid.data) return null;
  // a new server answer (save, reset) starts the form again from it
  return <GridForm key={JSON.stringify(grid.data.periods)} grid={grid.data} focusAfter={focusAfter} />;
}

function GridForm({ grid, focusAfter }: { grid: PeriodGrid; focusAfter: RefObject<"save" | "p1" | null> }) {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const [rows, setRows] = useState<Row[]>(() => rowsOf(grid));
  const [error, setError] = useState<GridError | null>(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [resetting, setResetting] = useState(false);
  const id = useId();
  const saveRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const want = focusAfter.current;
    if (!want) return;
    focusAfter.current = null;
    // after the confirm dialog has handed focus back (reset), so this one wins
    const raf = requestAnimationFrame(() => (want === "save" ? saveRef.current : document.getElementById(`${id}-1-start`))?.focus());
    return () => cancelAnimationFrame(raf);
  }, [focusAfter, id]);
  const initial = rowsOf(grid);
  const dirty = rows.some((r, i) => r.start.trim() !== initial[i]?.start || r.end.trim() !== initial[i]?.end);

  const done = (out: PeriodGrid, key: "saved" | "reset") => {
    qc.setQueryData(periodGridKey, out);
    // booking periods made "from grid" follow the change (/admin/schedules lists them)
    void qc.invalidateQueries({ queryKey: ["crbs"] });
    if (key === "reset") toast.success(t("rf.grid.resetDone"));
    else toast.success(out.booking_periods_updated ? t("rf.grid.savedFollow", { n: n(out.booking_periods_updated) }) : t("rf.grid.saved"));
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await periodGridApi.save(rows.map((r) => ({ start: r.start.trim(), end: r.end.trim() })));
      focusAfter.current = "save";
      done(out, "saved");
    } catch (e) {
      const message = serverMessage(e, locale) ?? t("glass.import.failed");
      const body = refusalBody(e);
      const en = typeof body?.message_en === "string" ? body.message_en : typeof body?.message === "string" ? body.message : "";
      const period = periodOfMessage(typeof body?.message_tr === "string" ? body.message_tr : message) ?? periodOfMessage(en);
      const field = period ? errorField(refusalCode(e), `${en} ${message}`, rows[period - 1]) : null;
      setError({ period, field, message });
      requestAnimationFrame(() => {
        const target = period ? document.getElementById(`${id}-${period}-${field ?? "start"}`) : document.getElementById(`${id}-alert`);
        target?.focus();
      });
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setResetting(true);
    try {
      const out = await periodGridApi.reset();
      focusAfter.current = "p1";
      done(out, "reset");
      setConfirm(false);
    } catch (e) {
      setConfirm(false);
      setError({ period: null, field: null, message: serverMessage(e, locale) ?? t("glass.import.failed") });
    } finally {
      setResetting(false);
    }
  };

  const set = (i: number, k: keyof Row, v: string) => {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
    if (error?.period === i + 1) setError(null);
  };

  return (
    <Card className="gap-4 px-5" data-testid="period-grid" data-tour="admin-periods">
      <section aria-labelledby={`${id}-title`} className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={`${id}-title`} className="type-title-3 font-semibold text-label-1">
            {t("rf.grid.title")}
          </h2>
          <Badge variant="secondary">{grid.source === "setting" ? t("rf.grid.sourceSetting") : t("rf.grid.sourceDefault")}</Badge>
        </div>
        <p className="type-callout text-label-2">{t("rf.grid.lead")}</p>
        {error && error.period === null ? (
          <div id={`${id}-alert`} tabIndex={-1} className="outline-hidden">
            <Alert tone="error">{error.message}</Alert>
          </div>
        ) : null}
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <ol className="grid gap-x-6 gap-y-1 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((r, i) => {
              const p = i + 1;
              const bad = error?.period === p;
              const errId = `${id}-${p}-err`;
              return (
                <li key={p} className="flex flex-col gap-1 py-1" data-testid={`grid-row-${p}`}>
                  <div className="flex items-center gap-2">
                    <span className="w-9 shrink-0 type-callout font-semibold text-label-1 tabular-nums">P{p}</span>
                    {(["start", "end"] as const).map((k) => (
                      <Input
                        key={k}
                        id={`${id}-${p}-${k}`}
                        value={r[k]}
                        onChange={(e) => set(i, k, e.target.value)}
                        aria-label={t(k === "start" ? "rf.grid.startNamed" : "rf.grid.endNamed", { n: p })}
                        aria-invalid={bad && (error?.field === null || error?.field === k) ? true : undefined}
                        aria-describedby={bad ? errId : undefined}
                        inputMode="decimal"
                        autoComplete="off"
                        maxLength={16}
                        placeholder="08.30"
                        className="w-24 tabular-nums"
                      />
                    ))}
                  </div>
                  {bad ? (
                    <p id={errId} role="alert" className="type-footnote text-status-infeasible-fg">
                      {error.message}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ol>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button type="button" variant="ghost" className="pointer-coarse:h-11" aria-expanded={advanced} aria-controls={`${id}-adv`} onClick={() => setAdvanced((v) => !v)} data-testid="period-grid-advanced">
              <ChevronDown aria-hidden className={cn("transition-transform motion-reduce:transition-none", advanced && "rotate-180")} />
              {t("rf.grid.advanced")}
            </Button>
            {/* focusable while clean (aria-disabled), so focus stays on it after a save */}
            <Button ref={saveRef} type="submit" {...busyProps(busy, !dirty)} focusableWhenDisabled data-testid="period-grid-save">
              <BusyLabel busy={busy} label={t("busy.saving")}>
                {t("rf.grid.save")}
              </BusyLabel>
            </Button>
          </div>
          {advanced ? (
            <div id={`${id}-adv`} className="flex flex-col items-start gap-2 rounded-xl bg-fill-3 p-3">
              <Button type="button" variant="outline" onClick={() => setConfirm(true)} disabled={grid.source !== "setting"} data-testid="period-grid-reset">
                {t("rf.grid.reset")}
              </Button>
              {grid.source !== "setting" ? <p className="type-footnote text-label-2">{t("rf.grid.already")}</p> : null}
            </div>
          ) : null}
        </form>
      </section>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title={t("rf.grid.resetTitle")} description={t("rf.grid.resetBody")} confirmLabel={t("rf.grid.reset")} busy={resetting} onConfirm={() => void reset()} />
    </Card>
  );
}
