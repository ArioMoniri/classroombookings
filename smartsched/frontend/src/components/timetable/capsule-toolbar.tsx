"use client";
/**
 * Three floating chrome capsules (calendar.md §5.1): Navigate · Lens · Subject & actions. Segmented lens
 * switch with a neutral glass thumb (no saturated fill, A7/anti-AI #7). The issue capsule appears only when a
 * count is > 0 (no zero celebration). Undo/redo appear only when the stack is non-empty. Capsules condense
 * 44 → 36 px when the canvas scrolls (glassMorph layout morph; off under reduced motion).
 */
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, Ellipsis, PanelLeft, Redo2, Search, Undo2, Users } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { springs, useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { ScheduleRun } from "@/lib/api/schemas";
import { fold } from "./model/filters";
import type { Density } from "./model/geometry";
import type { CalendarModel } from "./model/index-model";
import { LENSES, type BoardMode, type Lens, type Subject } from "./model/view-state";

export interface SubjectOption {
  subject: Subject | null;
  label: string;
  sub: string;
  group: "all" | "room" | "instructor" | "cohort";
}

export function subjectOptions(model: CalendarModel, t: ReturnType<typeof useI18n>["t"]): SubjectOption[] {
  const out: SubjectOption[] = [{ subject: null, label: t("calendar.subject.all"), sub: "", group: "all" }];
  for (const r of model.rooms) out.push({ subject: { kind: "room", id: String(r.id) }, label: r.name, sub: t("calendar.subject.roomHeader", { room: "", cap: r.capacity }).replace(/^ · /, ""), group: "room" });
  const instr = new Map<number, { name: string; n: number }>();
  const cohorts = new Map<string, { name: string; year: number; n: number }>();
  const seen = new Set<number>();
  for (const e of model.events) {
    if (seen.has(e.a.id)) continue;
    seen.add(e.a.id);
    e.a.instr_ids.forEach((id, i) => {
      const x = instr.get(id) ?? { name: e.a.instr[i] ?? "?", n: 0 };
      x.n++;
      instr.set(id, x);
    });
    if (e.cohort && e.a.prog && e.a.year) {
      const x = cohorts.get(e.cohort) ?? { name: e.a.prog, year: e.a.year, n: 0 };
      x.n++;
      cohorts.set(e.cohort, x);
    }
  }
  for (const [id, x] of [...instr].sort((a, b) => a[1].name.localeCompare(b[1].name, "tr"))) out.push({ subject: { kind: "instructor", id: String(id) }, label: x.name, sub: t("calendar.subject.instructorHeader", { name: "", n: x.n }).replace(/^ · /, ""), group: "instructor" });
  for (const [id, x] of [...cohorts].sort((a, b) => a[1].name.localeCompare(b[1].name, "tr") || a[1].year - b[1].year)) out.push({ subject: { kind: "cohort", id }, label: t("calendar.subject.cohortLabel", { program: x.name, year: x.year }), sub: t("calendar.subject.cohortHeader", { name: "", n: x.n }).replace(/^ · /, ""), group: "cohort" });
  return out;
}

export function SubjectPicker({ model, subject, onSubject, condensed }: { model: CalendarModel; subject: Subject | null; onSubject: (s: Subject | null) => void; condensed?: boolean }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const options = useMemo(() => subjectOptions(model, t), [model, t]);
  const current = options.find((o) => (o.subject === null ? subject === null : subject && o.subject.kind === subject.kind && o.subject.id === subject.id));
  const filtered = useMemo(() => {
    const f = fold(q);
    return (f ? options.filter((o) => fold(`${o.label} ${o.sub}`).includes(f)) : options).slice(0, 80);
  }, [options, q]);
  const groups: { key: SubjectOption["group"]; label: string }[] = [
    { key: "all", label: "" },
    { key: "room", label: t("calendar.subject.room") },
    { key: "instructor", label: t("calendar.subject.instructor") },
    { key: "cohort", label: t("calendar.subject.cohort") },
  ];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant="ghost" size="sm" aria-label={t("calendar.subject.label")} data-testid="subject-picker" className="max-w-[180px]" />}>
        <Users aria-hidden />
        {!condensed ? <span className="truncate">{current?.label ?? t("calendar.subject.all")}</span> : null}
        <ChevronDown className="size-3 text-label-3" aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-1.5">
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("calendar.subject.search")} aria-label={t("calendar.subject.search")} className="mb-1 h-8 w-full rounded-lg bg-fill-2 px-2.5 text-[13px] outline-none focus-visible:outline-2 focus-visible:outline-(--focus)" />
        <div className="max-h-80 overflow-y-auto" role="listbox" aria-label={t("calendar.subject.label")}>
          {groups.map((g) => {
            const items = filtered.filter((o) => o.group === g.key);
            if (!items.length) return null;
            return (
              <div key={g.key} role="group" aria-label={g.label || t("calendar.subject.all")}>
                {g.label ? <p className="px-2 pt-2 pb-0.5 text-[11px] font-semibold text-label-3">{g.label}</p> : null}
                {items.map((o) => (
                  <button
                    key={`${o.group}:${o.subject?.id ?? "all"}`}
                    type="button"
                    role="option"
                    aria-selected={o === current}
                    onClick={() => {
                      onSubject(o.subject);
                      setOpen(false);
                      setQ("");
                    }}
                    className={cn("flex w-full items-baseline justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-fill-2", o === current && "bg-tint-soft")}
                  >
                    <span className="truncate font-medium">{o.label}</span>
                    <span className="shrink-0 text-[11px] text-label-2 tabular-nums">{o.sub}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export interface CapsuleToolbarProps {
  model: CalendarModel;
  lens: Lens;
  onLens: (l: Lens) => void;
  board: BoardMode;
  onBoard: (b: BoardMode) => void;
  weekLabel: string;
  weeks: { index: number; start_date: string | null; label: string | null }[];
  week: number;
  onWeek: (w: number) => void;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onToggleSidebar: () => void;
  subject: Subject | null;
  onSubject: (s: Subject | null) => void;
  conflicts: number;
  warnings: number;
  onIssues: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  density: Density;
  onDensity: (d: Density) => void;
  runs: ScheduleRun[];
  compare: number | null;
  onCompare: (id: number | null) => void;
  onExport: () => void;
  onShortcuts: () => void;
  onSearch: () => void;
  condensed: boolean;
  readOnly: boolean;
}

export function CapsuleToolbar(p: CapsuleToolbarProps) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const condensed = p.condensed && !reduce;
  const h = condensed ? "h-9" : "h-11";
  const capsule = cn("glass-chrome pointer-events-auto flex items-center gap-0.5 rounded-full px-1", h);
  return (
    <div className="pointer-events-none flex w-full flex-wrap items-center justify-between gap-2" role="toolbar" aria-label={t("calendar.lens.label")}>
      <motion.div layout={!reduce} transition={springs.glassMorph} className={capsule} data-glass="chrome">
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.toggleSidebar")} onClick={p.onToggleSidebar}><PanelLeft /></Button>
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.prev")} onClick={p.onPrev} data-testid="week-prev"><ChevronLeft /></Button>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="sm" className="min-w-[72px] font-semibold tabular-nums" aria-label={t("calendar.nav.pickWeek")} data-testid="week-label" />}>{p.weekLabel}</DropdownMenuTrigger>
          <DropdownMenuContent className="max-h-80 overflow-y-auto">
            <DropdownMenuRadioGroup value={String(p.week)} onValueChange={(v) => p.onWeek(Number(v))}>
              {p.weeks.map((w) => (
                <DropdownMenuRadioItem key={w.index} value={String(w.index)}>
                  {t("calendar.nav.weekShort", { n: w.index })} · {w.start_date ? formatDate(w.start_date, locale) : (w.label ?? "")}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.next")} onClick={p.onNext} data-testid="week-next"><ChevronRight /></Button>
        {!condensed ? <Button variant="ghost" size="sm" onClick={p.onToday}>{t("calendar.nav.today")}</Button> : null}
      </motion.div>

      <motion.div layout={!reduce} transition={springs.glassMorph} className={cn(capsule, "px-1.5")} data-glass="chrome">
        <SegmentedGlass size={condensed ? "sm" : "md"} aria-label={t("calendar.lens.label")} options={LENSES.map((l) => ({ value: l, label: t(`calendar.lens.${l}`) }))} value={p.lens} onValueChange={p.onLens} />
        {p.lens === "board" ? (
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-xs" aria-label={t("calendar.board.mode")} />}><ChevronDown /></DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuRadioGroup value={p.board} onValueChange={(v) => p.onBoard(v as BoardMode)}>
                <DropdownMenuRadioItem value="day">{t("calendar.board.day")}</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="strip">{t("calendar.board.strip")}</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </motion.div>

      <motion.div layout={!reduce} transition={springs.glassMorph} className={capsule} data-glass="chrome">
        <SubjectPicker model={p.model} subject={p.subject} onSubject={p.onSubject} condensed={condensed} />
        <Button variant="ghost" size="icon-sm" aria-label={t("calendar.sidebar.search")} onClick={p.onSearch}><Search /></Button>
        {p.conflicts > 0 || p.warnings > 0 ? (
          <Button variant="ghost" size="sm" onClick={p.onIssues} data-testid="issues-capsule" className="text-status-infeasible-fg">
            <AlertTriangle aria-hidden />
            {p.conflicts > 0 ? t("calendar.issues.conflicts", { n: p.conflicts }) : null}
            {p.conflicts > 0 && p.warnings > 0 ? <span aria-hidden className="text-label-3">·</span> : null}
            {p.warnings > 0 ? <span className="text-status-warning-fg">{t("calendar.issues.warnings", { n: p.warnings })}</span> : null}
          </Button>
        ) : null}
        {p.canUndo ? <Button variant="ghost" size="icon-sm" aria-label={t("calendar.toast.undo")} onClick={p.onUndo}><Undo2 /></Button> : null}
        {p.canRedo ? <Button variant="ghost" size="icon-sm" aria-label={t("calendar.toast.redo")} onClick={p.onRedo}><Redo2 /></Button> : null}
        {p.readOnly ? <span className="px-2 text-[12px] text-label-2">{t("calendar.readOnly")}</span> : null}
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("calendar.more")} />}><Ellipsis /></DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuGroup>
              <DropdownMenuLabel>{t("calendar.compare.pick")}</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={p.compare === null ? "" : String(p.compare)} onValueChange={(v) => p.onCompare(v ? Number(v) : null)}>
                <DropdownMenuRadioItem value="">{t("calendar.sidebar.compareNone")}</DropdownMenuRadioItem>
                {p.runs.filter((r) => r.id !== p.model.index.run.id).slice(0, 8).map((r) => (
                  <DropdownMenuRadioItem key={r.id} value={String(r.id)}>Run #{r.id} · {r.kind === "EXAM" ? t("classes.kind.exams") : t("classes.kind.meetings")}</DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuLabel>{t("calendar.density.label")}</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={p.density} onValueChange={(v) => p.onDensity(v as Density)}>
                {(["compact", "standard", "comfortable"] as const).map((d) => (
                  <DropdownMenuRadioItem key={d} value={d}>{t(`calendar.density.${d}`)}</DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={p.onExport}>{t("calendar.export")}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => window.print()}>{t("calendar.print")}</DropdownMenuItem>
            <DropdownMenuItem onClick={p.onShortcuts}>{t("calendar.shortcuts")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </motion.div>
    </div>
  );
}
