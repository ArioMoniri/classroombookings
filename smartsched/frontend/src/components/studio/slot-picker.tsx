"use client";

import { Minus, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import type { TemplateField } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";
import { fold } from "./class-filters";
import type { AppliesTo, Slot } from "./rule-sentence";
import { useStudioData } from "./studio-data";

const TAGS = ["TIP", "PC", "LAB", "AMPHI"] as const;

function ToggleChip({ on, onClick, children, label }: { on: boolean; onClick: () => void; children: React.ReactNode; label?: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={label}
      onClick={onClick}
      className={cn("min-h-8 rounded-xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] px-2 text-xs pointer-coarse:min-h-11", on ? "border-primary bg-tint-soft font-medium text-tint-text" : "hover:bg-fill-2")}
    >
      {children}
    </button>
  );
}

const toggle = <T,>(list: T[], v: T): T[] => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

/** The editor for one slot type (room combobox, programme picker, day chips, period range, stepper…). */
export function SlotEditor({ field, value, onChange }: { field: TemplateField; value: unknown; onChange: (v: unknown) => void }) {
  const { t, locale } = useI18n();
  const { rooms, classes, sentence, termWeeks } = useStudioData();
  const [q, setQ] = useState("");
  const qf = fold(q).trim();
  const buildings = useMemo(() => [...new Set(rooms.map((r) => r.building_code))].sort(), [rooms]);
  const nums = (Array.isArray(value) ? value : []).map(Number);
  const strs = (Array.isArray(value) ? value : []).map(String);

  switch (field.type) {
    case "applies_to": {
      const v = (value as AppliesTo | null) ?? { mode: "all" };
      const prog = v.mode === "programs" ? (v.programs[0] ?? "") : "";
      const year = v.mode === "programs" ? v.year : null;
      return (
        <div className="grid gap-2" role="group" aria-label={t("studio.slot.appliesTo")}>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="applies" checked={v.mode === "all"} onChange={() => onChange({ mode: "all" })} />
            {t("studio.rule.allClasses")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="applies" checked={v.mode === "programs"} onChange={() => onChange({ mode: "programs", programs: [sentence.programs[0] ?? ""], year: null })} />
            {t("studio.slot.programme")}
          </label>
          {v.mode === "programs" ? (
            <div className="grid grid-cols-[1fr_6rem] gap-2 pl-6">
              <NativeSelect aria-label={t("studio.slot.programme")} value={prog} onChange={(e) => onChange({ mode: "programs", programs: [e.target.value], year })}>
                {sentence.programs.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect aria-label={t("studio.classes.year")} value={year ?? ""} onChange={(e) => onChange({ mode: "programs", programs: [prog], year: e.target.value ? Number(e.target.value) : null })}>
                <option value="">{t("studio.slot.allYears")}</option>
                {[1, 2, 3, 4, 5, 6].map((y) => (
                  <option key={y} value={y}>
                    {t("studio.classes.yearN", { n: y })}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
          {v.mode === "classes" ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="radio" name="applies" checked readOnly />
              {t("studio.rule.nClasses", { n: v.event_ids.length })}
            </label>
          ) : null}
          {v.mode === "other" ? <p className="text-xs text-label-2">{v.text}</p> : null}
        </div>
      );
    }
    case "applies_to_others": {
      const list = sentence.programs.filter((p) => !qf || fold(p).includes(qf));
      return (
        <div className="grid gap-2">
          <SearchBox value={q} onChange={setQ} label={t("studio.slot.programme")} />
          <div className="max-h-56 space-y-1 overflow-y-auto" role="group" aria-label={t("studio.slot.whoMayUse")}>
            {list.map((p) => (
              <label key={p} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={strs.includes(p)} onChange={() => onChange(toggle(strs, p))} />
                {p}
              </label>
            ))}
          </div>
        </div>
      );
    }
    case "building":
      return (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("common.building")}>
          {buildings.map((b) => (
            <ToggleChip key={b} on={value === b} onClick={() => onChange(value === b ? null : b)}>
              {t("studio.slot.block", { b })}
            </ToggleChip>
          ))}
        </div>
      );
    case "buildings":
      return (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("common.building")}>
          {buildings.map((b) => (
            <ToggleChip key={b} on={strs.includes(b)} onClick={() => onChange(toggle(strs, b))}>
              {t("studio.slot.block", { b })}
            </ToggleChip>
          ))}
        </div>
      );
    case "tag":
      return (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("rooms.tags")}>
          {TAGS.map((tag) => (
            <ToggleChip key={tag} on={strs.includes(tag)} onClick={() => onChange(toggle(strs, tag))}>
              {t(`rooms.tag.${tag}`)}
            </ToggleChip>
          ))}
        </div>
      );
    case "days":
      return (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("common.day")}>
          {[1, 2, 3, 4, 5, 6, 7].map((d) => (
            <ToggleChip key={d} on={nums.includes(d)} onClick={() => onChange(toggle(nums, d).sort((a, b) => a - b))}>
              {sentence.dayName(d)}
            </ToggleChip>
          ))}
        </div>
      );
    case "period":
      return (
        <NativeSelect aria-label={field.name} value={value === null || value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t("studio.rule.choose")}</option>
          {PERIODS.map((p) => (
            <option key={p.index} value={p.index}>
              {field.name === "earliest" ? t("studio.slot.periodStart", { p: p.index, time: p.start }) : t("studio.slot.periodEnd", { p: p.index, time: p.end })}
            </option>
          ))}
        </NativeSelect>
      );
    case "periods": {
      const s = nums.length ? Math.min(...nums) : null;
      const e = nums.length ? Math.max(...nums) : null;
      const set = (a: number | null, b: number | null) => (a && b && b >= a ? onChange(Array.from({ length: b - a + 1 }, (_, i) => a + i)) : onChange(a ? [a] : []));
      return (
        <div className="grid grid-cols-2 gap-2">
          <NativeSelect aria-label={t("studio.slot.from")} value={s ?? ""} onChange={(ev) => set(ev.target.value ? Number(ev.target.value) : null, e)}>
            <option value="">{t("studio.slot.from")}</option>
            {PERIODS.map((p) => (
              <option key={p.index} value={p.index}>{`P${p.index} ${p.start}`}</option>
            ))}
          </NativeSelect>
          <NativeSelect aria-label={t("studio.slot.to")} value={e ?? ""} onChange={(ev) => set(s, ev.target.value ? Number(ev.target.value) : null)}>
            <option value="">{t("studio.slot.to")}</option>
            {PERIODS.map((p) => (
              <option key={p.index} value={p.index}>{`P${p.index} ${p.end}`}</option>
            ))}
          </NativeSelect>
        </div>
      );
    }
    case "rooms":
    case "room": {
      const single = field.type === "room";
      const list = rooms.filter((r) => r.is_bookable && (!qf || fold(`${r.display_name} ${r.code} ${r.capacity} ${r.tags.join(" ")}`).includes(qf))).slice(0, 80);
      const chosen = single ? (value === null || value === undefined ? [] : [Number(value)]) : nums;
      return (
        <div className="grid gap-2">
          <SearchBox value={q} onChange={setQ} label={t("common.room")} />
          <div className="max-h-56 space-y-0.5 overflow-y-auto" role="group" aria-label={t("common.rooms")}>
            {list.map((r) => (
              <label key={r.id} className="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-fill-2">
                <input
                  type={single ? "radio" : "checkbox"}
                  name={single ? "room-pick" : undefined}
                  checked={chosen.includes(r.id)}
                  onChange={() => onChange(single ? r.id : toggle(nums, r.id))}
                />
                <span className="font-mono">{r.display_name}</span>
                <span className="ml-auto text-xs text-label-2">
                  {r.capacity} {t("common.seats")}
                </span>
              </label>
            ))}
          </div>
          {!single && chosen.length > 1 && field.ordered ? <p className="text-xs text-label-2">{t("studio.slot.ordered", { list: chosen.map(sentence.roomCode).join(" › ") })}</p> : null}
        </div>
      );
    }
    case "courses": {
      const list = (classes ?? []).filter((c) => !qf || fold(`${c.course_code} ${c.course_name} ${c.program_name}`).includes(qf)).slice(0, 60);
      return (
        <div className="grid gap-2">
          <SearchBox value={q} onChange={setQ} label={t("requests.course")} />
          <div className="max-h-56 space-y-0.5 overflow-y-auto" role="group" aria-label={t("requests.course")}>
            {list.map((c) => (
              <label key={c.id} className="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-fill-2">
                <input type="checkbox" checked={nums.includes(c.id)} onChange={() => onChange(toggle(nums, c.id))} />
                <span className="font-mono text-xs">
                  {c.course_code} §{c.section_label}
                </span>
                <span className="truncate text-xs text-label-2">{c.program_name}</span>
              </label>
            ))}
          </div>
        </div>
      );
    }
    case "date":
    case "weeks": {
      const ws = termWeeks.filter((w) => w.kind !== "HOLIDAY");
      const fromMode = field.type === "date";
      const start = nums.length ? Math.min(...nums) : null;
      return (
        <div className="flex flex-wrap gap-1" role="group" aria-label={t("common.week")}>
          {ws.map((w) => (
            <ToggleChip
              key={w.index}
              label={`W${w.index}`}
              on={fromMode ? start !== null && w.index >= start : nums.includes(w.index)}
              onClick={() => (fromMode ? onChange(ws.filter((x) => x.index >= w.index).map((x) => x.index)) : onChange(toggle(nums, w.index).sort((a, b) => a - b)))}
            >
              W{w.index}
            </ToggleChip>
          ))}
        </div>
      );
    }
    case "number": {
      const min = field.min ?? 0;
      const max = field.max ?? 99;
      const n = value === null || value === undefined ? (typeof field.default === "number" ? field.default : min) : Number(value);
      const set = (x: number) => onChange(Math.max(min, Math.min(max, x)));
      return (
        <div className="flex items-center gap-1">
          <button type="button" className="inline-flex size-8 items-center justify-center rounded-md border hover:bg-fill-2 pointer-coarse:size-11" aria-label={t("studio.slot.less")} onClick={() => set(n - 1)}>
            <Minus className="size-3.5" aria-hidden />
          </button>
          <Input type="number" className="w-16 text-center" min={min} max={max} value={n} aria-label={field.name} onChange={(e) => set(Number(e.target.value))} />
          <button type="button" className="inline-flex size-8 items-center justify-center rounded-md border hover:bg-fill-2 pointer-coarse:size-11" aria-label={t("studio.slot.more")} onClick={() => set(n + 1)}>
            <Plus className="size-3.5" aria-hidden />
          </button>
        </div>
      );
    }
    default:
      return <Input aria-label={field.name} defaultValue={value === null || value === undefined ? "" : String(value)} onBlur={(e) => onChange(e.target.value || null)} lang={locale} />;
  }
}

function SearchBox({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const { t } = useI18n();
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-label-2" aria-hidden />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("common.search")} aria-label={`${t("common.search")}: ${label}`} className="pl-7" />
    </div>
  );
}

/** A clickable slot in a rule sentence; opens its picker. Low-confidence values get a dotted underline. */
export function SlotChip({ slot, onChange, readOnly, uncertain }: { slot: Slot; onChange?: (v: unknown) => void; readOnly?: boolean; uncertain?: boolean }) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<unknown>(slot.value);
  const cls = cn(
    "mx-0.5 inline-flex max-w-full items-center rounded-[var(--radius-xs)] border px-1.5 py-0.5 align-baseline text-[0.95em] font-medium leading-snug",
    slot.empty ? "border-dashed border-status-warning-border text-status-warning-fg" : "border-border-strong/60 bg-fill-2/60 text-foreground",
    uncertain && "underline decoration-dotted underline-offset-4",
  );
  if (readOnly || !onChange) return <span className={cls}>{slot.display}</span>;
  return (
    <Popover
      onOpenChange={(open) => {
        if (open) setDraft(slot.value);
      }}
    >
      <PopoverTrigger
        render={<button type="button" className={cn(cls, "hover:border-primary hover:text-primary pointer-coarse:min-h-11")} aria-label={t("studio.slot.change", { name: t(slotNameKey(slot.field.type)), value: slot.display })} data-testid={`slot-${slot.name}`} />}
      >
        <span className="truncate">{slot.display}</span>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <p className="text-xs font-medium text-label-2">
          {t(slotNameKey(slot.field.type))}
          {slot.field.required ? ` ${t("studio.builder.required")}` : ""}
        </p>
        <SlotEditor
          field={slot.field}
          value={draft}
          onChange={(v) => {
            setDraft(v);
            onChange(v);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

export function slotNameKey(type: string) {
  switch (type) {
    case "applies_to":
      return "studio.slot.appliesTo" as const;
    case "applies_to_others":
      return "studio.slot.whoMayUse" as const;
    case "building":
    case "buildings":
      return "common.building" as const;
    case "days":
      return "common.day" as const;
    case "period":
    case "periods":
      return "studio.slot.time" as const;
    case "tag":
      return "rooms.tags" as const;
    case "rooms":
    case "room":
      return "common.room" as const;
    case "courses":
      return "requests.course" as const;
    case "date":
    case "weeks":
      return "common.week" as const;
    default:
      return "studio.slot.value" as const;
  }
}
