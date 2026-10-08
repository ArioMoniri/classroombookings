"use client";
/**
 * "Filtre +" (all-classes.md §7.2, Linear #2): a type-ahead field list, then values with facet counts computed
 * against the other active filters, plus the removable chips row ("Gün: Pzt, Sal ✕"). The time window snaps to
 * period starts with Örtüşen / Tamamen içinde; building / room / day can apply to İstenen or Yerleşen.
 */
import { ChevronLeft, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Slider } from "@/components/ui/slider";
import type { ClassRow } from "@/lib/api/classes";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { fold } from "@/components/timetable/model/filters";
import { FILTER_FIELDS, activeFields, clearField, facetCounts, type ClassFilters, type FilterField } from "./classes-model";

const FIELD_KEY: Record<FilterField, MessageKey> = {
  faculty: "classes.f.faculty", program: "classes.f.program", year: "classes.f.year", instructor: "classes.f.instructor", building: "classes.f.building", room: "classes.f.room", day: "classes.f.day", time: "classes.f.time", mode: "classes.f.mode", status: "classes.f.status", issue: "classes.f.issue", changed: "classes.f.changed", locked: "classes.f.locked",
};

export function useValueLabels(rows: readonly ClassRow[]) {
  const { t, locale } = useI18n();
  return useMemo(() => {
    const fac = new Map<string, string>();
    const prog = new Map<string, string>();
    const instr = new Map<string, string>();
    const room = new Map<string, string>();
    for (const r of rows) {
      if (r.faculty_id) fac.set(String(r.faculty_id), r.faculty_name ?? "");
      if (r.program_id) prog.set(String(r.program_id), r.program_name ?? "");
      r.instructors.forEach((i) => instr.set(fold(i.name), i.name));
      [...(r.placement?.room_codes ?? []), ...r.req.room_codes].forEach((c) => room.set(fold(c), c));
    }
    return (field: FilterField, key: string): string => {
      switch (field) {
        case "faculty":
          return fac.get(key) ?? key;
        case "program":
          return prog.get(key) ?? key;
        case "instructor":
          return instr.get(key) ?? key;
        case "room":
          return room.get(key) ?? key;
        case "day":
          return dayName(Number(key), locale);
        case "year":
          return locale === "tr" ? `${key}. sınıf` : `Year ${key}`;
        case "mode":
          return t(`classes.mode.${key}` as MessageKey);
        case "status":
          return key.startsWith("req:") ? t(`classes.req.${key.slice(4)}` as MessageKey) : t(`classes.status.${key.slice(3)}` as MessageKey);
        case "issue":
          return key === "hard" ? t("classes.f.hard") : key === "soft" ? t("classes.f.soft") : t("classes.f.no");
        case "changed":
        case "locked":
          return key === "yes" ? t("classes.f.yes") : t("classes.f.no");
        default:
          return key;
      }
    };
  }, [rows, t, locale]);
}

function isOn(f: ClassFilters, field: FilterField, key: string): boolean {
  switch (field) {
    case "faculty":
      return f.faculty.includes(Number(key));
    case "program":
      return f.program.includes(Number(key));
    case "year":
      return f.year.includes(Number(key));
    case "instructor":
      return f.instructor.includes(key);
    case "building":
      return f.building.includes(key);
    case "room":
      return f.room.includes(key);
    case "day":
      return f.day.includes(Number(key));
    case "mode":
      return f.mode.includes(key);
    case "status":
      return key.startsWith("req:") ? f.status.includes(key.slice(4)) : f.placement.includes(key.slice(3) as never);
    case "issue":
      return f.issue === key || (key === "none" && false);
    case "changed":
      return f.changed === (key === "yes");
    case "locked":
      return f.locked === (key === "yes");
    default:
      return false;
  }
}

export function toggleValue(f: ClassFilters, field: FilterField, key: string): ClassFilters {
  const tog = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  switch (field) {
    case "faculty":
      return { ...f, faculty: tog(f.faculty, Number(key)) };
    case "program":
      return { ...f, program: tog(f.program, Number(key)) };
    case "year":
      return { ...f, year: tog(f.year, Number(key)) };
    case "instructor":
      return { ...f, instructor: tog(f.instructor, key) };
    case "building":
      return { ...f, building: tog(f.building, key) };
    case "room":
      return { ...f, room: tog(f.room, key) };
    case "day":
      return { ...f, day: tog(f.day, Number(key)) };
    case "mode":
      return { ...f, mode: tog(f.mode, key) };
    case "status":
      return key.startsWith("req:") ? { ...f, status: tog(f.status, key.slice(4)) } : { ...f, placement: tog(f.placement, key.slice(3) as never) };
    case "issue":
      return { ...f, issue: f.issue === key ? null : (key as ClassFilters["issue"]) };
    case "changed":
      return { ...f, changed: f.changed === (key === "yes") ? null : key === "yes" };
    case "locked":
      return { ...f, locked: f.locked === (key === "yes") ? null : key === "yes" };
    default:
      return f;
  }
}

