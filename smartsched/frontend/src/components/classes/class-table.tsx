"use client";
/**
 * ClassTable (all-classes.md §5, §8, §17–§19): TanStack Table v8 (MIT) for columns, sorting and grouping
 * (grouped row model; groups keep their natural order), @tanstack/react-virtual over the flattened
 * group/row list, sticky glass group headers with aggregates, one tab stop with a roving cell cursor,
 * inline edit (double-click / Enter / F2; Esc cancels; Enter saves and moves down; Tab saves and moves right).
 * Opaque rows (no glass on data, A8); hairline separators; no zebra; numbers right-aligned.
 */
import { getCoreRowModel, getGroupedRowModel, getSortedRowModel, useReactTable, type ColumnDef, type Row, type SortingState } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, ArrowDown, ArrowUp, ChevronRight, Circle, CircleDashed, Contrast, Lock, LockOpen, Minus, Moon } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import type { ClassRow } from "@/lib/api/classes";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { dayName, formatDate, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { aggregate, groupKey, type Density } from "./classes-model";

export const ROW_H: Record<Density, number> = { compact: 32, standard: 44, comfortable: 56 };
const HEADER_H = 36;
const EDITABLE = new Set(["students", "reqStatus", "notes"]);

export interface EditCommit {
  row: ClassRow;
  column: string;
  value: string;
}

export interface ClassTableProps {
  rows: ClassRow[];
  columns: string[];
  sort: SortingState;
  onSort: (s: SortingState) => void;
  group: string | null;
  subgroup: string | null;
  collapsed: ReadonlySet<string>;
  onCollapsed: (next: Set<string>) => void;
  density: Density;
  selection: ReadonlySet<number>;
  onSelection: (next: Set<number>) => void;
  activeId: number | null;
  onOpen: (row: ClassRow) => void;
  onCommit: (e: EditCommit) => Promise<boolean>;
  onToggleLock: (row: ClassRow) => void;
  onQuickFilter: (column: string, row: ClassRow, negate: boolean) => void;
  onKeyAction: (key: string, row: ClassRow | null) => boolean;
  readOnly: boolean;
  savingIds: ReadonlySet<string>;
  label: string;
  emptySlot?: ReactNode;
}

type Flat = { type: "group"; id: string; depth: number; label: ReactNode; field: string; leaves: ClassRow[] } | { type: "row"; id: string; depth: number; row: ClassRow };

const WIDTH: Record<string, number> = { select: 40, status: 122, course: 190, faculty: 180, program: 200, year: 58, instructor: 180, students: 84, mode: 104, reqTime: 150, weeks: 88, reqRoom: 170, definitive: 130, placement: 196, fit: 116, issues: 210, lock: 56, changed: 70, reqStatus: 140, source: 140, notes: 210 };
const RIGHT = new Set(["year", "students", "fit"]);
const HEAD_KEY: Record<string, MessageKey> = {
  select: "classes.col.select", status: "classes.col.status", course: "classes.col.course", faculty: "classes.col.faculty", program: "classes.col.program", year: "classes.col.year", instructor: "classes.col.instructor", students: "classes.col.students", mode: "classes.col.mode", reqTime: "classes.col.reqTime", weeks: "classes.col.weeks", reqRoom: "classes.col.reqRoom", definitive: "classes.col.definitive", placement: "classes.col.placement", fit: "classes.col.fit", issues: "classes.col.issues", lock: "classes.col.lock", changed: "classes.col.changed", reqStatus: "classes.col.reqStatus", source: "classes.col.source", notes: "classes.col.notes",
};
export const COLUMN_LABEL = HEAD_KEY;

const collator = new Intl.Collator("tr", { numeric: true, sensitivity: "base" });

function weeksLabel(ws: number[]): string {
  if (!ws.length) return "—";
  const s = [...ws].sort((a, b) => a - b);
  return s.every((w, i) => i === 0 || w === s[i - 1] + 1) ? (s.length > 1 ? `${s[0]}–${s[s.length - 1]}` : String(s[0])) : s.join(",");
}

export function StatusCell({ r }: { r: ClassRow }) {
  const { t } = useI18n();
  const s = r.placement_status;
  const icon =
    s === "placed" ? <Circle className="size-2.5 fill-current" /> : s === "partial" ? <Contrast className="size-3" /> : s === "unplaced" ? <CircleDashed className="size-3" /> : s === "conflict" ? <AlertTriangle className="size-3" /> : <Minus className="size-3" />;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[12px] font-medium", s === "placed" && "text-status-feasible-fg", s === "partial" && "text-status-warning-fg", s === "unplaced" && "text-status-warning-fg", s === "conflict" && "text-status-infeasible-fg", (s === "no_room_needed" || s === "no_run") && "text-label-2")}>
      <span aria-hidden>{icon}</span>
      {t(`classes.status.${s}`)}
      {s === "partial" && r.placement ? <span className="tabular-nums"> {r.placement.weeks_placed.length}/{r.req.weeks.length}</span> : null}
    </span>
  );
}

