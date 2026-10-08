"use client";
/**
 * Move flows (calendar.md §9.2, §9.5; planner usability M11 / ROADMAP "Move dialog: free-room finder,
 * Turkish reasons, date-ranged moves"):
 * - `MoveDialog`: room (from the free-room finder for the chosen slot: "Boş ve sığar" first, best fit),
 *   day, periods, and which weeks: all / only week N / from a date on. Live client check + server dry run.
 * - `MovePopover`: after a drop on a valid slot; old → new, soft warnings, the same scope radio; Enter saves,
 *   Esc reverts, auto-save after 4 s when untouched.
 */
import { Check, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { calendarApi, useFreeRooms, type FreeRoom, type MoveScope } from "@/lib/api/calendar";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, PERIODS_PER_DAY, dayName, formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { FloatingPanel } from "./floating-panel";
import { checkMove, whenText, type CheckIssue } from "./model/check";
import { dateOf } from "./model/dates";
import { maskOf, roomCap, weeksOfMask, type CalEvent, type CalendarModel } from "./model/index-model";

export interface ScopeValue {
  scope: MoveScope;
  week: number;
}

export function ScopeRadio({ model, ev, value, onChange, day }: { model: CalendarModel; ev: CalEvent; value: ScopeValue; onChange: (v: ScopeValue) => void; day: number }) {
  const { t, locale } = useI18n();
  const name = useId();
  const weeks = weeksOfMask(ev.mask);
  const label = (w: number) => {
    const d = dateOf(model.index.weeks, w, day);
    return d ? formatDate(d, locale, { day: "numeric", month: "long" }) : `${w}`;
  };
  if (weeks.length <= 1) return null;
  const range = weeks.length > 1 ? `${weeks[0]}–${weeks[weeks.length - 1]}` : String(weeks[0]);
  const opt = (scope: MoveScope, text: string, extra?: React.ReactNode) => (
    <label className="flex items-center gap-2 py-0.5">
      <input type="radio" name={name} checked={value.scope === scope} onChange={() => onChange({ ...value, scope })} className="accent-(--accent)" />
      <span className="flex-1">{text}</span>
      {extra}
    </label>
  );
  return (
    <fieldset className="flex flex-col gap-0.5 text-[13px]">
      <legend className="mb-1 text-[12px] font-semibold text-label-2">{t("calendar.move.scope")}</legend>
      {opt("all", t("calendar.move.scopeAll", { weeks: range }))}
      {opt("week", t("calendar.move.scopeWeek", { n: value.week, date: label(value.week) }))}
      {opt(
        "from",
        t("calendar.move.scopeFrom", { n: value.week, date: label(value.week) }),
        null,
      )}
      {value.scope !== "all" ? (
        <label className="mt-1 flex items-center gap-2 text-[12px] text-label-2">
          {t("calendar.move.fromWeek")}
          <select className="h-7 rounded-lg bg-fill-2 px-2 text-[12px] text-label-1" value={value.week} onChange={(e) => onChange({ ...value, week: Number(e.target.value) })}>
            {weeks.map((w) => (
              <option key={w} value={w}>
                {t("calendar.nav.weekShort", { n: w })} · {label(w)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </fieldset>
  );
}

function scopeMask(ev: CalEvent, s: ScopeValue): number {
  if (s.scope === "all") return ev.mask;
  const ws = weeksOfMask(ev.mask).filter((w) => (s.scope === "week" ? w === s.week : w >= s.week));
  return maskOf(ws);
}

function Issues({ hard, soft, lang }: { hard: CheckIssue[] | { text: { tr: string; en: string } }[]; soft: { text: { tr: string; en: string } }[]; lang: "tr" | "en" }) {
  if (!hard.length && !soft.length) return null;
  return (
    <ul className="flex flex-col gap-1 text-[12px]" aria-live="polite">
      {hard.map((h, i) => (
        <li key={`h${i}`} className="flex gap-1.5 text-status-infeasible-fg"><TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />{h.text[lang]}</li>
      ))}
      {soft.map((s, i) => (
        <li key={`s${i}`} className="flex gap-1.5 text-status-warning-fg"><span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--status-warning-solid)]" />{s.text[lang]}</li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ MoveDialog */

export interface MoveDialogProps {
  model: CalendarModel;
  ev: CalEvent | null;
  week: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (target: { room: number; day: number; sp: number; ep: number }, scope: ScopeValue) => Promise<boolean>;
}

export function MoveDialog({ model, ev, week, open, onOpenChange, onConfirm }: MoveDialogProps) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [room, setRoom] = useState<number>(ev?.room ?? 0);
  const [day, setDay] = useState<number>(ev?.day ?? 1);
  const [sp, setSp] = useState<number>(ev?.sp ?? 1);
  const [scope, setScope] = useState<ScopeValue>({ scope: "all", week });
  const [busy, setBusy] = useState(false);
  const [server, setServer] = useState<{ ok: boolean; hard: CheckIssue[]; soft: CheckIssue[] } | null>(null);
  const evKey = ev?.key;
  useEffect(() => {
    if (!ev) return;
    // reset the form whenever another class is opened
    /* eslint-disable react-hooks/set-state-in-effect */
    setRoom(ev.room);
    setDay(ev.day);
    setSp(ev.sp);
    setScope({ scope: "all", week: weeksOfMask(ev.mask).includes(week) ? week : weeksOfMask(ev.mask)[0] ?? week });
    setServer(null);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [evKey, ev, week]);
  const span = ev ? ev.ep - ev.sp : 0;
  const ep = Math.min(PERIODS_PER_DAY, sp + span);
  const mask = ev ? scopeMask(ev, scope) : 0;
  const weeks = weeksOfMask(mask);
  const finder = useFreeRooms(open && ev ? model.index.run.id : null, ev ? { day, start_period: sp, end_period: ep, weeks, exclude_assignment_id: ev.a.id } : null);
  const check = useMemo(() => (ev ? checkMove(model, ev, { room, day, sp, ep, mask }) : null), [ev, model, room, day, sp, ep, mask]);

  // server-confirmed dry run (debounced) so the dialog shows the same reasons the commit will
  const reqId = useRef(0);
  useEffect(() => {
    if (!open || !ev) return;
    const id = ++reqId.current;
    const h = setTimeout(() => {
      calendarApi
        .movePreview(model.index.run.id, ev.a.id, { day, start_period: sp, end_period: ep, room_ids: [room], scope: scope.scope, week: scope.scope === "all" ? null : scope.week })
        .then((r) => {
          if (id !== reqId.current) return;
          const it = r.items[0];
          setServer(it ? { ok: it.ok, hard: it.hard, soft: it.soft } : null);
        })
        .catch(() => id === reqId.current && setServer(null));
    }, 250);
    return () => clearTimeout(h);
  }, [open, ev, model.index.run.id, day, sp, ep, room, scope]);

  if (!ev) return null;
  const groups: { key: string; label: string; rooms: FreeRoom[] }[] = [
    { key: "free", label: t("calendar.move.groupFree"), rooms: [] },
    { key: "too_small", label: t("calendar.move.groupSmall"), rooms: [] },
    { key: "busy", label: t("calendar.move.groupBusy"), rooms: [] },
    { key: "other", label: t("calendar.move.groupOther"), rooms: [] },
  ];
  for (const r of finder.data?.rooms ?? []) {
    const g = r.status === "free" ? groups[0] : r.status === "too_small" ? groups[1] : r.status === "busy" ? groups[2] : groups[3];
    g.rooms.push(r);
  }
  const shown = server ?? check;
  const ok = !!shown && shown.hard.length === 0;
  const changed = room !== ev.room || day !== ev.day || sp !== ev.sp;
  const fromRoom = model.roomById.get(ev.room)?.name ?? "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-[640px]" data-testid="move-dialog">
        <DialogHeader>
          <DialogTitle>{t("calendar.move.title", { label: ev.a.label })}</DialogTitle>
          <DialogDescription>
            {fromRoom} · {whenText(ev.day, ev.sp, ev.ep)[lang]} · {ev.a.size} {lang === "tr" ? "öğrenci" : "students"}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-[1fr_220px]">
          <div className="flex min-w-0 flex-col gap-2">
            <p className="text-[12px] font-semibold text-label-2">{t("calendar.move.finder")}</p>
            <div className="max-h-[300px] overflow-y-auto rounded-xl bg-fill-3 p-1" role="listbox" aria-label={t("calendar.move.room")}>
              {finder.isLoading ? (
                <p className="flex items-center gap-2 p-3 text-[12px] text-label-2"><Loader2 className="size-3.5 animate-spin" aria-hidden />{t("calendar.move.checking")}</p>
              ) : (
                groups.map((g) =>
                  g.rooms.length ? (
                    <div key={g.key} role="group" aria-label={g.label}>
                      <p className="px-2 pt-2 pb-1 text-[11px] font-semibold text-label-2">{g.label} · {g.rooms.length}</p>
                      {g.rooms.slice(0, g.key === "free" ? 40 : 12).map((r) => (
                        <button
                          key={r.room_id}
                          type="button"
                          role="option"
                          aria-selected={room === r.room_id}
                          data-testid="free-room"
                          data-room-id={r.room_id}
                          data-status={r.status}
                          disabled={g.key === "other"}
                          onClick={() => setRoom(r.room_id)}
                          className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-fill-2 disabled:opacity-50", room === r.room_id && "bg-tint-soft")}
                        >
                          <span className="w-14 shrink-0 font-semibold">{r.code}</span>
                          <span className="w-16 shrink-0 text-[12px] text-label-2 tabular-nums">{t(model.exam ? "calendar.move.examSeats" : "calendar.move.seats", { n: r.capacity })}</span>
                          <span className="min-w-0 flex-1 truncate text-[12px] text-label-2">{r.status === "free" && r.fit ? `%${Math.round(r.fit * 100)}` : (r.reason?.[lang] ?? "")}</span>
                          {room === r.room_id ? <Check className="size-3.5 shrink-0 text-tint-text" aria-hidden /> : null}
                        </button>
                      ))}
                    </div>
                  ) : null,
                )
              )}
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
              {t("calendar.move.day")}
              <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-normal text-label-1" value={day} onChange={(e) => setDay(Number(e.target.value))}>
                {[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{dayName(d, locale)}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
              {t("calendar.move.start")}
              <select className="h-8 rounded-lg bg-fill-2 px-2 text-[13px] font-normal text-label-1" value={sp} onChange={(e) => setSp(Number(e.target.value))}>
                {PERIODS.filter((p) => p.index + span <= PERIODS_PER_DAY).map((p) => (
                  <option key={p.index} value={p.index}>P{p.index} · {p.start}–{PERIODS[p.index + span - 1].end}</option>
                ))}
              </select>
            </label>
            <ScopeRadio model={model} ev={ev} value={scope} onChange={setScope} day={day} />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          {shown ? <Issues hard={shown.hard} soft={shown.soft} lang={lang} /> : null}
          {server && server.ok ? <p className="text-[12px] text-status-feasible-fg" data-testid="move-server-ok">✓ {t("calendar.move.serverOk")}</p> : null}
          {scope.scope === "from" && ok ? <p className="text-[12px] text-label-2">{t("calendar.move.split", { room: fromRoom })}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("calendar.insp.cancel")}</Button>
          <Button
            data-testid="move-confirm"
            disabled={!ok || busy || !changed}
            onClick={async () => {
              setBusy(true);
              const done = await onConfirm({ room, day, sp, ep }, scope);
              setBusy(false);
              if (done) onOpenChange(false);
            }}
          >
            {busy ? t("calendar.move.moving") : changed ? t("calendar.move.confirm") : t("calendar.move.nothing")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ MovePopover (after a drop) */

export interface PendingMove {
  ev: CalEvent;
  target: { room: number; day: number; sp: number; ep: number };
  extra: { ev: CalEvent; target: { room: number; day: number; sp: number; ep: number } }[];
  anchor: { x: number; y: number };
  soft: CheckIssue[];
}

export function MovePopover({ model, pending, week, onSave, onCancel }: { model: CalendarModel; pending: PendingMove | null; week: number; onSave: (scope: ScopeValue) => void; onCancel: () => void }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const [scope, setScope] = useState<ScopeValue>({ scope: "all", week });
  const [touched, setTouched] = useState(false);
  const pkey = pending?.ev.key;
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setScope({ scope: "all", week });
    setTouched(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [pkey, week]);
  // auto-save after 4 s when the planner does not interact (calendar.md §9.2)
  useEffect(() => {
    if (!pending || touched) return;
    const h = setTimeout(() => onSave(scope), 4000);
    return () => clearTimeout(h);
  }, [pending, touched, scope, onSave]);
  if (!pending) return null;
  const from = model.roomById.get(pending.ev.room)?.name ?? "";
  const to = model.roomById.get(pending.target.room);
  return (
    <FloatingPanel open anchor={pending.anchor} onClose={onCancel} labelledBy={id} width={330} testId="move-popover">
      <div className="flex flex-col gap-2.5" onPointerDown={() => setTouched(true)} onKeyDown={(e) => {
        setTouched(true);
        if (e.key === "Enter" && !(e.target instanceof HTMLSelectElement)) {
          e.preventDefault();
          onSave(scope);
        }
      }}>
        <p id={id} className="text-[13px] font-semibold">
          {pending.extra.length ? t("calendar.drag.multi", { n: pending.extra.length + 1, ok: pending.extra.length + 1, bad: 0 }) : `${pending.ev.a.label} → ${to?.name ?? ""}`}
        </p>
        <p className="text-[12px] text-label-2 tabular-nums">
          <span className="line-through decoration-label-3">{from} {whenText(pending.ev.day, pending.ev.sp, pending.ev.ep)[lang]}</span>
          {" → "}
          <span className="text-label-1">{to?.name} {whenText(pending.target.day, pending.target.sp, pending.target.ep)[lang]} · {roomCap(model, to)} {lang === "tr" ? "koltuk" : "seats"}</span>
        </p>
        <Issues hard={[]} soft={pending.soft} lang={lang} />
        {pending.extra.length === 0 ? <ScopeRadio model={model} ev={pending.ev} value={scope} onChange={(v) => { setTouched(true); setScope(v); }} day={pending.target.day} /> : null}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={onCancel}>{t("calendar.toast.undo")} <kbd className="ml-1 text-[11px] text-label-3">esc</kbd></Button>
          <Button size="sm" data-testid="move-confirm" data-autofocus onClick={() => onSave(scope)}>{t("calendar.move.confirm")} <kbd className="ml-1 text-[11px] opacity-80">↵</kbd></Button>
        </div>
      </div>
    </FloatingPanel>
  );
}