function TimeWindow({ f, onChange }: { f: ClassFilters; onChange: (f: ClassFilters) => void }) {
  const { t } = useI18n();
  const w = f.time ?? { from: 1, to: PERIODS.length, mode: "overlap" as const };
  return (
    <div className="flex flex-col gap-3 p-1">
      <p className="text-[13px] font-medium tabular-nums">{PERIODS[w.from - 1].start}–{PERIODS[w.to - 1].end}</p>
      <Slider min={1} max={PERIODS.length} step={1} value={[w.from, w.to]} onValueChange={(v) => {
        const [a, b] = Array.isArray(v) ? v : [v, v];
        onChange({ ...f, time: { from: Math.min(a, b), to: Math.max(a, b), mode: w.mode } });
      }} />
      <SegmentedGlass size="sm" aria-label={t("classes.f.time")} options={[{ value: "overlap", label: t("classes.f.overlap") }, { value: "within", label: t("classes.f.within") }]} value={w.mode} onValueChange={(m) => onChange({ ...f, time: { ...w, mode: m } })} />
      <div className="flex gap-1.5">
        <Chip size="sm" onClick={() => onChange({ ...f, time: { from: 12, to: PERIODS.length, mode: "within" } })}>{t("classes.f.after1730")}</Chip>
        {f.time ? <Button size="xs" variant="ghost" onClick={() => onChange({ ...f, time: null })}>{t("classes.clear")}</Button> : null}
      </div>
    </div>
  );
}

