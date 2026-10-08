"use client";
/**
 * Ajanda (calendar.md §6.7): days → periods → events, a virtualised feed (role=feed of articles) with sticky
 * day headers; on today "Şimdi" (running, with a progress hairline) and "Sıradaki" (next two periods) come
 * first. The screen-reader-friendly lens and the phone list.
 */
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, Lock } from "lucide-react";
import { memo, useMemo, useRef } from "react";
import { PERIODS } from "@/lib/time";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { chipVars } from "./event-chip";
import { spanText } from "./model/check";
import { dayTitle } from "./model/dates";
import { periodEndMin, periodStartMin } from "./model/geometry";
import type { CalEvent, CalendarModel } from "./model/index-model";

type Item =
  | { kind: "day"; key: string; day: number; date: string | null }
  | { kind: "section"; key: string; label: string }
  | { kind: "event"; key: string; ev: CalEvent; now?: boolean };

export interface AgendaProps {
  model: CalendarModel;
  events: CalEvent[];
  days: number[];
  dates: (string | null)[];
  todayIso: string;
  nowMin: number;
  selection: ReadonlySet<number>;
  onOpen: (ev: CalEvent) => void;
  onSelect: (aid: number | null, mode: "replace" | "toggle" | "range") => void;
  /** phone list: no day headers, larger rows */
  compact?: boolean;
  emptyLabel: string;
}

