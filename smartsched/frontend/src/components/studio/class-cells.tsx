"use client";

import { Lock, LockOpen, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ClassMode, ClassRow, MeetingPatch, Pin } from "@/lib/api/studio-schemas";
import { ClassMode as ClassModeEnum } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { SlotEditor } from "./slot-picker";
import { changedIn, type FieldGroup } from "./use-class-edit";

export const MODE_KEY: Record<ClassMode, MessageKey> = {
  F2F: "studio.mode.F2F",
  ONLINE: "studio.mode.ONLINE",
  HYBRID: "studio.mode.HYBRID",
  UZEM: "studio.mode.UZEM",
  ASYNC: "studio.mode.ASYNC",
  HOSPITAL: "studio.mode.HOSPITAL",
  SIMULATION: "studio.mode.SIMULATION",
  OTHER: "studio.mode.OTHER",
};
const ROOMLESS = new Set(["ONLINE", "UZEM", "ASYNC", "HOSPITAL"]);

export function dayTimeLabel(r: ClassRow, locale: string, noTime: string): string {
  if (r.start_period === null || r.end_period === null) return noTime;
  const day = r.day ?? r.days[0] ?? null;
  const a = PERIODS[r.start_period - 1];
  const b = PERIODS[r.end_period - 1];
  return `${day ? dayName(day, locale, "short") : "—"} P${r.start_period}–P${r.end_period} · ${a?.start ?? ""}–${b?.end ?? ""}`;
}

/** Wraps an editable cell: amber underline + "↺" when it differs from the imported file. */
export function ChangedMark({ row, group, onRevert, children }: { row: ClassRow; group: FieldGroup; onRevert: (fields: string[]) => void; children: ReactNode }) {
  const { t } = useI18n();
  const changed = changedIn(row, group);
  if (!changed.length) return <>{children}</>;
  const imported = changed.map((c) => (Array.isArray(c.imported) ? c.imported.join(", ") : String(c.imported ?? "—"))).join(" · ");
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <span className="border-b-2 border-status-warning-border" title={t("studio.classes.changedFrom", { value: imported })}>
        {children}
        <span className="sr-only">, {t("studio.classes.changedFrom", { value: imported })}</span>
      </span>
      <button type="button" onClick={() => onRevert(changed.map((c) => c.field))} className="inline-flex size-6 shrink-0 items-center justify-center rounded text-status-warning-fg hover:bg-status-warning pointer-coarse:size-11" aria-label={t("studio.classes.revertField", { field: t(`studio.classes.col.${group}`) })} data-testid="revert-field">
        <RotateCcw className="size-3" aria-hidden />
      </button>
    </span>
  );
}

export function StudentsCell({ row, onSave, warning }: { row: ClassRow; onSave: (patch: MeetingPatch) => void; warning?: string }) {
  const { t, n } = useI18n();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(row.enrolment ?? ""));
  if (editing)
    return (
      <Input
        autoFocus
        type="number"
        min={0}
        max={5000}
        className="h-7 w-20"
        value={value}
        aria-label={t("studio.classes.edit", { field: t("studio.classes.col.students") })}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") {
            setValue(String(row.enrolment ?? ""));
            setEditing(false);
          }
        }}
        onBlur={() => {
          setEditing(false);
          const v = value.trim() === "" ? null : Number(value);
          if (v !== row.enrolment && (v === null || Number.isFinite(v))) onSave({ enrolment: v });
        }}
        data-testid="students-input"
      />
    );
  return (
    <span className="inline-flex flex-col">
      <button
        type="button"
        className="rounded px-1 text-right tabular-nums hover:bg-fill-2"
        onClick={() => {
          setValue(String(row.enrolment ?? ""));
          setEditing(true);
        }}
        aria-label={t("studio.classes.editValue", { field: t("studio.classes.col.students"), value: row.enrolment ?? "—" })}
        data-edit="students"
      >
        {row.enrolment !== null ? n(row.enrolment) : "—"}
      </button>
      {warning ? <span className="text-[11px] text-status-warning-fg">{warning}</span> : null}
    </span>
  );
}

