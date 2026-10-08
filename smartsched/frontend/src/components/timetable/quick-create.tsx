"use client";
/**
 * Quick-create popover after a drag across empty slots (calendar.md §9.4):
 * - Rezervasyon: a CRBS-style booking through `/api/v1/bookings` (one booking per booking period inside the
 *   range; "every week" uses the recurring endpoint). Disabled with a reason when the room has no booking
 *   periods configured.
 * - Ders talebi: pick a class (unplaced first). A class already placed in this run is moved here
 *   (bulk-move); an unplaced one is pinned to this room and time for the next run (room_pin + fixed_time),
 *   because placing a new assignment needs a backend endpoint that does not exist yet.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { calendarApi, calKeys } from "@/lib/api/calendar";
import { HttpError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { FloatingPanel } from "./floating-panel";
import { slotFree, whenText } from "./model/check";
import { dateOf } from "./model/dates";
import { fold } from "./model/filters";
import { roomCap, type CalendarModel } from "./model/index-model";
import type { GridColumn } from "./time-grid";

export interface CreateRequest {
  column: GridColumn;
  room: number;
  sp: number;
  ep: number;
  anchor: { x: number; y: number };
  defaultTab: "booking" | "request";
}

interface Pick {
  key: string;
  label: string;
  sub: string;
  mr: number | null;
  aid: number | null;
}

export function QuickCreate({ model, req, week, onClose, onMoveHere }: { model: CalendarModel; req: CreateRequest | null; week: number; onClose: () => void; onMoveHere: (aid: number, target: { room: number; day: number; sp: number; ep: number }) => Promise<boolean> }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const titleId = useId();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"booking" | "request">(req?.defaultTab ?? "request");
  const [note, setNote] = useState("");
  const [repeat, setRepeat] = useState<"week" | "term">("week");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Pick | null>(null);
  const [periods, setPeriods] = useState<{ id: number; start_period: number; end_period: number }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const reqKey = req ? `${req.room}:${req.column.day}:${req.sp}:${req.ep}` : "";
  const date = req ? dateOf(model.index.weeks, week, req.column.day) : null;

  useEffect(() => {
    if (!req) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    setTab(req.defaultTab);
    setNote("");
    setQuery("");
    setPicked(null);
    setPeriods(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    if (!date) return;
    let alive = true;
    calendarApi
      .bookingPeriods(req.room, date)
      .then((ps) => alive && setPeriods(ps))
      .catch(() => alive && setPeriods([]));
    return () => {
      alive = false;
    };
  }, [reqKey, req, date]);

  // typing a course code right after the drag jumps into the class search (Fibery "title in place")
  useEffect(() => {
    if (!req) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.key.length !== 1 || !/[\p{L}\d]/u.test(e.key)) return;
      if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) return;
      setTab("request");
      setQuery((q) => q + e.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [req]);

  const candidates = useMemo<Pick[]>(() => {
    const q = fold(query);
    const unplaced: Pick[] = model.unplaced.map((u) => ({ key: `u${u.mr}`, label: u.label, sub: `${u.prog ?? ""}${u.year ? ` · ${u.year}` : ""} · ${u.size}`, mr: u.mr, aid: null }));
    const seen = new Set<number>();
    const placed: Pick[] = [];
    for (const e of model.events) {
      if (seen.has(e.a.id)) continue;
      seen.add(e.a.id);
      placed.push({ key: `a${e.a.id}`, label: e.a.label, sub: `${model.roomById.get(e.room)?.name ?? ""} · ${whenText(e.day, e.sp, e.ep)[lang]}`, mr: e.a.mr ?? null, aid: e.a.id });
    }
    const match = (p: Pick) => !q || fold(`${p.label} ${p.sub}`).includes(q);
    return [...unplaced.filter(match).slice(0, 30), ...(q ? placed.filter(match).slice(0, 30) : [])];
  }, [model, query, lang]);

  if (!req) return null;
  const room = model.roomById.get(req.room);
  const free = slotFree(model, req.room, req.column.day, req.sp, req.ep, model.allMask & (1 << (week - 1)));
  const inRange = (periods ?? []).filter((p) => p.start_period >= req.sp && p.end_period <= req.ep);
  const target = { room: req.room, day: req.column.day, sp: req.sp, ep: req.ep };
  const when = whenText(req.column.day, req.sp, req.ep)[lang];

  const book = async () => {
    if (!date || !inRange.length) return;
    setBusy(true);
    try {
      for (const p of inRange) {
        if (repeat === "term") await calendarApi.createRecurring({ room_id: req.room, date, period_id: p.id, notes: note || undefined, term_id: model.index.run.term_id });
        else await calendarApi.createBooking({ room_id: req.room, date, period_id: p.id, notes: note || undefined, term_id: model.index.run.term_id });
      }
      toast.success(t("calendar.create.booked", { room: room?.name ?? "", when }));
      void qc.invalidateQueries({ queryKey: calKeys.index(model.index.run.id) });
      onClose();
    } catch (e) {
      toast.error(t("calendar.create.bookFailed", { reason: e instanceof HttpError ? e.message : String(e) }));
    } finally {
      setBusy(false);
    }
  };

  const place = async () => {
    if (!picked) return;
    setBusy(true);
    try {
      if (picked.aid !== null) {
        if (await onMoveHere(picked.aid, target)) onClose();
        return;
      }
      if (picked.mr === null) return;
      const base = { term_id: model.index.run.term_id, run_id: null, hardness: "hard" as const, weight: 1, source: "ADMIN" as const, enabled: true };
      await api.constraints.create({ ...base, kind: "room_pin", params: { event_ids: [picked.mr], room_ids: [req.room] }, nl_text: `${picked.label} → ${room?.name ?? ""}` });
      await api.constraints.create({ ...base, kind: "fixed_time", params: { event_ids: [picked.mr], day: req.column.day, start: req.sp }, nl_text: `${picked.label} → ${when}` });
      toast.success(t("calendar.create.pinned", { code: picked.label, room: room?.name ?? "", when }));
      onClose();
    } catch (e) {
      toast.error(t("calendar.create.bookFailed", { reason: e instanceof HttpError ? e.message : String(e) }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <FloatingPanel open anchor={req.anchor} onClose={onClose} labelledBy={titleId} width={360} testId="quick-create">
      <div
        className="flex flex-col gap-3"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void (tab === "booking" ? book() : place());
          }
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <p id={titleId} className="text-[13px] font-semibold" data-testid="booking-slot" data-room-id={req.room} data-day={req.column.day} data-period={req.sp}>
              {t("calendar.create.slot", { room: room?.name ?? "", when, n: req.ep - req.sp + 1 })}
            </p>
            <p className={cn("text-[12px]", free ? "text-status-feasible-fg" : "text-status-warning-fg")}>{free ? `✓ ${t("calendar.create.free", { cap: roomCap(model, room) })}` : t("calendar.create.busy")}</p>
          </div>
        </div>
        <SegmentedGlass
          fill
          size="sm"
          aria-label={t("calendar.create.label", { room: room?.name ?? "" })}
          options={[
            { value: "booking", label: t("calendar.create.booking") },
            { value: "request", label: t("calendar.create.request") },
          ]}
          value={tab}
          onValueChange={setTab}
        />
        {tab === "booking" ? (
          <div className="flex flex-col gap-2.5">
            {periods !== null && periods.length === 0 ? <p className="text-[12px] text-label-2">{t("calendar.create.noPeriods")}</p> : null}
            <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
              {t("calendar.create.title")}
              <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={255} placeholder={t("calendar.create.note")} />
            </label>
            <fieldset className="flex flex-col gap-1 text-[13px]">
              <legend className="mb-1 text-[12px] font-semibold text-label-2">{t("calendar.create.repeat")}</legend>
              {(["week", "term"] as const).map((r) => (
                <label key={r} className="flex items-center gap-2">
                  <input type="radio" name={`${titleId}-repeat`} checked={repeat === r} onChange={() => setRepeat(r)} className="accent-(--accent)" />
                  {r === "week" ? t("calendar.create.thisWeek") : t("calendar.create.wholeTerm")}
                </label>
              ))}
            </fieldset>
            <div className="flex justify-end">
              <Button size="sm" data-testid="booking-create" disabled={busy || !inRange.length || !free} onClick={() => void book()}>
                {t("calendar.create.book")} <kbd className="ml-1 text-[11px] opacity-80">⌘↵</kbd>
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Input data-autofocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("calendar.create.search")} aria-label={t("calendar.create.search")} />
            <p className="text-[11px] font-semibold text-label-2">{query ? t("calendar.create.allClasses") : t("calendar.create.unplacedFirst", { n: model.unplaced.length })}</p>
            <ul className="max-h-48 overflow-y-auto" role="listbox" aria-label={t("calendar.create.search")}>
              {candidates.length === 0 ? <li className="px-2 py-1.5 text-[12px] text-label-2">{t("calendar.create.noMatch")}</li> : null}
              {candidates.map((c) => (
                <li key={c.key}>
                  <button type="button" role="option" aria-selected={picked?.key === c.key} onClick={() => setPicked(c)} className={cn("flex w-full flex-col rounded-lg px-2 py-1 text-left hover:bg-fill-2", picked?.key === c.key && "bg-tint-soft", c.aid === null && "cal-unplaced my-0.5 border-[var(--label-3)]")}>
                    <span className="text-[13px] font-semibold">{c.label}</span>
                    <span className="truncate text-[11px] text-label-2">{c.sub}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex justify-end">
              <Button size="sm" disabled={busy || !picked} onClick={() => void place()}>
                {picked?.aid ? t("calendar.create.place") : t("calendar.create.later")} <kbd className="ml-1 text-[11px] opacity-80">⌘↵</kbd>
              </Button>
            </div>
          </div>
        )}
      </div>
    </FloatingPanel>
  );
}
