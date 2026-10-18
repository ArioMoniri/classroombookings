"use client";
/**
 * One chrome toolbar (calendar.md §5.1, design-system overhaul 2026-10-15): Navigate · Lens · Subject & actions
 * as groups of one capsule, never wrapping. Segmented lens
 * switch with a neutral glass thumb (no saturated fill, A7/anti-AI #7). The issue capsule appears only when a
 * count is > 0 (no zero celebration). Undo/redo appear only when the stack is non-empty. Capsules condense
 * 44 → 36 px when the canvas scrolls (glassMorph layout morph; off under reduced motion).
 */
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, Ellipsis, PanelLeft, Redo2, Search, Undo2, Users } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { springs, useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { ScheduleRun } from "@/lib/api/schemas";
import { fold } from "./model/filters";
import type { Density } from "./model/geometry";
import type { CalendarModel } from "./model/index-model";
import { LENSES, type BoardMode, type Lens, type Subject } from "./model/view-state";
import { BareButton } from "@/components/shell/bare-button";
import { Input } from "@/components/ui/input";

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

export function SubjectPicker({ model, subject, onSubject, condensed, size = "sm" }: { model: CalendarModel; subject: Subject | null; onSubject: (s: Subject | null) => void; condensed?: boolean; size?: "sm" | "md" }) {
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
      <PopoverTrigger render={<Button variant="ghost" size={size} aria-label={t("calendar.subject.label")} data-testid="subject-picker" className="max-w-[180px]" />}>
        <Users aria-hidden />
        {!condensed ? <span className="truncate">{current?.label ?? t("calendar.subject.all")}</span> : null}
        <ChevronDown className="text-label-3" aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-1.5">
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("calendar.subject.search")} aria-label={t("calendar.subject.search")} className="mb-1" />
        <div className="max-h-80 overflow-y-auto" role="listbox" aria-label={t("calendar.subject.label")}>
          {groups.map((g) => {
            const items = filtered.filter((o) => o.group === g.key);
            if (!items.length) return null;
            return (
              <div key={g.key} role="group" aria-label={g.label || t("calendar.subject.all")}>
                {g.label ? <p className="px-2 pt-2 pb-0.5 type-caption font-semibold text-label-3">{g.label}</p> : null}
                {items.map((o) => (
                  <BareButton
                    key={`${o.group}:${o.subject?.id ?? "all"}`}
                    role="option"
                    aria-selected={o === current}
                    onClick={() => {
                      onSubject(o.subject);
                      setOpen(false);
                      setQ("");
                    }}
                    className={cn("flex w-full items-baseline justify-between gap-2 rounded-lg px-2 py-1.5 text-left type-callout hover:bg-fill-2", o === current && "bg-tint-soft")}
                  >
                    <span className="truncate font-medium">{o.label}</span>
                    <span className="shrink-0 type-caption text-label-2 tabular-nums">{o.sub}</span>
                  </BareButton>
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
  /** the filters sidebar is shown (aria-expanded on the toggle) */
  sidebarOpen?: boolean;
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
  /** "week": the visible week only; "term": every week of the run (admin persona M-32) */
  onExport: (scope: "week" | "term") => void;
  onShortcuts: () => void;
  onSearch: () => void;
  condensed: boolean;
  readOnly: boolean;
}

export function CapsuleToolbar(p: CapsuleToolbarProps) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const condensed = p.condensed && !reduce;
  // ONE toolbar (review 2026-10-15 §3 Timetable: three capsules wrapped into 2–3 rows): groups split by hairline
  // separators, nowrap; below 80rem of toolbar width (container query) Today and Search move into "⋯".
  const sep = <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-hairline" />;
  return (
    <div className="@container/tb w-full min-w-0">
      <motion.div
        layout={!reduce}
        transition={springs.glassMorph}
        role="toolbar"
        aria-label={t("calendar.lens.label")}
        data-glass="chrome"
        data-testid="calendar-toolbar"
        className={cn("glass-chrome flex w-full min-w-0 flex-nowrap items-center gap-0.5 rounded-full px-1", condensed ? "h-(--control-h-lg)" : "h-[calc(var(--control-h-lg)+4px)]")}
      >
        <div role="group" aria-label={t("calendar.nav.pickWeek")} className="flex shrink-0 items-center gap-0.5">
          <IconButton size="sm" label={t("calendar.nav.toggleSidebar")} onClick={p.onToggleSidebar} aria-expanded={p.sidebarOpen} data-testid="calendar-sidebar-toggle"><PanelLeft aria-hidden /></IconButton>
          <IconButton size="sm" label={t("calendar.nav.prev")} onClick={p.onPrev} data-testid="week-prev"><ChevronLeft aria-hidden /></IconButton>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="sm" className="min-w-[72px] font-semibold tnum" aria-label={t("calendar.nav.pickWeek")} data-testid="week-label" />}>{p.weekLabel}</DropdownMenuTrigger>
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
          <IconButton size="sm" label={t("calendar.nav.next")} onClick={p.onNext} data-testid="week-next"><ChevronRight aria-hidden /></IconButton>
          <Button variant="ghost" size="sm" onClick={p.onToday} className="hidden @min-[80rem]/tb:inline-flex">{t("calendar.nav.today")}</Button>
        </div>
        {sep}
        <div className="flex shrink-0 items-center gap-0.5">
          <SegmentedControl size="sm" collapse={false} aria-label={t("calendar.lens.label")} options={LENSES.map((l) => ({ value: l, label: t(`calendar.lens.${l}`) }))} value={p.lens} onValueChange={p.onLens} />
          {p.lens === "board" ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<IconButton size="sm" label={t("calendar.board.mode")} />}><ChevronDown aria-hidden /></DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuRadioGroup value={p.board} onValueChange={(v) => p.onBoard(v as BoardMode)}>
                  <DropdownMenuRadioItem value="day">{t("calendar.board.day")}</DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="strip">{t("calendar.board.strip")}</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
        {sep}
        <div className="flex min-w-0 flex-1 items-center gap-0.5">
          <div className="flex min-w-24 flex-1 overflow-hidden p-0.5">
            <SubjectPicker model={p.model} subject={p.subject} onSubject={p.onSubject} condensed={condensed} />
          </div>
          <IconButton size="sm" label={t("calendar.sidebar.search")} onClick={p.onSearch} className="hidden @min-[80rem]/tb:inline-flex"><Search aria-hidden /></IconButton>
          {p.conflicts > 0 || p.warnings > 0 ? (
            <Button variant="ghost" size="sm" onClick={p.onIssues} data-testid="issues-capsule" className="shrink-0 text-status-infeasible-fg">
              <AlertTriangle aria-hidden />
              {/* full sentence from 72rem of toolbar width; below it the two counts only (the label keeps the words) */}
              <span className="hidden @min-[72rem]/tb:inline">
                {p.conflicts > 0 ? t("calendar.issues.conflictsWeek", { n: p.conflicts }) : null}
                {p.conflicts > 0 && p.warnings > 0 ? <span aria-hidden className="text-label-2"> · </span> : null}
                {p.warnings > 0 ? <span className="text-status-warning-fg">{t("calendar.issues.warningsWeek", { n: p.warnings })}</span> : null}
              </span>
              <span className="tnum @min-[72rem]/tb:hidden" aria-label={[p.conflicts > 0 ? t("calendar.issues.conflictsWeek", { n: p.conflicts }) : "", p.warnings > 0 ? t("calendar.issues.warningsWeek", { n: p.warnings }) : ""].filter(Boolean).join(", ")}>
                {/* HX12B-F08: never bare numbers ("13 · 135"): the short words stay */}
                {p.conflicts > 0 ? t("calendar.issues.conflicts", { n: p.conflicts }) : null}
                {p.conflicts > 0 && p.warnings > 0 ? <span aria-hidden className="text-label-2"> · </span> : null}
                {p.warnings > 0 ? <span className="text-status-warning-fg">{t("calendar.issues.warnings", { n: p.warnings })}</span> : null}
              </span>
            </Button>
          ) : null}
          {p.canUndo ? <IconButton size="sm" label={t("calendar.toast.undo")} onClick={p.onUndo}><Undo2 aria-hidden /></IconButton> : null}
          {p.canRedo ? <IconButton size="sm" label={t("calendar.toast.redo")} onClick={p.onRedo}><Redo2 aria-hidden /></IconButton> : null}
          {p.readOnly ? <span className="shrink-0 px-2 type-footnote text-label-2">{t("calendar.readOnly")}</span> : null}
          <DropdownMenu>
            <DropdownMenuTrigger render={<IconButton size="sm" label={t("calendar.more")} />}><Ellipsis aria-hidden /></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuGroup className="@min-[80rem]/tb:hidden">
                <DropdownMenuItem onClick={p.onToday}>{t("calendar.nav.today")}</DropdownMenuItem>
                <DropdownMenuItem onClick={p.onSearch}>{t("calendar.sidebar.search")}</DropdownMenuItem>
                <DropdownMenuSeparator />
              </DropdownMenuGroup>
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
              <DropdownMenuItem onClick={() => p.onExport("week")} data-testid="export-week">{t("calendar.exportWeek")}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => p.onExport("term")} data-testid="export-term">{t("calendar.exportTerm")}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => window.print()}>{t("calendar.print")}</DropdownMenuItem>
              <DropdownMenuItem onClick={p.onShortcuts}>{t("calendar.shortcuts")}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </motion.div>
    </div>
  );
}
