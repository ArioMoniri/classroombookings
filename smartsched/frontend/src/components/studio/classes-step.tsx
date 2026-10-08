"use client";

import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, Search, SlidersHorizontal, X } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { ClassRow, MeetingPatch, Pin } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { ChangedMark, DayTimeCell, ModeCell, PinCell, RoomsCell, StudentsCell } from "./class-cells";
import { EMPTY_FILTERS, QUICK_FILTERS, activeFilterCount, filterClasses, filterOptions, quickCounts, type ClassFilters, type QuickFilter } from "./class-filters";
import { ConfirmDialog } from "./confirm-dialog";
import { plainRuleText } from "./rule-helpers";
import { useStudio } from "./studio-context";
import { useClassEdit } from "./use-class-edit";

const QUICK_KEY: Record<QuickFilter, MessageKey> = {
  needsRoom: "studio.classes.quick.needsRoom",
  changed: "studio.classes.quick.changed",
  pinned: "studio.classes.quick.pinned",
  leftOut: "studio.classes.quick.leftOut",
  needsReview: "studio.classes.quick.needsReview",
  evening: "studio.classes.quick.evening",
  noDayTime: "studio.classes.quick.noDayTime",
};
const STATUS_KIND = { NEW: "preoccupied", PARSED: "feasible", NEEDS_REVIEW: "warning", LOCKED: "locked" } as const;
const ROW_H = 44;

function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