function AgendaImpl(p: AgendaProps) {
  const { t, locale } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    for (const d of p.days) {
      const date = p.dates[d - 1] ?? null;
      const evs = p.events.filter((e) => e.day === d).sort((a, b) => a.sp - b.sp || a.a.label.localeCompare(b.a.label, "tr"));
      if (!evs.length) continue;
      if (!p.compact) out.push({ kind: "day", key: `d${d}`, day: d, date });
      const isToday = date === p.todayIso;
      let rest = evs;
      if (isToday) {
        const running = evs.filter((e) => periodStartMin(e.sp) <= p.nowMin && p.nowMin < periodEndMin(e.ep));
        const nextStart = PERIODS.find((q) => periodStartMin(q.index) > p.nowMin)?.index;
        const next = nextStart ? evs.filter((e) => e.sp >= nextStart && e.sp <= nextStart + 1) : [];
        if (running.length) {
          out.push({ kind: "section", key: `now${d}`, label: `${t("calendar.agenda.now")} · ${String(Math.floor(p.nowMin / 60)).padStart(2, "0")}:${String(p.nowMin % 60).padStart(2, "0")}` });
          running.forEach((ev) => out.push({ kind: "event", key: `n${ev.key}`, ev, now: true }));
        }
        if (next.length && nextStart) {
          out.push({ kind: "section", key: `next${d}`, label: `${t("calendar.agenda.upNext")} · ${PERIODS[nextStart - 1].start}` });
          next.forEach((ev) => out.push({ kind: "event", key: `x${ev.key}`, ev }));
        }
        const shown = new Set([...running, ...next].map((e) => e.key));
        rest = evs.filter((e) => !shown.has(e.key) && periodEndMin(e.ep) > p.nowMin);
      }
      let lastP = -1;
      for (const ev of rest) {
        if (ev.sp !== lastP) {
          lastP = ev.sp;
          const per = PERIODS[ev.sp - 1];
          out.push({ kind: "section", key: `p${d}-${ev.sp}`, label: `${t("calendar.agenda.period", { time: per.start, n: ev.sp })}${ev.sp === 13 ? ` · ${t("calendar.agenda.evening")}` : ""}` });
        }
        out.push({ kind: "event", key: ev.key, ev });
      }
    }
    return out;
  }, [p.days, p.dates, p.events, p.todayIso, p.nowMin, p.compact, t]);

  const rowH = p.compact ? 64 : 44;
  const v = useVirtualizer({
    count: items.length,
    getScrollElement: () => ref.current,
    estimateSize: (i) => (items[i].kind === "event" ? rowH : items[i].kind === "day" ? 40 : 28),
    overscan: 12,
  });

  if (!items.length) return <p className="cal-canvas h-full px-6 py-8 text-[13px] text-label-2">{p.emptyLabel}</p>;

  const activeDay = (() => {
    const first = v.getVirtualItems()[0]?.index ?? 0;
    for (let i = first; i >= 0; i--) {
      const it = items[i];
      if (it.kind === "day") return it;
    }
    return null;
  })();

  return (
    <div ref={ref} className="cal-canvas relative h-full overflow-auto" role="feed" aria-label={t("calendar.agenda.label")} data-testid="agenda">
      {activeDay && !p.compact ? (
        <div className="cal-sticky sticky top-0 z-10 flex h-10 items-center px-4 hairline-b text-[13px] font-semibold capitalize" aria-hidden>
          {activeDay.date ? dayTitle(activeDay.date, locale) : ""}
        </div>
      ) : null}
      <div style={{ height: v.getTotalSize(), position: "relative", marginTop: activeDay && !p.compact ? -40 : 0 }}>
        {v.getVirtualItems().map((vi) => {
          const it = items[vi.index];
          const style = { position: "absolute" as const, top: 0, left: 0, right: 0, transform: `translateY(${vi.start}px)`, height: vi.size };
          if (it.kind === "day")
            return (
              <h3 key={it.key} style={style} className="flex items-center px-4 text-[13px] font-semibold capitalize">
                {it.date ? dayTitle(it.date, locale) : ""}
              </h3>
            );
          if (it.kind === "section")
            return (
              <p key={it.key} style={style} className="flex items-end px-4 pb-1 text-[12px] font-semibold text-label-2">
                {it.label}
              </p>
            );
          const ev = it.ev;
          const room = p.model.roomById.get(ev.room);
          const progress = it.now ? Math.min(1, Math.max(0, (p.nowMin - periodStartMin(ev.sp)) / Math.max(1, periodEndMin(ev.ep) - periodStartMin(ev.sp)))) : null;
          return (
            <article key={it.key} style={style} aria-label={`${ev.a.label}, ${room?.name ?? ""}, ${spanText(ev.sp, ev.ep)}`} className="px-3 py-0.5">
              <button
                type="button"
                data-testid="calendar-event"
                data-assignment-id={ev.a.id}
                onClick={() => {
                  p.onSelect(ev.a.id, "replace");
                  p.onOpen(ev);
                }}
                className={cn("relative flex h-full w-full items-center gap-3 overflow-hidden rounded-[10px] px-3 text-left hover:bg-fill-3", p.selection.has(ev.a.id) && "bg-tint-soft", p.compact && "bg-fill-3")}
                style={chipVars(ev.a.slot)}
              >
                <span aria-hidden className="h-[70%] w-[3px] shrink-0 rounded-full" style={{ background: "var(--chip-bar)" }} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex min-w-0 items-baseline gap-2">
                    <span className="shrink-0 text-[13px] font-semibold">{ev.a.code ?? ev.a.label}{ev.a.sec ? ` §${ev.a.sec}` : ""}</span>
                    <span className="truncate text-[12px] text-label-2">{ev.a.name ?? ev.a.prog ?? ""}</span>
                  </span>
                  {p.compact ? (
                    <span className="truncate text-[12px] text-label-2 tabular-nums">
                      {room?.name ?? "—"} · {spanText(ev.sp, ev.ep)} · {ev.a.size}/{room ? (p.model.exam ? room.exam_capacity : room.capacity) : "—"}
                      {ev.conflict ? ` · ▲ ${t("calendar.state.conflict").toLocaleLowerCase(locale)}` : ""}
                    </span>
                  ) : null}
                </span>
                {!p.compact ? <span className="shrink-0 text-[12px] font-medium">{room?.name ?? "—"}</span> : null}
                {!p.compact ? <span className="w-24 shrink-0 text-right text-[12px] text-label-2 tabular-nums">P{ev.sp}–P{ev.ep}</span> : null}
                <span className="flex w-4 shrink-0 justify-end">{ev.conflict ? <AlertTriangle className="size-3.5 text-status-infeasible-fg" aria-label={t("calendar.state.conflict")} /> : ev.a.locked ? <Lock className="size-3.5 text-label-2" aria-label={t("calendar.state.locked")} /> : null}</span>
                {progress !== null ? <span aria-hidden className="absolute bottom-0 left-3 h-px origin-left bg-[var(--now)]" style={{ width: "calc(100% - 24px)", transform: `scaleX(${progress})` }} /> : null}
              </button>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export const AgendaLens = memo(AgendaImpl);