function ClassTableImpl(p: ClassTableProps) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const scroller = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState<{ row: number; col: number }>({ row: 0, col: 2 });
  const [edit, setEdit] = useState<{ rowId: string; column: string; value: string } | null>(null);
  const [savedFlash, setSavedFlash] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<number | null>(null);
  const rowH = ROW_H[p.density];

  const when = useCallback((day: number | null | undefined, sp: number | null | undefined, ep: number | null | undefined, date?: string | null) => {
    if (date && sp && ep) return `${formatDate(date, locale, { weekday: "short", day: "numeric", month: "short" })} ${periodRangeLabel(sp, ep)}`;
    if (!day || !sp || !ep) return null;
    return `${dayName(day, locale, "short")} ${periodRangeLabel(sp, ep)}`;
  }, [locale]);

  const columnDefs = useMemo<ColumnDef<ClassRow>[]>(() => {
    const groupCol = (id: string): ColumnDef<ClassRow> => ({ id: `g_${id}`, accessorFn: (r) => groupKey(r, id).key, enableSorting: false });
    return [
      ...["faculty", "program", "day", "room", "building", "status", "instructor", "year"].map(groupCol),
      { id: "status", accessorFn: (r) => ["conflict", "unplaced", "partial", "placed", "no_run", "no_room_needed"].indexOf(r.placement_status) },
      { id: "course", accessorFn: (r) => `${r.course_code} ${r.section ?? ""}`, sortingFn: (a, b) => collator.compare(a.getValue("course"), b.getValue("course")) },
      { id: "faculty", accessorFn: (r) => r.faculty_name ?? "", sortingFn: (a, b) => collator.compare(a.getValue("faculty"), b.getValue("faculty")) },
      { id: "program", accessorFn: (r) => r.program_name ?? "", sortingFn: (a, b) => collator.compare(a.getValue("program"), b.getValue("program")) },
      { id: "year", accessorFn: (r) => r.class_years[0] ?? 99 },
      { id: "instructor", accessorFn: (r) => r.instructors[0]?.name ?? "", sortingFn: (a, b) => collator.compare(a.getValue("instructor"), b.getValue("instructor")) },
      { id: "students", accessorFn: (r) => r.enrolment ?? -1 },
      { id: "mode", accessorFn: (r) => r.mode },
      { id: "reqTime", accessorFn: (r) => (r.req.day ?? 9) * 100 + (r.req.start_period ?? 99) },
      { id: "weeks", accessorFn: (r) => r.req.weeks.length },
      { id: "reqRoom", accessorFn: (r) => r.req.room_text ?? "" },
      { id: "definitive", accessorFn: (r) => r.definitive.room_codes.join(" ") },
      { id: "placement", accessorFn: (r) => (r.placement ? r.placement.day * 100 + r.placement.start_period : 9999) },
      { id: "fit", accessorFn: (r) => (r.placement?.capacity && r.enrolment ? r.enrolment / r.placement.capacity : -1) },
      { id: "issues", accessorFn: (r) => r.issues.length },
      { id: "lock", accessorFn: (r) => (r.placement?.locked ? 1 : 0) },
      { id: "changed", accessorFn: (r) => r.changed.length },
      { id: "reqStatus", accessorFn: (r) => r.req.status },
      { id: "source", accessorFn: (r) => r.provenance.row ?? 0 },
      { id: "notes", accessorFn: (r) => r.req.notes ?? "" },
      { id: "select", enableSorting: false },
    ];
  }, []);

  const grouping = useMemo(() => [p.group, p.subgroup].filter((g): g is string => !!g).map((g) => `g_${g}`), [p.group, p.subgroup]);
  // natural group order (faculty by name, day Mon→Sun, …): pre-sort the data; grouping keeps insertion order
  const data = useMemo(() => {
    if (!grouping.length) return p.rows;
    const keys = [p.group, p.subgroup].filter((g): g is string => !!g);
    return [...p.rows].sort((a, b) => {
      for (const k of keys) {
        const c = collator.compare(groupKey(a, k).order, groupKey(b, k).order);
        if (c) return c;
      }
      return 0;
    });
  }, [p.rows, grouping.length, p.group, p.subgroup]);

  const table = useReactTable({
    data,
    columns: columnDefs,
    state: { sorting: p.sort, grouping },
    onSortingChange: (u) => p.onSort(typeof u === "function" ? u(p.sort) : u),
    getCoreRowModel: getCoreRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => `${r.kind}${r.id}`,
    enableMultiSort: true,
    isMultiSortEvent: (e) => (e as MouseEvent).shiftKey,
    manualExpanding: true,
  });

  const flat = useMemo<Flat[]>(() => {
    const out: Flat[] = [];
    const walk = (rows: Row<ClassRow>[], depth: number) => {
      for (const r of rows) {
        if (r.getIsGrouped()) {
          const field = String(r.groupingColumnId ?? "").replace(/^g_/, "");
          const leaves = r.getLeafRows().filter((x) => !x.getIsGrouped()).map((x) => x.original);
          const first = leaves[0];
          const label = first ? groupLabel(field, first) : "—";
          out.push({ type: "group", id: r.id, depth, label, field, leaves });
          if (!p.collapsed.has(r.id)) walk(r.subRows, depth + 1);
        } else out.push({ type: "row", id: r.id, depth, row: r.original });
      }
    };
    walk(table.getSortedRowModel().rows, 0);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, data, p.sort, grouping, p.collapsed, locale]);

  function groupLabel(field: string, r: ClassRow): ReactNode {
    if (field === "faculty") return <span className="flex items-center gap-2"><span aria-hidden className="size-2 rounded-full" style={{ background: `var(--fac-${r.faculty_slot}-bar)` }} />{r.faculty_name ?? "—"}</span>;
    if (field === "day") {
      const d = r.placement?.day ?? r.req.day;
      return d ? dayName(d, locale) : "—";
    }
    if (field === "status") return t(`classes.status.${r.placement_status}`);
    if (field === "year") return r.class_years[0] ? (lang === "tr" ? `${r.class_years[0]}. sınıf` : `Year ${r.class_years[0]}`) : "—";
    return groupKey(r, field).label;
  }

  const stickyIndexes = useMemo(() => flat.map((f, i) => (f.type === "group" && f.depth === 0 ? i : -1)).filter((i) => i >= 0), [flat]);
  const v = useVirtualizer({
    count: flat.length,
    getScrollElement: () => scroller.current,
    estimateSize: (i) => (flat[i].type === "group" ? (flat[i].depth === 0 ? 36 : 32) : rowH),
    overscan: 10,
    rangeExtractor: (range) => {
      const prev = [...stickyIndexes].reverse().find((i) => i <= range.startIndex) ?? -1;
      const out = new Set<number>(prev >= 0 ? [prev] : []);
      for (let i = range.startIndex; i <= range.endIndex; i++) out.add(i);
      return [...out].sort((a, b) => a - b);
    },
  });

  const firstVisible = v.range?.startIndex ?? 0;
  const activeSticky = [...stickyIndexes].reverse().find((i) => i <= firstVisible) ?? -1;
  const cols = p.columns;
  const totalW = cols.reduce((s, c) => s + (WIDTH[c] ?? 120), 0);
  const leftOf = (i: number) => cols.slice(0, i).reduce((s, c) => s + (WIDTH[c] ?? 120), 0);
  const pinned = (c: string) => c === "select" || c === "course";

  // keep the cursor in range
  const cursorRow = Math.min(cursor.row, Math.max(0, flat.length - 1));
  const focusRow = flat[cursorRow];

  const scrollToIndex = (i: number) => v.scrollToIndex(i, { align: "auto" });

  const startEdit = (row: ClassRow, column: string) => {
    if (p.readOnly || !EDITABLE.has(column)) return false;
    const value = column === "students" ? String(row.enrolment ?? "") : column === "reqStatus" ? row.req.status : (row.req.notes ?? "");
    setEdit({ rowId: `${row.kind}${row.id}`, column, value });
    return true;
  };

  const commitEdit = async (move: "down" | "right" | null) => {
    if (!edit) return;
    const f = flat.find((x) => x.type === "row" && x.id === edit.rowId);
    const e = edit;
    setEdit(null);
    if (f && f.type === "row") {
      const ok = await p.onCommit({ row: f.row, column: e.column, value: e.value });
      if (ok) {
        setSavedFlash(`${e.rowId}:${e.column}`);
        setTimeout(() => setSavedFlash(null), 1000);
      }
    }
    if (move === "down") moveCursor(cursorRow + 1, cursor.col);
    if (move === "right") moveCursor(cursorRow, cursor.col + 1);
    scroller.current?.focus();
  };

  const moveCursor = (r: number, c: number) => {
    const row = Math.min(flat.length - 1, Math.max(0, r));
    const col = Math.min(cols.length - 1, Math.max(0, c));
    setCursor({ row, col });
    scrollToIndex(row);
    const el = scroller.current;
    if (el) {
      const x = leftOf(col);
      const pinW = (WIDTH.select ?? 40) + (WIDTH.course ?? 190);
      if (x - el.scrollLeft < pinW && !pinned(cols[col])) el.scrollLeft = Math.max(0, x - pinW);
      else if (x + (WIDTH[cols[col]] ?? 120) > el.scrollLeft + el.clientWidth) el.scrollLeft = x + (WIDTH[cols[col]] ?? 120) - el.clientWidth;
    }
  };

  const toggleSel = (id: number, extend = false) => {
    const next = new Set(p.selection);
    if (extend && anchor !== null) {
      const ids = flat.filter((f): f is Extract<Flat, { type: "row" }> => f.type === "row").map((f) => f.row.id);
      const a = ids.indexOf(anchor);
      const b = ids.indexOf(id);
      if (a >= 0 && b >= 0) for (const x of ids.slice(Math.min(a, b), Math.max(a, b) + 1)) next.add(x);
    } else if (next.has(id)) next.delete(id);
    else next.add(id);
    setAnchor(id);
    p.onSelection(next);
  };

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (edit) return;
    const meta = e.metaKey || e.ctrlKey;
    const row = focusRow?.type === "row" ? focusRow.row : null;
    if (p.onKeyAction(meta ? `mod+${e.key.toLowerCase()}` : e.key, row)) {
      e.preventDefault();
      return;
    }
    switch (e.key) {
      case "ArrowDown":
      case "j":
        e.preventDefault();
        if (e.shiftKey && row) {
          const nxt = flat[cursorRow + 1];
          if (nxt?.type === "row") toggleSel(nxt.row.id, true);
        }
        return moveCursor(meta ? flat.length - 1 : cursorRow + 1, cursor.col);
      case "ArrowUp":
      case "k":
        e.preventDefault();
        if (e.shiftKey && row) {
          const prv = flat[cursorRow - 1];
          if (prv?.type === "row") toggleSel(prv.row.id, true);
        }
        return moveCursor(meta ? 0 : cursorRow - 1, cursor.col);
      case "ArrowLeft":
        e.preventDefault();
        if (focusRow?.type === "group") return p.onCollapsed(new Set([...p.collapsed, focusRow.id]));
        return moveCursor(cursorRow, cursor.col - 1);
      case "ArrowRight":
        e.preventDefault();
        if (focusRow?.type === "group") {
          const next = new Set(p.collapsed);
          next.delete(focusRow.id);
          return p.onCollapsed(next);
        }
        return moveCursor(cursorRow, cursor.col + 1);
      case "Home":
        e.preventDefault();
        return moveCursor(cursorRow, 0);
      case "End":
        e.preventDefault();
        return moveCursor(cursorRow, cols.length - 1);
      case "Enter":
        e.preventDefault();
        if (focusRow?.type === "group") {
          const next = new Set(p.collapsed);
          if (next.has(focusRow.id)) next.delete(focusRow.id);
          else next.add(focusRow.id);
          return p.onCollapsed(next);
        }
        if (row && !startEdit(row, cols[cursor.col])) p.onOpen(row);
        return;
      case "F2":
      case "e":
        if (row) {
          e.preventDefault();
          startEdit(row, cols[cursor.col]);
        }
        return;
      case "x":
      case " ":
        if (row) {
          e.preventDefault();
          toggleSel(row.id);
        }
        return;
      case "[":
        e.preventDefault();
        return p.onCollapsed(new Set(flat.filter((f) => f.type === "group").map((f) => f.id)));
      case "]":
        e.preventDefault();
        return p.onCollapsed(new Set());
      default:
    }
  };

  // follow the inspector (‹ › / J K): keep the active row in view
  const activeId = p.activeId;
  useEffect(() => {
    if (activeId === null) return;
    const i = flat.findIndex((f) => f.type === "row" && f.row.id === activeId);
    if (i >= 0) {
      v.scrollToIndex(i, { align: "auto" });
    }
  }, [activeId, flat, v]);

  const header = (
    <div role="row" className="glass-thick sticky top-0 z-20 flex hairline-b" style={{ width: totalW, height: HEADER_H }}>
      {cols.map((c, i) => {
        const col = table.getColumn(c);
        const sorted = col?.getIsSorted();
        const allSel = p.rows.length > 0 && p.rows.every((r) => p.selection.has(r.id));
        return (
          <div
            key={c}
            role="columnheader"
            aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
            className={cn("flex shrink-0 items-center px-2 text-[12px] font-semibold text-label-2", RIGHT.has(c) && "justify-end", pinned(c) && "glass-thick sticky z-10")}
            style={{ width: WIDTH[c] ?? 120, left: pinned(c) ? leftOf(i) : undefined }}
          >
            {c === "select" ? (
              <Checkbox aria-label={t("classes.col.select")} checked={allSel} onCheckedChange={(v2) => p.onSelection(v2 ? new Set(p.rows.map((r) => r.id)) : new Set())} />
            ) : col?.getCanSort() ? (
              <button type="button" className="flex items-center gap-1 truncate hover:text-label-1" onClick={(e) => col.toggleSorting(undefined, e.shiftKey)}>
                {t(HEAD_KEY[c])}
                {sorted === "asc" ? <ArrowUp className="size-3" aria-hidden /> : sorted === "desc" ? <ArrowDown className="size-3" aria-hidden /> : null}
              </button>
            ) : (
              <span className="truncate">{t(HEAD_KEY[c])}</span>
            )}
          </div>
        );
      })}
    </div>
  );

  const renderCell = (c: string, r: ClassRow) => {
    const isEditing = edit && edit.rowId === `${r.kind}${r.id}` && edit.column === c;
    if (isEditing && edit) {
      const common = {
        autoFocus: true,
        "aria-label": t(HEAD_KEY[c]),
        className: "h-7 w-full rounded-md bg-(--mat-thick-solid) px-1.5 text-[13px] outline-2 outline-(--focus)",
        onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
          if (e.key === "Escape") {
            e.preventDefault();
            setEdit(null);
            scroller.current?.focus();
          } else if (e.key === "Enter") {
            e.preventDefault();
            void commitEdit("down");
          } else if (e.key === "Tab") {
            e.preventDefault();
            void commitEdit("right");
          }
        },
        onBlur: () => void commitEdit(null),
      };
      if (c === "reqStatus")
        return (
          <select {...common} value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })}>
            {["NEW", "PARSED", "NEEDS_REVIEW", "LOCKED"].map((s) => <option key={s} value={s}>{t(`classes.req.${s}` as MessageKey)}</option>)}
          </select>
        );
      return <input {...common} inputMode={c === "students" ? "numeric" : undefined} value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} />;
    }
    const saving = p.savingIds.has(`${r.kind}${r.id}:${c}`);
    const flash = savedFlash === `${r.kind}${r.id}:${c}`;
    const content = cellContent(c, r);
    return (
      <span className="relative flex min-w-0 items-center gap-1">
        {content}
        {saving ? <span aria-hidden className="absolute -right-1 size-2.5 animate-spin rounded-full border border-label-4 border-t-label-1" /> : null}
        {flash ? <span className="absolute right-0 text-[11px] text-status-feasible-fg" role="status">✓</span> : null}
      </span>
    );
  };

  const cellContent = (c: string, r: ClassRow): ReactNode => {
    const dash = <span className="text-label-3">—</span>;
    switch (c) {
      case "status":
        return <StatusCell r={r} />;
      case "course":
        return (
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-[13px]"><span className="font-semibold">{r.course_code}</span>{r.section ? <span className="text-label-2"> §{r.section}</span> : null}</span>
            {p.density !== "compact" && r.course_name ? <span className="truncate text-[11px] text-label-2">{r.course_name}</span> : null}
          </span>
        );
      case "faculty":
        return <span className="flex min-w-0 items-center gap-1.5 truncate text-[12px]"><span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: `var(--fac-${r.faculty_slot}-bar)` }} />{r.faculty_name ?? "—"}</span>;
      case "program":
        return <span className="flex min-w-0 items-center gap-1 truncate text-[12px]">{r.program_name ?? dash}{r.is_evening ? <span className="shrink-0 rounded-full bg-fill-2 px-1.5 text-[10px] font-semibold text-label-2"><Moon className="inline size-2.5" aria-hidden /> {t("classes.evening")}</span> : null}</span>;
      case "year":
        return <span className="text-[12px] tabular-nums">{r.class_years.length ? (r.class_years.length > 1 ? `${Math.min(...r.class_years)}–${Math.max(...r.class_years)}` : r.class_years[0]) : dash}</span>;
      case "instructor":
        return r.instructors.length ? <span className="truncate text-[12px]" title={r.instructors.map((i) => i.name).join(", ")}>{r.instructors[0].name}{r.instructors.length > 1 ? ` +${r.instructors.length - 1}` : ""}</span> : dash;
      case "students":
        return <span className="text-[13px] tabular-nums">{r.enrolment ?? dash}</span>;
      case "mode":
        return <span className="text-[12px]">{t(`classes.mode.${r.mode}` as MessageKey)}</span>;
      case "reqTime":
        return <span className="truncate text-[12px] tabular-nums">{when(r.req.day, r.req.start_period, r.req.end_period, r.req.date) ?? dash}</span>;
      case "weeks":
        return <span className="text-[12px] tabular-nums" title={r.req.weeks.join(", ")}>{weeksLabel(r.req.weeks)}</span>;
      case "reqRoom": {
        const chips = [...r.req.room_codes, ...(r.req.building ? [`${r.req.building} blok`] : []), ...(r.req.capacity ? [`≥ ${r.req.capacity}`] : []), ...r.req.tags];
        if (!chips.length) return r.req.room_text ? <span className="truncate text-[12px] text-label-2 italic" title={r.req.room_text}>“{r.req.room_text}”</span> : dash;
        return (
          <span className="flex min-w-0 gap-1" title={r.req.room_text ?? undefined}>
            {chips.slice(0, 2).map((x) => <span key={x} className="shrink-0 rounded-full bg-fill-2 px-1.5 text-[11px] font-medium">{x}</span>)}
            {chips.length > 2 ? <span className="text-[11px] text-label-2">+{chips.length - 2}</span> : null}
          </span>
        );
      }
      case "definitive":
        return r.definitive.room_codes.length || r.definitive.text ? <span className="truncate text-[12px] font-semibold" data-testid="definitive-room">{r.definitive.room_codes.join(" + ") || r.definitive.text}</span> : dash;
      case "placement": {
        if (!r.placement) return dash;
        const pl = r.placement;
        const differs = (r.req.day && r.req.day !== pl.day) || (r.req.start_period && r.req.start_period !== pl.start_period) || (r.definitive.room_codes.length > 0 && r.definitive.room_codes.join() !== pl.room_codes.join());
        return (
          <span className="flex min-w-0 items-center gap-1 truncate text-[12px] tabular-nums">
            <span className="truncate">{when(pl.day, pl.start_period, pl.end_period, r.kind === "exam" ? pl.date : null)} · <span className="font-semibold">{pl.room_codes.join(" + ")}</span></span>
            {differs ? <span aria-label={t("calendar.state.ghost", { run: "" })} className="shrink-0 text-label-3">↔</span> : null}
          </span>
        );
      }
      case "fit": {
        const cap = r.placement?.capacity;
        if (!cap || !r.enrolment) return dash;
        const pct = Math.round((r.enrolment / cap) * 100);
        return <span className={cn("text-[12px] tabular-nums", (pct > 100 || pct < 30) && "font-medium text-status-warning-fg")}>{r.enrolment}/{cap} · %{pct}</span>;
      }
      case "issues": {
        if (!r.issues.length) return null;
        const hard = r.issues.some((i) => i.severity === "hard");
        return (
          <span className={cn("flex min-w-0 items-center gap-1 text-[12px]", hard ? "text-status-infeasible-fg" : "text-status-warning-fg")} title={r.issues.map((i) => i.text[lang]).join("\n")}>
            <span aria-hidden>{hard ? "▲" : "•"}</span>
            <span className="tabular-nums">{r.issues.length}</span>
            <span className="truncate">· {r.issues[0].text[lang]}</span>
          </span>
        );
      }
      case "lock":
        return r.placement ? (
          <button type="button" className="rounded-md p-1 text-label-2 hover:bg-fill-2 hover:text-label-1 disabled:opacity-40" aria-label={r.placement.locked ? t("calendar.insp.unlock") : t("calendar.insp.lock")} aria-pressed={r.placement.locked} disabled={p.readOnly} onClick={(e) => { e.stopPropagation(); p.onToggleLock(r); }}>
            {r.placement.locked ? <Lock className="size-3.5" /> : <LockOpen className="size-3.5 opacity-40" />}
          </button>
        ) : null;
      case "changed":
        return r.changed.length ? <span className="flex items-center gap-1" title={r.changed.map((c2) => `${c2.field}: ${String(c2.from)} → ${String(c2.to)}`).join("\n")}><span aria-hidden className="size-1.5 rounded-full bg-[var(--status-warning-solid)]" /><span className="sr-only">{t("classes.col.changed")}</span><span className="truncate text-[11px] text-label-2">{r.changed.map((c2) => c2.field).join(", ")}</span></span> : null;
      case "reqStatus":
        return <span className="text-[12px]">{t(`classes.req.${r.req.status}` as MessageKey)}</span>;
      case "source":
        return <span className="truncate text-[12px] text-label-2 tabular-nums">{r.provenance.file_name ? `${r.provenance.file_name.replace(/\.xlsx?$/i, "").slice(-14)} · ` : ""}{r.provenance.row ? `${lang === "tr" ? "satır" : "row"} ${r.provenance.row}` : "—"}</span>;
      case "notes":
        return r.req.notes ? <span className="truncate text-[12px] text-label-2" title={r.req.notes}>{r.req.notes}</span> : dash;
      default:
        return null;
    }
  };

  return (
    <div
      ref={scroller}
      role={grouping.length ? "treegrid" : "grid"}
      aria-label={p.label}
      aria-rowcount={flat.length + 1}
      aria-colcount={cols.length}
      aria-multiselectable
      tabIndex={0}
      onKeyDown={onKey}
      className="relative min-h-0 flex-1 overflow-auto outline-none focus-visible:outline-none"
      data-testid="classes-table"
    >
      {header}
      {flat.length === 0 ? p.emptySlot : null}
      <div style={{ height: v.getTotalSize(), width: totalW, position: "relative" }}>
        {v.getVirtualItems().map((vi) => {
          const f = flat[vi.index];
          const isSticky = vi.index === activeSticky && f.type === "group";
          const style = isSticky
            ? { position: "sticky" as const, top: HEADER_H, zIndex: 15, height: vi.size }
            : { position: "absolute" as const, top: 0, transform: `translateY(${vi.start}px)`, height: vi.size };
          if (f.type === "group") {
            const agg = aggregate(f.leaves);
            const open = !p.collapsed.has(f.id);
            const focused = cursorRow === vi.index;
            return (
              <div
                key={f.id}
                role="row"
                aria-level={f.depth + 1}
                aria-expanded={open}
                aria-rowindex={vi.index + 2}
                className={cn("glass-thick left-0 flex items-center gap-2 pr-3 hairline-b", focused && "outline-2 -outline-offset-2 outline-(--focus)")}
                style={{ ...style, width: totalW, paddingLeft: 8 + f.depth * 16 }}
                data-testid="classes-group"
              >
                <button
                  type="button"
                  aria-label={open ? t("classes.group.collapse", { name: typeof f.label === "string" ? f.label : f.field }) : t("classes.group.expand", { name: typeof f.label === "string" ? f.label : f.field })}
                  onClick={(e) => {
                    const next = new Set(p.collapsed);
                    if (e.altKey) {
                      const same = flat.filter((x) => x.type === "group" && x.depth === f.depth).map((x) => x.id);
                      if (open) same.forEach((id) => next.add(id));
                      else same.forEach((id) => next.delete(id));
                    } else if (open) next.add(f.id);
                    else next.delete(f.id);
                    p.onCollapsed(next);
                  }}
                  className="rounded p-0.5 text-label-2 hover:text-label-1"
                >
                  <ChevronRight className={cn("size-3.5 transition-transform duration-(--dur-fast)", open && "rotate-90")} />
                </button>
                <span className={cn("sticky left-10 flex min-w-0 items-center gap-2 truncate", f.depth === 0 ? "text-[13px] font-semibold" : "text-[12px] font-semibold text-label-1")}>{f.label}</span>
                <span className="sticky right-3 ml-auto shrink-0 text-[12px] text-label-2 tabular-nums">
                  {t("classes.group.aggregate", { n: agg.n, s: agg.students.toLocaleString(locale), p: agg.placedPct, i: agg.issues })}
                </span>
                <button type="button" className="sr-only focus:not-sr-only focus:text-[12px]" onClick={() => p.onSelection(new Set([...p.selection, ...f.leaves.map((x) => x.id)]))}>{t("classes.group.select")}</button>
              </div>
            );
          }
          const r = f.row;
          const selected = p.selection.has(r.id);
          return (
            <div
              key={f.id}
              role="row"
              aria-rowindex={vi.index + 2}
              aria-level={grouping.length ? f.depth + 1 : undefined}
              aria-selected={selected}
              data-testid="classes-row"
              data-class-id={r.id}
              className={cn("group/row left-0 flex hairline-b hover:bg-fill-3", selected && "bg-tint-soft", p.activeId === r.id && "bg-fill-2")}
              style={{ ...style, width: totalW }}
              onClick={(e) => {
                setCursor((cc) => ({ ...cc, row: vi.index }));
                if (e.metaKey || e.ctrlKey) toggleSel(r.id);
                else if (e.shiftKey) toggleSel(r.id, true);
                else p.onOpen(r);
              }}
              onDoubleClick={(e) => {
                const cell = (e.target as HTMLElement).closest("[data-col]")?.getAttribute("data-col");
                if (cell) startEdit(r, cell);
              }}
            >
              {cols.map((c, ci) => {
                const focused = cursorRow === vi.index && cursor.col === ci;
                return (
                  <div
                    key={c}
                    role="gridcell"
                    data-col={c}
                    aria-colindex={ci + 1}
                    aria-readonly={!EDITABLE.has(c) || p.readOnly}
                    className={cn("flex shrink-0 items-center overflow-hidden px-2", RIGHT.has(c) && "justify-end", pinned(c) && "cal-canvas sticky z-[5] group-hover/row:bg-[color-mix(in_srgb,var(--cal-canvas),var(--label-1)_4%)]", pinned(c) && selected && "bg-[color-mix(in_srgb,var(--cal-canvas),var(--accent)_12%)]", focused && "outline-2 -outline-offset-2 outline-(--focus) [[role=grid]:not(:focus-within)_&]:outline-0 [[role=treegrid]:not(:focus-within)_&]:outline-0")}
                    style={{ width: WIDTH[c] ?? 120, left: pinned(c) ? leftOf(ci) : undefined }}
                    onClick={(e) => {
                      if (e.altKey) {
                        e.stopPropagation();
                        p.onQuickFilter(c, r, e.shiftKey);
                      }
                    }}
                  >
                    {c === "select" ? (
                      <span className={cn("flex", !selected && "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100")} onClick={(e) => e.stopPropagation()}>
                        <Checkbox aria-label={`${r.course_code}${r.section ? ` §${r.section}` : ""} ${t("classes.col.select").toLocaleLowerCase(locale)}`} checked={selected} onCheckedChange={() => toggleSel(r.id)} />
                      </span>
                    ) : (
                      renderCell(c, r)
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const ClassTable = memo(ClassTableImpl);