export function ClassesStep({ onMakeRule }: { onMakeRule: (eventIds: number[]) => void }) {
  const { t, n, locale } = useI18n();
  const params = useSearchParams();
  const { classes, classesLoading, classesError, rowState, dispatch, store, local, rooms, sentence, rules, meta, refresh, kind } = useStudio();
  const edits = useClassEdit();
  const reduce = useReducedMotion();
  const narrow = useIsNarrow();
  const ruleParam = params.get("rule");
  const [filters, setFilters] = useState<ClassFilters>(() => ({ ...EMPTY_FILTERS, ruleId: ruleParam ? Number(ruleParam) : null }));
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [changesOpen, setChangesOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [confirmRevertAll, setConfirmRevertAll] = useState(false);
  const [pinOpen, setPinOpen] = useState<number | null>(null);
  const [setStudents, setSetStudents] = useState("");
  const lastClicked = useRef<number | null>(null);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ruleParam) setFilters((f) => ({ ...f, ruleId: Number(ruleParam) }));
  }, [ruleParam]);

  const rows = useMemo(() => classes ?? [], [classes]);
  const opts = useMemo(() => filterOptions(rows), [rows]);
  const shown = useMemo(() => filterClasses(rows, filters, rowState), [rows, filters, rowState]);
  const counts = useMemo(() => quickCounts(rows, rowState), [rows, rowState]);
  const active = activeFilterCount(filters);
  const pinByEvent = useMemo(() => new Map(local.pins.map((p) => [p.event_id, p])), [local.pins]);
  const changedRows = rows.filter((r) => r.changed_fields.length > 0);
  const inPlan = rows.filter((r) => r.schedulable && !rowState.excluded.has(r.id)).length;
  const ruleFilter = filters.ruleId !== null ? rules?.rules.find((r) => r.id === filters.ruleId) : undefined;

  const set = (patch: Partial<ClassFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const exclude = (ids: number[], label: string) => {
    const was = ids.filter((i) => !rowState.excluded.has(i));
    if (!was.length) return;
    dispatch({ type: "exclude", ids: was });
    store.getState().record({ label, undo: () => dispatch({ type: "include", ids: was }), redo: () => dispatch({ type: "exclude", ids: was }) });
  };
  const include = (ids: number[], label: string) => {
    const was = ids.filter((i) => rowState.excluded.has(i));
    if (!was.length) return;
    dispatch({ type: "include", ids: was });
    store.getState().record({ label, undo: () => dispatch({ type: "exclude", ids: was }), redo: () => dispatch({ type: "include", ids: was }) });
  };
  const toggleIn = (r: ClassRow) => (rowState.excluded.has(r.id) ? include([r.id], t("studio.history.putBack")) : exclude([r.id], t("studio.history.leftOut")));
  const onlyThese = () => {
    const keep = new Set(shown.map((r) => r.id));
    const before = local.excluded;
    const next = rows.filter((r) => !keep.has(r.id)).map((r) => r.id);
    dispatch({ type: "setExcluded", ids: next });
    store.getState().record({ label: t("studio.history.onlyThese"), undo: () => dispatch({ type: "setExcluded", ids: before }), redo: () => dispatch({ type: "setExcluded", ids: next }) });
  };
  const pin = (p: Pin) => {
    const prev = pinByEvent.get(p.event_id);
    dispatch({ type: "setPin", pin: p });
    store.getState().record({ label: t("studio.history.pinned"), undo: () => (prev ? dispatch({ type: "setPin", pin: prev }) : dispatch({ type: "unpin", eventId: p.event_id })), redo: () => dispatch({ type: "setPin", pin: p }) });
    setPinOpen(null);
  };
  const unpin = (id: number) => {
    const prev = pinByEvent.get(id);
    if (!prev) return;
    dispatch({ type: "unpin", eventId: id });
    store.getState().record({ label: t("studio.pin.removed"), undo: () => dispatch({ type: "setPin", pin: prev }), redo: () => dispatch({ type: "unpin", eventId: id }) });
    setPinOpen(null);
  };
  const save = (r: ClassRow, patch: MeetingPatch) => void edits.edit([r], patch);

  const toggleSelect = (id: number, shift: boolean) => {
    setSelected((s) => {
      const next = new Set(s);
      if (shift && lastClicked.current !== null) {
        const a = shown.findIndex((r) => r.id === lastClicked.current);
        const b = shown.findIndex((r) => r.id === id);
        if (a >= 0 && b >= 0) for (const r of shown.slice(Math.min(a, b), Math.max(a, b) + 1)) next.add(r.id);
      } else if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    lastClicked.current = id;
  };

  const columns = useMemo<ColumnDef<ClassRow>[]>(
    () => [
      {
        id: "select",
        header: () => <Checkbox checked={shown.length > 0 && selected.size === shown.length} indeterminate={selected.size > 0 && selected.size < shown.length} onCheckedChange={(v) => setSelected(v ? new Set(shown.map((r) => r.id)) : new Set())} aria-label={t("studio.classes.selectAll")} />,
        cell: ({ row }) => <Checkbox checked={selected.has(row.original.id)} onClick={(e) => { e.preventDefault(); toggleSelect(row.original.id, e.shiftKey); }} aria-label={t("studio.classes.selectRow", { name: `${row.original.course_code} §${row.original.section_label ?? ""}` })} />,
        size: 36,
      },
      {
        id: "inPlan",
        header: () => t("studio.classes.inPlan"),
        cell: ({ row }) => {
          const r = row.original;
          const on = !rowState.excluded.has(r.id);
          return <Switch checked={on} onCheckedChange={() => toggleIn(r)} aria-label={t("studio.classes.inPlanLabel", { name: `${r.course_code} §${r.section_label ?? ""}` })} data-testid="in-plan" />;
        },
        size: 64,
      },
      {
        id: "course",
        header: () => t("studio.classes.col.course"),
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-xs font-semibold">{(r.course_code ?? "").toLocaleUpperCase(locale === "tr" ? "tr-TR" : "en-US")}</span>
                {r.section_label ? <span className="text-xs text-label-2">§{r.section_label}</span> : null}
                {rowState.excluded.has(r.id) ? <span className="rounded border px-1 text-[10px] text-label-2">{t("studio.classes.leftOutChip")}</span> : null}
              </div>
              <div className="truncate text-xs text-label-2" title={r.course_name ?? ""}>
                {r.course_name}
              </div>
            </div>
          );
        },
        size: 220,
      },
      {
        id: "program",
        header: () => t("studio.classes.col.program"),
        cell: ({ row }) => (
          <div className="min-w-0 text-xs">
            <div className="truncate" title={`${row.original.faculty_name ?? ""} › ${row.original.program_name ?? ""}`}>
              {row.original.program_name}
              {row.original.is_evening ? <span className="ml-1 rounded bg-fill-2 px-1 text-[10px]">İÖ</span> : null}
            </div>
            <div className="truncate text-label-2">{row.original.faculty_name}</div>
          </div>
        ),
        size: 200,
      },
      { id: "year", header: () => t("studio.classes.col.year"), cell: ({ row }) => <span className="tabular-nums">{row.original.class_year ?? "—"}</span>, size: 56 },
      {
        id: "dayTime",
        header: () => t("studio.classes.col.dayTime"),
        cell: ({ row }) => (
          <ChangedMark row={row.original} group="dayTime" onRevert={(f) => void edits.revert(row.original, f)}>
            <DayTimeCell row={row.original} onSave={(p) => save(row.original, p)} />
          </ChangedMark>
        ),
        size: 220,
      },
      {
        id: "weeks",
        header: () => t("studio.classes.col.weeks"),
        cell: ({ row }) => {
          const w = row.original.weeks;
          return <span className="tabular-nums text-xs">{w.length ? (w.every((x, i) => i === 0 || x === w[i - 1] + 1) ? `${w[0]}–${w[w.length - 1]}` : w.join(",")) : "—"}</span>;
        },
        size: 72,
      },
      {
        id: "students",
        header: () => t("studio.classes.col.students"),
        cell: ({ row }) => (
          <ChangedMark row={row.original} group="students" onRevert={(f) => void edits.revert(row.original, f)}>
            <StudentsCell row={row.original} onSave={(p) => save(row.original, p)} warning={edits.warnings[row.original.id]?.[0]} />
          </ChangedMark>
        ),
        size: 96,
      },
      {
        id: "mode",
        header: () => t("studio.classes.col.mode"),
        cell: ({ row }) => (
          <ChangedMark row={row.original} group="mode" onRevert={(f) => void edits.revert(row.original, f)}>
            <ModeCell row={row.original} onSave={(p) => save(row.original, p)} />
          </ChangedMark>
        ),
        size: 160,
      },
      {
        id: "rooms",
        header: () => t("studio.classes.col.rooms"),
        cell: ({ row }) => (
          <ChangedMark row={row.original} group="rooms" onRevert={(f) => void edits.revert(row.original, f)}>
            <RoomsCell row={row.original} onSave={(p) => save(row.original, p)} />
          </ChangedMark>
        ),
        size: 180,
      },
      {
        id: "pin",
        header: () => t("studio.classes.col.pin"),
        cell: ({ row }) => <PinCell row={row.original} pin={pinByEvent.get(row.original.id)} roomCode={sentence.roomCode} rooms={rooms} onPin={pin} onUnpin={() => unpin(row.original.id)} open={pinOpen === row.original.id ? true : undefined} onOpenChange={(o) => setPinOpen(o ? row.original.id : null)} />,
        size: 110,
      },
      {
        id: "status",
        header: () => t("studio.classes.col.status"),
        cell: ({ row }) => {
          const s = row.original.status as keyof typeof STATUS_KIND;
          return STATUS_KIND[s] ? <StatusBadge kind={STATUS_KIND[s]} label={t(`requests.status.${s}`)} /> : <span className="text-xs">{row.original.status}</span>;
        },
        size: 130,
      },
      {
        id: "changed",
        header: () => <span className="sr-only">{t("studio.classes.col.changed")}</span>,
        cell: ({ row }) => (row.original.changed_fields.length ? <span className="inline-block size-2 rounded-full bg-status-warning-fg" title={t("studio.classes.col.changed")} aria-label={t("studio.classes.col.changed")} role="img" /> : null),
        size: 28,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shown, selected, rowState, edits.warnings, pinByEvent, pinOpen, rooms, sentence, t, locale],
  );

  const table = useReactTable({ data: shown, columns, getCoreRowModel: getCoreRowModel(), getRowId: (r) => String(r.id) });
  const scroller = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: shown.length, getScrollElement: () => scroller.current, estimateSize: () => (narrow ? 132 : ROW_H), overscan: 12 });
  const vItems = virt.getVirtualItems();
  const tableRows = table.getRowModel().rows;
  const padTop = vItems[0]?.start ?? 0;
  const padBottom = vItems.length ? virt.getTotalSize() - (vItems[vItems.length - 1]?.end ?? 0) : 0;

  const onRowKey = (e: KeyboardEvent<HTMLElement>, r: ClassRow, index: number) => {
    if (e.target !== e.currentTarget) return;
    const focusRow = (i: number) => {
      virt.scrollToIndex(i);
      window.requestAnimationFrame(() => scroller.current?.querySelector<HTMLElement>(`[data-row-index="${i}"]`)?.focus());
    };
    switch (e.key) {
      case "j":
      case "ArrowDown":
        e.preventDefault();
        focusRow(Math.min(shown.length - 1, index + 1));
        break;
      case "k":
      case "ArrowUp":
        e.preventDefault();
        focusRow(Math.max(0, index - 1));
        break;
      case "x":
        toggleSelect(r.id, e.shiftKey);
        break;
      case "i":
        toggleIn(r);
        break;
      case "p":
        setPinOpen(r.id);
        break;
      case "e":
        e.currentTarget.querySelector<HTMLElement>("[data-edit='students']")?.click();
        break;
      case "Escape":
        setSelected(new Set());
        break;
    }
  };

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (e.key === "/") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sel = rows.filter((r) => selected.has(r.id));

  const filterControls = (
    <>
        <NativeSelect className="w-40" aria-label={t("studio.classes.faculty")} value={filters.faculty ?? ""} onChange={(e) => set({ faculty: e.target.value ? Number(e.target.value) : null, program: null })} data-testid="filter-faculty">
        <option value="">{t("studio.classes.faculty")}</option>
        {opts.faculties.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect className="w-44" aria-label={t("studio.classes.program")} value={filters.program ?? ""} onChange={(e) => set({ program: e.target.value ? Number(e.target.value) : null })} data-testid="filter-program">
        <option value="">{t("studio.classes.program")}</option>
        {opts.programs.filter((p) => filters.faculty === null || p.faculty === filters.faculty).map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect className="w-28" aria-label={t("studio.classes.year")} value={filters.year ?? ""} onChange={(e) => set({ year: e.target.value ? Number(e.target.value) : null })}>
        <option value="">{t("studio.classes.year")}</option>
        {opts.years.map((y) => (
          <option key={y} value={y}>
            {t("studio.classes.yearN", { n: y })}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect className="w-32" aria-label={t("common.day")} value={filters.day ?? ""} onChange={(e) => set({ day: e.target.value ? Number(e.target.value) : null })} data-testid="filter-day">
        <option value="">{t("common.day")}</option>
        {[1, 2, 3, 4, 5, 6, 7].map((d) => (
          <option key={d} value={d}>
            {dayName(d, locale)}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect className="w-28" aria-label={t("common.building")} value={filters.building ?? ""} onChange={(e) => set({ building: e.target.value || null })}>
        <option value="">{t("common.building")}</option>
        {opts.buildings.map((b) => (
          <option key={b} value={b}>
            {t("studio.slot.block", { b })}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect className="w-36" aria-label={t("studio.classes.col.mode")} value={filters.mode ?? ""} onChange={(e) => set({ mode: e.target.value || null })}>
        <option value="">{t("studio.classes.col.mode")}</option>
        {opts.modes.map((m) => (
          <option key={m} value={m}>
            {t(`studio.mode.${m as "F2F"}`)}
          </option>
        ))}
      </NativeSelect>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={filters.changed} onChange={(e) => set({ changed: e.target.checked })} data-testid="filter-changed" /> {t("studio.classes.changedOnly")}
      </label>
    </>
  );

  if (classesError)
    return (
      <div role="alert" className="flex items-center gap-2 rounded-md border border-status-infeasible-border bg-status-infeasible p-3 text-sm text-status-infeasible-fg">
        <AlertTriangle className="size-4" aria-hidden /> {t("studio.classes.loadError")}
        <Button size="sm" variant="outline" onClick={() => void refresh(["classes"])}>
          {t("common.retry")}
        </Button>
      </div>
    );

  return (
    <div className="space-y-3" data-testid="classes-step">
      <p className="text-sm text-label-2">{t("studio.classes.helper")}</p>

      <div className="flex flex-wrap items-center gap-2" role="search">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-label-2" aria-hidden />
          <Input ref={search} value={filters.q} onChange={(e) => set({ q: e.target.value })} placeholder={t("studio.classes.search")} aria-label={t("studio.classes.search")} aria-keyshortcuts="/" className="pl-7" data-testid="class-search" />
        </div>
        {narrow ? (
          <Button variant="outline" size="sm" onClick={() => setFiltersOpen(true)} className="pointer-coarse:min-h-11" data-testid="open-filters">
            <SlidersHorizontal aria-hidden /> {t("common.filter")}
            {active ? ` (${active})` : ""}
          </Button>
        ) : (
          filterControls
        )}
        {active ? (
          <Button variant="ghost" size="sm" onClick={() => setFilters(EMPTY_FILTERS)}>
            <X aria-hidden /> {t("studio.classes.clear")}
          </Button>
        ) : null}
      </div>

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="group" aria-label={t("studio.classes.quickTitle")}>
        {QUICK_FILTERS.map((q) => (
          <button key={q} type="button" aria-pressed={filters.quick === q} onClick={() => set({ quick: filters.quick === q ? null : q })} className={cn("shrink-0 rounded-full border px-2.5 py-1 text-xs pointer-coarse:min-h-11", filters.quick === q ? "border-primary bg-tint-soft font-medium text-tint-text" : "hover:bg-fill-2")} data-testid={`quick-${q}`}>
            {t(QUICK_KEY[q])} <span className="tabular-nums text-label-2">{n(counts[q])}</span>
          </button>
        ))}
      </div>

      {ruleFilter ? (
        <div className="flex items-center gap-2 rounded-md bg-tint-soft px-2.5 py-1.5 text-sm">
          <span className="min-w-0 flex-1 truncate">{t("studio.classes.byRule", { rule: plainRuleText(meta, ruleFilter.kind, ruleFilter.params, ruleFilter.nl_text, sentence) })}</span>
          <Button size="icon-xs" variant="ghost" aria-label={t("studio.classes.clear")} onClick={() => set({ ruleId: null })}>
            <X aria-hidden />
          </Button>
        </div>
      ) : null}

      {active > 0 && shown.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-fill-3 px-2.5 py-1.5 text-sm" data-testid="only-these-bar">
          <span>{t("studio.classes.matchBar", { n: n(shown.length) })}</span>
          <Button size="sm" variant="outline" onClick={onlyThese} data-testid="only-these">
            {t("studio.classes.onlyThese", { n: n(shown.length) })}
          </Button>
          <span className="text-xs text-label-2">{t("studio.classes.onlyTheseHint", { n: n(Math.max(0, rows.length - shown.length)) })}</span>
          <Button size="sm" variant="ghost" onClick={() => exclude(shown.map((r) => r.id), t("studio.history.leftOut"))}>
            {t("studio.classes.leaveTheseOut")}
          </Button>
        </div>
      ) : null}

      {classesLoading ? (
        <div className="space-y-1" aria-busy="true" aria-label={t("common.loading")}>
          {Array.from({ length: 12 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] p-6 text-center text-sm">
          <p>{t("studio.scope.nothingToPlan")}</p>
          <Button className="mt-3" render={<Link href={kind === "EXAM" ? "/import?source=exam" : "/import?source=planning"} />}>
            {t("studio.scope.importCta")}
          </Button>
        </div>
      ) : shown.length === 0 ? (
        <div className="rounded-2xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] p-6 text-center text-sm text-label-2" data-testid="classes-empty">
          {t("studio.classes.empty")}{" "}
          <button type="button" className="font-medium text-tint-text underline" onClick={() => setFilters(EMPTY_FILTERS)}>
            {t("studio.classes.clear")}
          </button>
        </div>
      ) : narrow ? (
        <div ref={scroller} className="relative h-[60dvh] overflow-y-auto overscroll-contain rounded-lg border" data-testid="class-cards">
          <ul style={{ height: virt.getTotalSize(), position: "relative" }} aria-label={t("studio.step.classes")}>
            {vItems.map((v) => {
              const r = shown[v.index];
              const out = rowState.excluded.has(r.id);
              return (
                <li key={r.id} data-index={v.index} ref={virt.measureElement} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${v.start}px)` }} className={cn("border-b p-3", out && "opacity-60")} data-testid="class-row" data-class-id={r.id}>
                  <div className="flex items-start gap-3">
                    <Checkbox checked={selected.has(r.id)} onClick={(e) => { e.preventDefault(); toggleSelect(r.id, false); }} aria-label={t("studio.classes.selectRow", { name: `${r.course_code} §${r.section_label ?? ""}` })} className="mt-1" />
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-mono text-xs font-semibold">
                        {r.course_code} <span className="text-label-2">§{r.section_label}</span> {out ? <span className="ml-1 rounded border px-1 font-sans text-[10px] font-normal text-label-2">{t("studio.classes.leftOutChip")}</span> : null}
                      </p>
                      <p className="truncate text-xs">{r.course_name}</p>
                      <p className="truncate text-xs text-label-2">{r.program_name}</p>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        <DayTimeCell row={r} onSave={(p) => save(r, p)} />
                        <span>· {t("studio.classes.studentsN", { n: r.enrolment ?? "—" })}</span>
                        <PinCell row={r} pin={pinByEvent.get(r.id)} roomCode={sentence.roomCode} rooms={rooms} onPin={pin} onUnpin={() => unpin(r.id)} />
                      </p>
                    </div>
                    <Switch checked={!out} onCheckedChange={() => toggleIn(r)} aria-label={t("studio.classes.inPlanLabel", { name: `${r.course_code} §${r.section_label ?? ""}` })} data-testid="in-plan" className="mt-1" />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <div ref={scroller} className="relative max-h-[62dvh] overflow-auto overscroll-contain rounded-lg border" data-testid="class-table">
          <table role="grid" aria-rowcount={shown.length} className="w-full min-w-[1100px] border-separate border-spacing-0 text-sm" style={{ tableLayout: "fixed" }}>
            <colgroup>
              {table.getAllLeafColumns().map((c) => (
                <col key={c.id} style={{ width: c.getSize() }} />
              ))}
            </colgroup>
            <thead className="sticky top-0 z-[2] bg-background">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h, i) => (
                    <th key={h.id} scope="col" className={cn("border-b bg-background px-2 py-2 text-left text-xs font-medium whitespace-nowrap text-label-2", i < 3 && "xl:sticky xl:z-[3]", i === 0 && "xl:left-0", i === 1 && "xl:left-9", i === 2 && "xl:left-[100px]")}>
                      {flexRender(h.column.columnDef.header, h.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {padTop > 0 ? (
                <tr aria-hidden>
                  <td style={{ height: padTop }} colSpan={columns.length} />
                </tr>
              ) : null}
              {vItems.map((v) => {
                const row = tableRows[v.index];
                if (!row) return null;
                const r = row.original;
                const out = rowState.excluded.has(r.id);
                return (
                  <tr
                    key={row.id}
                    data-index={v.index}
                    data-row-index={v.index}
                    ref={virt.measureElement}
                    tabIndex={v.index === 0 ? 0 : -1}
                    aria-rowindex={v.index + 1}
                    aria-selected={selected.has(r.id)}
                    onKeyDown={(e) => onRowKey(e, r, v.index)}
                    className={cn("group/row outline-none focus-visible:bg-tint-soft", out && "opacity-60", selected.has(r.id) && "bg-tint-soft/60")}
                    data-testid="class-row"
                    data-class-id={r.id}
                    data-included={!out}
                  >
                    {row.getVisibleCells().map((cell, i) => (
                      <td key={cell.id} className={cn("h-11 border-b px-2 py-1 align-middle", i < 3 && "xl:sticky xl:z-[1] xl:bg-background", i === 0 && "xl:left-0", i === 1 && "xl:left-9", i === 2 && "xl:left-[100px]")}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {padBottom > 0 ? (
                <tr aria-hidden>
                  <td style={{ height: padBottom }} colSpan={columns.length} />
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-label-2" data-testid="classes-footer">
        <span>{t("studio.classes.footer", { in: n(inPlan), out: n(rowState.excluded.size), pinned: n(local.pins.length) })}</span>
        {changedRows.length ? (
          <>
            <span aria-hidden>·</span>
            <strong className="text-foreground">{t("studio.classes.changed", { n: n(changedRows.length) })}</strong>
            <Button size="xs" variant="outline" onClick={() => setChangesOpen(true)} data-testid="review-changes">
              {t("studio.classes.reviewChanges")}
            </Button>
          </>
        ) : null}
      </div>

      {selected.size > 0 ? (
        <motion.div initial={reduce ? false : { y: 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.18 }} className="sticky bottom-20 z-20 flex flex-wrap items-center gap-2 rounded-xl border bg-popover p-2 text-sm shadow-[var(--shadow-2)] xl:bottom-3" role="toolbar" aria-label={t("studio.classes.bulk")} data-testid="bulk-bar">
          <span className="px-1 font-medium">{t("studio.classes.selected", { n: n(selected.size) })}</span>
          <Button size="sm" variant="outline" onClick={() => exclude([...selected], t("studio.history.leftOut"))} data-testid="bulk-leave-out">
            {t("studio.classes.leaveOut")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => include([...selected], t("studio.history.putBack"))}>
            {t("studio.classes.putBack")}
          </Button>
          <Popover>
            <PopoverTrigger render={<Button size="sm" variant="outline" />}>{t("studio.classes.setStudents")}</PopoverTrigger>
            <PopoverContent className="w-56">
              <label className="grid gap-1 text-sm">
                <span>{t("studio.classes.col.students")}</span>
                <Input type="number" min={0} value={setStudents} onChange={(e) => setSetStudents(e.target.value)} />
              </label>
              <Button size="sm" disabled={!setStudents} onClick={() => void edits.edit(sel, { enrolment: Number(setStudents) }, t("studio.classes.setStudents"))}>
                {t("common.apply")}
              </Button>
            </PopoverContent>
          </Popover>
          <Button size="sm" variant="outline" onClick={() => onMakeRule([...selected])} data-testid="bulk-make-rule">
            {t("studio.classes.makeRule")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            {t("studio.classes.clearSelection")}
          </Button>
        </motion.div>
      ) : null}

      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-sm" data-testid="filters-sheet">
          <SheetHeader>
            <SheetTitle>{t("common.filter")}</SheetTitle>
          </SheetHeader>
          <div className="grid gap-3 px-4 pb-4 [&>span]:w-full">{filterControls}</div>
        </SheetContent>
      </Sheet>
      <Sheet open={changesOpen} onOpenChange={setChangesOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl" data-testid="changes-sheet">
          <SheetHeader>
            <SheetTitle>{t("studio.classes.reviewChanges")}</SheetTitle>
            <SheetDescription>{t("studio.classes.changesHelp")}</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-label-2">
                  <th className="py-1 font-medium">{t("studio.classes.col.course")}</th>
                  <th className="py-1 font-medium">{t("studio.classes.field")}</th>
                  <th className="py-1 font-medium">{t("studio.classes.imported")}</th>
                  <th className="py-1 font-medium">{t("studio.classes.current")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {changedRows.flatMap((r) =>
                  r.changed_fields.map((c) => (
                    <tr key={`${r.id}-${c.field}`} className="border-t align-top">
                      <td className="py-1.5 font-mono text-xs">
                        {r.course_code} §{r.section_label}
                      </td>
                      <td className="py-1.5 text-xs">{c.field}</td>
                      <td className="py-1.5 text-xs text-label-2 line-through">{fmt(c.imported)}</td>
                      <td className="py-1.5 text-xs">{fmt(c.current)}</td>
                      <td className="py-1.5 text-right">
                        <Button size="xs" variant="outline" onClick={() => void edits.revert(r, [c.field])}>
                          {t("studio.classes.revert")}
                        </Button>
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
            {changedRows.length ? (
              <Button className="mt-3" variant="destructive" size="sm" onClick={() => setConfirmRevertAll(true)}>
                {t("studio.classes.revertAll")}
              </Button>
            ) : (
              <p className="text-sm text-label-2">{t("studio.classes.noChanges")}</p>
            )}
          </div>
        </SheetContent>
      </Sheet>
      <ConfirmDialog open={confirmRevertAll} onOpenChange={setConfirmRevertAll} title={t("studio.classes.revertAll")} description={t("studio.classes.revertAllConfirm", { n: changedRows.length })} confirmLabel={t("studio.classes.revertAll")} destructive onConfirm={() => void edits.revertAll(changedRows)} />
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}
