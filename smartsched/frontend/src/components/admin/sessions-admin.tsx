"use client";
/**
 * /admin/sessions (CRBS `Sessions`, `Room_schedules`, `Dates_model`): which terms are selectable for
 * booking, the default schedule and the schedule per room group, and the calendar that assigns a
 * timetable week to each date (paint with a week, or apply one week to the whole term).
 */
import { Brush, Eraser, Loader2, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useReducer, useState, type PointerEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  crbs,
  useCrbsMutation,
  useSchedules,
  useSessionDates,
  useSessions,
  useTermSchedules,
  useTimetableWeeks,
  type Session,
  type TimetableWeek,
} from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { formatPattern, addDays } from "@/components/bookings/date-format";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { Alert, ConfirmDialog, FieldRow, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";
import { changeCount, changes, initialPainter, monthsBetween, painterReducer, type Brush as BrushValue } from "./date-painter";
import { DeleteSessionDialog, SessionDialog } from "./session-forms";

const KEYS = [["crbs", "sessions"], ["crbs", "session-dates"], ["crbs", "term-schedules"], ["crbs", "context"], ["crbs", "grid"], ["crbs", "dates"]];

export function SessionsAdmin() {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const sessions = useSessions();
  const [pick, setPick] = useState<number | null>(null);
  const current = sessions.data?.find((s) => s.term_id === pick) ?? sessions.data?.find((s) => s.is_selectable) ?? sessions.data?.[0];
  // CRBS Sessions::add / edit / delete (UI gap audit #3)
  const [editing, setEditing] = useState<Session | "new" | null>(null);
  const [deleting, setDeleting] = useState<Session | null>(null);
  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        title={t("crbs.admin.sessions.title")}
        subtitle={t("crbs.admin.sessions.lead")}
        actions={
          <Button onClick={() => setEditing("new")} data-testid="session-new">
            <Plus aria-hidden />
            {t("admingaps.sessions.new")}
          </Button>
        }
      />
      {sessions.isLoading ? <Loading /> : null}
      {sessions.data && sessions.data.length === 0 ? <Alert tone="info">{t("crbs.sessions.none")}</Alert> : null}
      {sessions.data && sessions.data.length ? (
        <Card variant="glass" className="py-0">
          <ul>
            {sessions.data.map((s) => (
              <li key={s.term_id} className="shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                <button
                  type="button"
                  aria-current={current?.term_id === s.term_id ? "true" : undefined}
                  onClick={() => setPick(s.term_id)}
                  className={cn("flex w-full items-center gap-3 px-4 py-2.5 text-left outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", current?.term_id === s.term_id ? "bg-tint-soft" : "hover:bg-fill-3")}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block type-headline text-label-1">{s.name}</span>
                    <span className="block type-footnote text-label-2">
                      {s.date_start && s.date_end ? `${fmt.short(s.date_start)} – ${fmt.short(s.date_end)}` : t("crbs.sessions.noDates")}
                      {" · "}
                      {t("crbs.sessions.counts", { dates: s.mapped_dates, holidays: s.holidays })}
                    </span>
                  </span>
                  <span className="type-footnote text-label-2">{s.is_selectable ? t("crbs.sessions.selectable") : t("crbs.sessions.hidden")}</span>
                  {s.is_current ? <span className="type-footnote font-medium text-tint-text">{t("crbs.sessions.current")}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {current ? <SessionDetail key={current.term_id} session={current} onEdit={() => setEditing(current)} onDelete={() => setDeleting(current)} /> : null}
      <SessionDialog open={editing !== null} session={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={(id) => setPick(id)} />
      <DeleteSessionDialog
        session={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => {
          setDeleting(null);
          setPick(null);
        }}
      />
    </div>
  );
}

function SessionDetail({ session, onEdit, onDelete }: { session: Session; onEdit: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const schedules = useSchedules();
  const termSchedules = useTermSchedules(session.term_id);
  const toastError = useErrorToast();
  const update = useCrbsMutation((body: { is_selectable?: boolean; default_schedule_id?: number | null }) => crbs.bookingAdmin.updateSession(session.term_id, body), KEYS);
  const putGroups = useCrbsMutation((body: { room_group_id: number; schedule_id: number }[]) => crbs.bookingAdmin.putTermSchedules(session.term_id, body), KEYS);
  return (
    <>
      <section aria-labelledby="sess-settings">
        <SectionTitle
          id="sess-settings"
          actions={
            <div className="flex gap-1">
              <Button variant="outline" size="sm" onClick={onEdit} data-testid="session-edit">
                <Pencil aria-hidden />
                {t("admingaps.sessions.edit")}
              </Button>
              <Button variant="ghost" size="sm" className="text-status-infeasible-fg" onClick={onDelete} data-testid="session-delete">
                <Trash2 aria-hidden />
                {t("crbs.common.delete")}
              </Button>
            </div>
          }
        >
          {t("crbs.sessions.settings", { name: session.name })}
        </SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          <FieldRow label={t("crbs.sessions.selectableLabel")} hint={t("crbs.sessions.selectableHint")} htmlFor="sess-sel">
            <Switch id="sess-sel" checked={session.is_selectable} onCheckedChange={(v) => update.mutate({ is_selectable: v }, { onError: toastError })} data-testid="session-selectable" />
          </FieldRow>
          <FieldRow label={t("crbs.sessions.defaultSchedule")} hint={t("crbs.sessions.defaultScheduleHint")} htmlFor="sess-sched" className="hairline-t">
            <SelectField id="sess-sched" className="w-56" value={session.default_schedule_id ?? ""} onChange={(e) => update.mutate({ default_schedule_id: e.target.value ? Number(e.target.value) : null }, { onError: toastError })}>
              <option value="">{t("crbs.common.none")}</option>
              {(schedules.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          </FieldRow>
        </Card>
      </section>
      <section aria-labelledby="sess-groups">
        <SectionTitle id="sess-groups">{t("crbs.sessions.groupSchedules")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          {(termSchedules.data ?? []).length === 0 ? <p className="py-3 type-callout text-label-2">{t("crbs.sessions.noGroups")}</p> : null}
          {(termSchedules.data ?? []).map((g, i) => (
            <FieldRow key={g.room_group_id} label={g.room_group} htmlFor={`ts-${g.room_group_id}`} className={i ? "hairline-t" : undefined}>
              <SelectField id={`ts-${g.room_group_id}`} className="w-56" value={g.schedule_id ?? ""} onChange={(e) => e.target.value && putGroups.mutate([{ room_group_id: g.room_group_id, schedule_id: Number(e.target.value) }], { onError: toastError })}>
                <option value="">{t("crbs.sessions.useDefault")}</option>
                {(schedules.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </SelectField>
            </FieldRow>
          ))}
        </Card>
      </section>
      <DatePainter session={session} />
    </>
  );
}

function DatePainter({ session }: { session: Session }) {
  const { t, locale } = useI18n();
  const dates = useSessionDates(session.term_id);
  const weeks = useTimetableWeeks();
  const [state, dispatch] = useReducer(painterReducer, initialPainter(null));
  const [applyOpen, setApplyOpen] = useState(false);
  const toastError = useErrorToast();
  const loaded = dates.data;
  useEffect(() => {
    if (loaded) dispatch({ type: "load", dates: loaded.dates });
  }, [loaded]);
  useEffect(() => {
    const up = () => dispatch({ type: "up" });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, []);
  const weekById = useMemo(() => new Map((weeks.data ?? []).map((w) => [w.id, w])), [weeks.data]);
  const info = useMemo(() => new Map((loaded?.dates ?? []).map((d) => [d.date, d])), [loaded]);
  const months = useMemo(() => (loaded ? monthsBetween(loaded.start, loaded.end) : []), [loaded]);
  const save = useCrbsMutation(() => crbs.bookingAdmin.putDates(session.term_id, changes(state)), KEYS);
  const applyAll = useCrbsMutation((id: number | null) => crbs.bookingAdmin.applyWeek(session.term_id, id), KEYS);
  const pending = changeCount(state);
  const weekdays = useMemo(() => Array.from({ length: 7 }, (_, i) => formatPattern(addDays("2026-02-16", i), "EEE", locale)), [locale]);

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!state.stroke) return;
    const el = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>("[data-paint-day]");
    const day = el?.dataset.paintDay;
    if (day && day !== state.last) dispatch({ type: "enter", date: day });
  };

  if (dates.isLoading) return <Loading />;
  if (!loaded) return null;
  const brushes: { value: BrushValue; week?: TimetableWeek }[] = [...(weeks.data ?? []).map((w) => ({ value: w.id as BrushValue, week: w })), { value: null }];

  return (
    <section aria-labelledby="sess-cal" className="flex flex-col gap-3">
      <SectionTitle
        id="sess-cal"
        actions={
          <div className="flex gap-2">
            {pending ? (
              <Button variant="ghost" size="sm" onClick={() => dispatch({ type: "revert" })}>
                <RotateCcw aria-hidden />
                {t("crbs.painter.revert")}
              </Button>
            ) : null}
            <Button size="sm" disabled={!pending || save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => toast.success(t("crbs.painter.saved", { n: pending })), onError: toastError })} data-testid="painter-save">
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t("crbs.painter.save", { n: pending })}
            </Button>
          </div>
        }
      >
        {t("crbs.painter.title")}
      </SectionTitle>
      <p className="type-callout text-label-2">{session.mapped_dates ? t("crbs.painter.leadMapped") : t("crbs.painter.leadUnmapped")}</p>
      {(weeks.data ?? []).length === 0 ? (
        <Alert tone="info">{t("crbs.painter.noWeeks")}</Alert>
      ) : (
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label={t("crbs.painter.brush")}>
          {brushes.map((b) => (
            <button
              key={b.value ?? "none"}
              type="button"
              role="radio"
              aria-checked={state.brush === b.value}
              onClick={() => dispatch({ type: "brush", brush: b.value })}
              className={cn("inline-flex h-8 items-center gap-1.5 rounded-full px-3 type-footnote font-medium outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)", state.brush === b.value ? "shadow-[0_0_0_2px_var(--accent)]" : "shadow-[0_0_0_1px_var(--hairline)]", !b.week && "bg-fill-2 text-label-1")}
              style={b.week ? { background: b.week.bgcol, color: b.week.fgcol } : undefined}
            >
              {b.week ? <Brush className="size-3.5" aria-hidden /> : <Eraser className="size-3.5" aria-hidden />}
              {b.week ? b.week.name : t("crbs.painter.eraser")}
            </button>
          ))}
          <Button variant="ghost" size="sm" onClick={() => setApplyOpen(true)}>
            {t("crbs.painter.applyAll")}
          </Button>
        </div>
      )}
      <p className="type-footnote text-label-3">{t("crbs.painter.howto")}</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" onPointerMove={onMove} data-testid="painter">
        {months.map((m) => (
          <Card key={m.key} variant="plain" className="gap-1 px-3 py-3">
            <p className="type-headline text-label-1">{formatPattern(`${m.key}-01`, "MMMM yyyy", locale)}</p>
            <div role="grid" aria-label={formatPattern(`${m.key}-01`, "MMMM yyyy", locale)}>
              <div role="row" className="grid grid-cols-[28px_repeat(7,1fr)] gap-0.5">
                <span role="columnheader" className="type-caption text-label-3" />
                {weekdays.map((w) => (
                  <span key={w} role="columnheader" className="text-center type-caption text-label-3">
                    {w}
                  </span>
                ))}
              </div>
              {m.weeks.map((wk) => (
                <div key={wk.monday} role="row" className="grid grid-cols-[28px_repeat(7,1fr)] gap-0.5">
                  <span role="rowheader">
                    {wk.days.some((d) => d && d in state.pending) ? (
                      <button type="button" aria-label={t("crbs.painter.paintWeek", { date: wk.monday })} onClick={() => dispatch({ type: "week", monday: wk.monday })} className="h-8 w-full rounded-md type-caption text-label-3 outline-none hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)">
                        {info.get(wk.days.find((d) => d && info.get(d)) ?? "")?.term_week ?? ""}
                      </button>
                    ) : null}
                  </span>
                  {wk.days.map((d, i) => {
                    if (!d || !(d in state.pending)) return <span key={i} role="gridcell" className="h-8" />;
                    const w = state.pending[d] != null ? weekById.get(state.pending[d] as number) : undefined;
                    const di = info.get(d);
                    const changed = state.pending[d] !== state.original[d];
                    return (
                      <span key={d} role="gridcell">
                        <button
                          type="button"
                          data-paint-day={d}
                          aria-label={[d, w ? w.name : t("crbs.painter.noWeek"), di?.holiday ? t("crbs.picker.holiday", { name: di.holiday }) : null, changed ? t("crbs.painter.changed") : null].filter(Boolean).join(", ")}
                          onPointerDown={(e) => {
                            e.preventDefault();
                            dispatch({ type: "down", date: d, shift: e.shiftKey });
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              dispatch({ type: "down", date: d, shift: e.shiftKey });
                              dispatch({ type: "up" });
                            }
                          }}
                          className={cn("relative flex h-8 w-full touch-none items-center justify-center rounded-md type-caption tabular-nums outline-none select-none focus-visible:outline-2 focus-visible:outline-(--focus)", !w && "bg-fill-3 text-label-2", changed && "shadow-[inset_0_0_0_1.5px_var(--label-1)]", di?.holiday && "line-through")}
                          style={w ? { background: w.bgcol, color: w.fgcol } : undefined}
                        >
                          {Number(d.slice(8))}
                        </button>
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
      <ConfirmDialog
        open={applyOpen}
        onOpenChange={setApplyOpen}
        title={t("crbs.painter.applyAllTitle")}
        description={t("crbs.painter.applyAllBody")}
        confirmLabel={state.brush != null ? t("crbs.painter.applyWeek", { name: weekById.get(state.brush)?.name ?? "" }) : t("crbs.painter.clearAll")}
        destructive={state.brush == null}
        busy={applyAll.isPending}
        onConfirm={() => applyAll.mutate(state.brush, { onSuccess: () => setApplyOpen(false), onError: toastError })}
      />
    </section>
  );
}