export function FilterMenu({ rows, filters, onChange, shownCount, triggerRef }: { rows: readonly ClassRow[]; filters: ClassFilters; onChange: (f: ClassFilters) => void; shownCount: number; triggerRef?: React.Ref<HTMLButtonElement> }) {
  const { t, n } = useI18n();
  const [open, setOpen] = useState(false);
  const [field, setField] = useState<FilterField | null>(null);
  const [q, setQ] = useState("");
  const label = useValueLabels(rows);
  const counts = useMemo(() => (field && field !== "time" ? facetCounts(rows, filters, field) : new Map<string, number>()), [rows, filters, field]);
  const values = useMemo(() => {
    const list = [...counts.entries()].map(([k, c]) => ({ k, c, l: label(field ?? "faculty", k) }));
    const qf = fold(q);
    const filtered = qf ? list.filter((x) => fold(x.l).includes(qf)) : list;
    if (field === "day" || field === "year") return filtered.sort((a, b) => Number(a.k) - Number(b.k));
    return filtered.sort((a, b) => b.c - a.c || a.l.localeCompare(b.l, "tr"));
  }, [counts, label, field, q]);
  const fields = FILTER_FIELDS.filter((x) => !q || field || fold(t(FIELD_KEY[x])).includes(fold(q)));
  const whereField = field === "building" || field === "room" || field === "day" || field === "time";

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setField(null); setQ(""); } }}>
      <PopoverTrigger ref={triggerRef} render={<Button variant="ghost" size="sm" data-testid="filter-menu" />}>
        {t("classes.filter")} <Plus aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-1.5">
        <div className="flex items-center gap-1">
          {field ? <Button variant="ghost" size="icon-xs" aria-label={t("calendar.nav.prev")} onClick={() => { setField(null); setQ(""); }}><ChevronLeft /></Button> : null}
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={field ? t("classes.f.searchValues") : t("classes.filter")} aria-label={field ? t("classes.f.searchValues") : t("classes.filter")} className="h-8 flex-1 rounded-lg bg-fill-2 px-2.5 text-[13px] outline-none focus-visible:outline-2 focus-visible:outline-(--focus)" />
        </div>
        {field ? (
          <div className="mt-1 flex flex-col gap-1">
            <p className="px-2 pt-1 text-[11px] font-semibold text-label-3">{t(FIELD_KEY[field])}</p>
            {whereField ? (
              <div className="px-1">
                <SegmentedGlass size="sm" fill aria-label={t(FIELD_KEY[field])} options={[{ value: "placed", label: t("classes.f.placed") }, { value: "requested", label: t("classes.f.requested") }]} value={field === "day" || field === "time" ? filters.dayWhere : filters.buildingWhere} onValueChange={(v) => onChange(field === "day" || field === "time" ? { ...filters, dayWhere: v } : { ...filters, buildingWhere: v })} />
              </div>
            ) : null}
            {field === "time" ? (
              <TimeWindow f={filters} onChange={onChange} />
            ) : (
              <ul className="max-h-72 overflow-y-auto" role="listbox" aria-label={t(FIELD_KEY[field])} aria-multiselectable>
                {values.slice(0, 200).map((v) => {
                  const on = isOn(filters, field, v.k);
                  return (
                    <li key={v.k}>
                      <button type="button" role="option" aria-selected={on} onClick={() => onChange(toggleValue(filters, field, v.k))} className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-fill-2", on && "bg-tint-soft")}>
                        <span className={cn("flex size-4 shrink-0 items-center justify-center rounded-[5px] text-[10px]", on ? "bg-tint text-tint-foreground" : "shadow-[inset_0_0_0_1px_var(--hairline-strong)]")} aria-hidden>{on ? "✓" : ""}</span>
                        {field === "faculty" ? <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: `var(--fac-${rows.find((r) => String(r.faculty_id) === v.k)?.faculty_slot ?? 8}-bar)` }} /> : null}
                        <span className="min-w-0 flex-1 truncate">{v.l}</span>
                        <span className="text-[11px] text-label-3 tabular-nums">{n(v.c)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex items-center justify-between px-1 pt-1">
              <Button size="xs" variant="ghost" onClick={() => onChange(clearField(filters, field))}>{t("classes.clear")}</Button>
              <Button size="xs" onClick={() => setOpen(false)}>{t("classes.showN", { n: n(shownCount) })}</Button>
            </div>
          </div>
        ) : (
          <ul className="mt-1" role="menu">
            {fields.map((x) => (
              <li key={x}>
                <button type="button" role="menuitem" onClick={() => { setField(x); setQ(""); }} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-fill-2">
                  {t(FIELD_KEY[x])}
                  {activeFields(filters).includes(x) ? <span aria-hidden className="size-1.5 rounded-full bg-tint" /> : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

export function FilterChips({ rows, filters, onChange }: { rows: readonly ClassRow[]; filters: ClassFilters; onChange: (f: ClassFilters) => void }) {
  const { t } = useI18n();
  const label = useValueLabels(rows);
  const fields = activeFields(filters);
  if (!fields.length) return null;
  const values = (field: FilterField): string => {
    switch (field) {
      case "time":
        return filters.time ? `${PERIODS[filters.time.from - 1].start}–${PERIODS[filters.time.to - 1].end} (${filters.time.mode === "overlap" ? t("classes.f.overlap") : t("classes.f.within")})` : "";
      case "status":
        return [...filters.status.map((s) => label("status", `req:${s}`)), ...filters.placement.map((s) => label("status", `pl:${s}`))].join(", ");
      case "issue":
        return filters.issue === "any" ? t("classes.f.any") : label("issue", filters.issue ?? "");
      case "changed":
        return filters.changed ? t("classes.f.yes") : t("classes.f.no");
      case "locked":
        return filters.locked ? t("classes.f.yes") : t("classes.f.no");
      default: {
        const arr = (filters[field] as (string | number)[]).map(String);
        return arr.map((k) => label(field, k)).join(", ");
      }
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="filter-chips">
      {fields.map((f) => (
        <Chip key={f} size="sm" onRemove={() => onChange(clearField(filters, f))} removeLabel={t("classes.f.remove", { name: t(FIELD_KEY[f]) })}>
          <span className="max-w-[260px] truncate">{t(FIELD_KEY[f])}: {values(f)}</span>
        </Chip>
      ))}
      <Button size="xs" variant="ghost" onClick={() => onChange({ ...filters, faculty: [], program: [], year: [], instructor: [], building: [], room: [], day: [], time: null, mode: [], status: [], placement: [], issue: null, changed: null, locked: null })}>{t("classes.clear")}</Button>
    </div>
  );
}