export function ModeCell({ row, onSave }: { row: ClassRow; onSave: (patch: MeetingPatch) => void }) {
  const { t } = useI18n();
  const mode = (ClassModeEnum.options as readonly string[]).includes(row.mode ?? "") ? (row.mode as ClassMode) : "OTHER";
  return (
    <span className="inline-flex flex-col">
      <NativeSelect className="h-7 w-36 text-xs" value={mode} aria-label={t("studio.classes.edit", { field: t("studio.classes.col.mode") })} onChange={(e) => onSave({ mode: e.target.value as ClassMode })}>
        {ClassModeEnum.options.map((m) => (
          <option key={m} value={m}>
            {t(MODE_KEY[m])}
          </option>
        ))}
      </NativeSelect>
      {ROOMLESS.has(mode) ? <span className="text-[11px] text-label-2">{t("studio.classes.noRoomNeeded")}</span> : null}
    </span>
  );
}

export function DayTimeCell({ row, onSave }: { row: ClassRow; onSave: (patch: MeetingPatch) => void }) {
  const { t, locale } = useI18n();
  const [day, setDay] = useState<number | null>(row.day ?? row.days[0] ?? null);
  const [start, setStart] = useState<number | null>(row.start_period);
  const [end, setEnd] = useState<number | null>(row.end_period);
  const [flex, setFlex] = useState(row.flexible_day);
  const [open, setOpen] = useState(false);
  const label = dayTimeLabel(row, locale, t("studio.classes.noTime"));
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setDay(row.day ?? row.days[0] ?? null);
          setStart(row.start_period);
          setEnd(row.end_period);
          setFlex(row.flexible_day);
        }
      }}
    >
      <PopoverTrigger render={<button type="button" className={cn("rounded px-1 text-left whitespace-nowrap hover:bg-fill-2", row.start_period === null && "text-status-warning-fg")} aria-label={t("studio.classes.editValue", { field: t("studio.classes.col.dayTime"), value: label })} data-edit="dayTime" />}>
        {label}
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <div className="grid gap-2 text-sm">
          <label className="grid gap-1">
            <span className="text-xs font-medium">{t("common.day")}</span>
            <NativeSelect value={day ?? ""} onChange={(e) => setDay(e.target.value ? Number(e.target.value) : null)} disabled={flex}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                <option key={d} value={d}>
                  {dayName(d, locale)}
                </option>
              ))}
            </NativeSelect>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1">
              <span className="text-xs font-medium">{t("studio.slot.from")}</span>
              <NativeSelect value={start ?? ""} onChange={(e) => setStart(e.target.value ? Number(e.target.value) : null)}>
                <option value="">—</option>
                {PERIODS.map((p) => (
                  <option key={p.index} value={p.index}>{`P${p.index} ${p.start}`}</option>
                ))}
              </NativeSelect>
            </label>
            <label className="grid gap-1">
              <span className="text-xs font-medium">{t("studio.slot.to")}</span>
              <NativeSelect value={end ?? ""} onChange={(e) => setEnd(e.target.value ? Number(e.target.value) : null)}>
                <option value="">—</option>
                {PERIODS.map((p) => (
                  <option key={p.index} value={p.index}>{`P${p.index} ${p.end}`}</option>
                ))}
              </NativeSelect>
            </label>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={flex} onChange={(e) => setFlex(e.target.checked)} /> {t("studio.classes.flexible")}
          </label>
          {start && end && end < start ? <p className="text-xs text-status-infeasible-fg">{t("studio.classes.endBeforeStart")}</p> : null}
          <Button
            size="sm"
            disabled={Boolean(start && end && end < start)}
            onClick={() => {
              onSave({ day: flex ? null : day, start_period: start, end_period: end, flexible_day: flex });
              setOpen(false);
            }}
          >
            {t("common.save")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function RoomsCell({ row, onSave }: { row: ClassRow; onSave: (patch: MeetingPatch) => void }) {
  const { t } = useI18n();
  const [ids, setIds] = useState<number[]>(row.requested_room_ids);
  const chips = row.requested_room_codes.length ? row.requested_room_codes : row.requested_building ? [t("studio.slot.block", { b: row.requested_building })] : [];
  return (
    <Popover
      onOpenChange={(o) => {
        if (o) setIds(row.requested_room_ids);
        else if (JSON.stringify(ids) !== JSON.stringify(row.requested_room_ids)) onSave({ requested_room_ids: ids });
      }}
    >
      <PopoverTrigger render={<button type="button" className="flex max-w-56 flex-wrap gap-1 rounded px-1 text-left hover:bg-fill-2" aria-label={t("studio.classes.editValue", { field: t("studio.classes.col.rooms"), value: chips.join(", ") || "—" })} data-edit="rooms" />}>
        {chips.length ? chips.slice(0, 3).map((c) => <span key={c} className="rounded border px-1 font-mono text-[11px]">{c}</span>) : <span className="text-label-2">—</span>}
        {chips.length > 3 ? <span className="text-[11px] text-label-2">+{chips.length - 3}</span> : null}
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <p className="text-xs font-medium text-label-2">{t("studio.classes.col.rooms")}</p>
        <SlotEditor field={{ name: "rooms", type: "rooms", param: "requested_room_ids", required: false, ordered: true }} value={ids} onChange={(v) => setIds(Array.isArray(v) ? v.map(Number) : [])} />
        <p className="text-[11px] text-label-2">{t("studio.classes.roomsHint", { n: row.enrolment ?? 0 })}</p>
      </PopoverContent>
    </Popover>
  );
}

export function PinCell({ row, pin, roomCode, rooms, onPin, onUnpin, open, onOpenChange }: { row: ClassRow; pin: Pin | undefined; roomCode: (id: number) => string; rooms: { id: number; display_name: string; capacity: number; is_bookable: boolean }[]; onPin: (p: Pin) => void; onUnpin: () => void; open?: boolean; onOpenChange?: (v: boolean) => void }) {
  const { t, locale } = useI18n();
  const initialRoom = pin?.room_ids[0] ?? row.definitive_room_ids[0] ?? row.requested_room_ids[0] ?? null;
  const [room, setRoom] = useState<number | null>(initialRoom);
  const fit = rooms.filter((r) => r.is_bookable && r.capacity >= (row.enrolment ?? 0));
  const label = pin ? (pin.room_ids.length ? pin.room_ids.map(roomCode).join(", ") : pin.day ? `${dayName(pin.day, locale, "short")} P${pin.start_period ?? ""}` : t("studio.pin.pinned")) : null;
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger render={<button type="button" className={cn("inline-flex items-center gap-1 rounded px-1 py-0.5 text-xs pointer-coarse:min-h-11", pin ? "bg-status-locked text-status-locked-fg" : "text-label-2 hover:bg-fill-2")} aria-label={pin ? t("studio.pin.pinnedTo", { where: label ?? "" }) : t("studio.pin.title")} data-testid="pin-button" />}>
        {pin ? <Lock className="size-3.5" aria-hidden /> : <LockOpen className="size-3.5" aria-hidden />}
        {label ? <span className="max-w-24 truncate">{label}</span> : null}
      </PopoverTrigger>
      <PopoverContent className="w-72" align="end">
        <div className="grid gap-2 text-sm">
          <p className="text-xs font-medium text-label-2">{t("studio.pin.title")}</p>
          <label className="grid gap-1">
            <span>{t("studio.pin.room")}</span>
            <NativeSelect value={room ?? ""} onChange={(e) => setRoom(e.target.value ? Number(e.target.value) : null)}>
              <option value="">{t("studio.pin.pickRoom")}</option>
              {fit.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.display_name} · {r.capacity}
                </option>
              ))}
            </NativeSelect>
          </label>
          <Button size="sm" disabled={room === null} onClick={() => room !== null && onPin({ event_id: row.id, room_ids: [room], day: null, start_period: null })} data-testid="pin-room">
            {t("studio.pin.room")}
          </Button>
          <Button size="sm" variant="outline" disabled={row.start_period === null} onClick={() => onPin({ event_id: row.id, room_ids: [], day: row.day ?? row.days[0] ?? null, start_period: row.start_period })}>
            {t("studio.pin.time")}
          </Button>
          {pin ? (
            <Button size="sm" variant="ghost" onClick={onUnpin}>
              {t("studio.pin.remove")}
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
