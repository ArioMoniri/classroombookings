"use client";
/**
 * /classes, "Tüm dersler" (docs/design/v2/all-classes.md): every meeting (or exam) of the term with its
 * request, placement in the selected run, issues and provenance. Saved views as tabs (system + personal +
 * shared; server-side with a localStorage fallback), token search, Filtre +, Görünüm (group / sub-group / sort /
 * columns / density), glass group headers with aggregates, inline edit and Excel paste, a selection bar that
 * replaces the toolbar capsule, the shared inspector, exports (incl. the planning-list round-trip).
 */
import "@/components/timetable/calendar.css";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Ellipsis, Lock, LockOpen, MoveRight, Search, SlidersHorizontal, X, CalendarDays } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { ClassInspector, SelectionSummary } from "./class-inspector";
import { useSavedViews, useSaveView, useDeleteView, type SavedView } from "@/lib/api/calendar";
import { useClasses, classesApi, type ClassKind, type ClassRow, type ClassesOut } from "@/lib/api/classes";
import { api } from "@/lib/api/endpoints";
import { useMe, usePrograms, useRooms, useRuns } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useCalendarActions } from "@/components/timetable/use-calendar-actions";
import { useUndoStore } from "@/components/timetable/model/undo-store";
import { defaultRun, usableRuns, useTermContext } from "@/components/timetable/use-calendar-data";
import { BulkMoveDialog } from "./bulk-move-dialog";
import { ClassCards } from "./class-cards";
import { COLUMN_LABEL, ClassTable, type EditCommit } from "./class-table";
import { ALL_COLUMNS, SYSTEM_VIEWS, applyFilters, defaultView, normalizeView, parsePastedColumn, parseTokens, sameView, systemPredicate, type SystemView, type ViewState } from "./classes-model";
import { FilterChips, FilterMenu } from "./filter-bar";
import { dayName, periodRangeLabel } from "@/lib/time";

const LOCAL_VIEWS = "smartsched.classes.views";
const GROUPS = ["faculty", "program", "day", "room", "building", "instructor", "status", "year"] as const;

function useMedia(q: string) {
  const [m, setM] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setM(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}

function useFill(ref: React.RefObject<HTMLElement | null>) {
  const [h, setH] = useState<number | undefined>();
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const m = () => setH(Math.max(420, window.innerHeight - el.getBoundingClientRect().top - 12));
    m();
    window.addEventListener("resize", m);
    return () => window.removeEventListener("resize", m);
  }, [ref]);
  return h;
}

type LocalView = { id: string; name: string; state: ViewState };
function readLocal(): LocalView[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_VIEWS) ?? "[]") as LocalView[];
  } catch {
    return [];
  }
}

export function ClassesPage() {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const me = useMe();
  const readOnly = me.data?.role === "VIEWER";
  const mobile = useMedia("(max-width: 767px)");
  const wide = useMedia("(min-width: 1600px)");
  const rootRef = useRef<HTMLDivElement>(null);
  const fill = useFill(rootRef);
  const searchRef = useRef<HTMLInputElement>(null);
  const filterRef = useRef<HTMLButtonElement>(null);
  const saveCurrentRef = useRef<() => Promise<void>>(async () => {});

  // ------------------------------------------------------------------ term, kind, run
  const kind: ClassKind = params.get("kind") === "exams" ? "exams" : "meetings";
  const requestedRun = params.get("run") ? Number(params.get("run")) : null;
  const { term, termId } = useTermContext();
  const runsQ = useRuns(termId !== null ? { term_id: termId } : undefined);
  const hydrated = useHydrated();
  const runs = useMemo(() => (hydrated ? usableRuns(runsQ.data, termId).filter((r) => (r.kind === "EXAM") === (kind === "exams")) : []), [hydrated, runsQ.data, termId, kind]);
  const runId = requestedRun ?? defaultRun(runs, term)?.id ?? runs[0]?.id ?? null;
  const classes = useClasses(termId, kind, runId);
  const allRows = useMemo(() => classes.data?.items ?? [], [classes.data]);
  const programs = usePrograms();
  const rooms = useRooms();
  const tipRooms = useMemo(() => new Set((rooms.data ?? []).filter((r) => r.tags.includes("TIP")).map((r) => r.display_name)), [rooms.data]);
  const actions = useCalendarActions(runId, useMemo(() => ({ isAdmin: me.data?.role === "ADMIN" }), [me.data?.role]));
  const setUndoRun = useUndoStore((s) => s.setRun);
  useEffect(() => setUndoRun(runId), [runId, setUndoRun]);

  // ------------------------------------------------------------------ views
  const serverViews = useSavedViews("classes");
  const saveView = useSaveView("classes");
  const deleteView = useDeleteView("classes");
  const [localViews, setLocalViews] = useState<LocalView[]>([]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read the browser fallback once after mount
    setLocalViews(readLocal());
  }, []);
  const saved: { id: string; name: string; state: ViewState; shared: boolean; mine: boolean; local: boolean }[] = useMemo(
    () => [
      ...(serverViews.data ?? []).map((v: SavedView) => ({ id: v.id, name: v.name, state: normalizeView(v.state), shared: v.shared, mine: v.mine, local: false })),
      ...(serverViews.isError ? localViews.map((v) => ({ ...v, state: normalizeView(v.state), shared: false, mine: true, local: true })) : []),
    ],
    [serverViews.data, serverViews.isError, localViews],
  );
  const viewParam = params.get("view") ?? "all";
  const isSystem = (SYSTEM_VIEWS as string[]).includes(viewParam);
  const savedView = saved.find((v) => v.id === viewParam);
  const baseline = useMemo<ViewState>(() => (savedView ? savedView.state : defaultView((isSystem ? viewParam : "all") as SystemView)), [savedView, isSystem, viewParam]);
  // legacy deep links (⌘K course → /requests?q=, programme → /requests?program_id=) arrive as a draft of the view
  const [drafts, setDrafts] = useState<Record<string, ViewState>>(() => {
    const q = params.get("q");
    const prog = Number(params.get("program_id") ?? params.get("program") ?? "") || null;
    if (!q && prog === null) return {};
    const base = defaultView((isSystem ? viewParam : "all") as SystemView);
    return { [viewParam]: { ...base, filters: { ...base.filters, text: q ?? "", program: prog !== null ? [prog] : [] } } };
  });
  const view = drafts[viewParam] ?? baseline;
  const setView = useCallback((patch: Partial<ViewState>) => setDrafts((d) => ({ ...d, [viewParam]: { ...(d[viewParam] ?? baseline), ...patch } })), [viewParam, baseline]);
  const modified = !sameView(view, baseline);

  const setParam = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    router.replace(`/classes?${next.toString()}`, { scroll: false });
  }, [params, router]);

  // ------------------------------------------------------------------ query
  const [search, setSearch] = useState(view.filters.text);
  const systemRows = useMemo(() => allRows.filter(systemPredicate(view.system, tipRooms)), [allRows, view.system, tipRooms]);
  const rows = useMemo(() => applyFilters(systemRows, view.filters), [systemRows, view.filters]);
  const counts = useMemo(() => Object.fromEntries(SYSTEM_VIEWS.map((v) => [v, allRows.filter(systemPredicate(v, tipRooms)).length])) as Record<SystemView, number>, [allRows, tipRooms]);
  const tokenCtx = useMemo(() => ({ faculties: [...new Map(allRows.filter((r) => r.faculty_id).map((r) => [r.faculty_id as number, { id: r.faculty_id as number, name: r.faculty_name ?? "" }])).values()], programs: (programs.data ?? []).map((p) => ({ id: p.id, name: p.name })), modes: ["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"] }), [allRows, programs.data]);
  const onSearch = (text: string) => {
    setSearch(text);
    // a token becomes a chip when followed by a space
    if (/\s$/.test(text)) {
      const r = parseTokens(text, { ...view.filters, text: "" }, tokenCtx);
      if (r.consumed.length) {
        setView({ filters: r.filters });
        setSearch(r.rest ? `${r.rest} ` : "");
        return;
      }
    }
    setView({ filters: { ...view.filters, text } });
  };
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    const h = setTimeout(() => setAnnounce(t("classes.announce", { n: rows.length })), 500);
    return () => clearTimeout(h);
  }, [rows.length, t]);

  // ------------------------------------------------------------------ selection + inspector
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const activeId = params.get("id") ? Number(params.get("id")) : null;
  const active = allRows.find((r) => r.id === activeId) ?? null;
  const [explainSignal, setExplainSignal] = useState(0);
  const [moveOpen, setMoveOpen] = useState(false);
  const [saveAs, setSaveAs] = useState<{ name: string; shared: boolean } | null>(null);
  const [paste, setPaste] = useState<{ values: (number | null)[]; rows: ClassRow[] } | null>(null);
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const selectedRows = useMemo(() => allRows.filter((r) => selection.has(r.id)), [allRows, selection]);
  const openRow = useCallback((r: ClassRow) => setParam({ id: String(r.id) }), [setParam]);
  const step = (dir: 1 | -1) => {
    const i = rows.findIndex((r) => r.id === activeId);
    const next = rows[Math.min(rows.length - 1, Math.max(0, i + dir))];
    if (next) openRow(next);
  };

  // ------------------------------------------------------------------ edits (request fields → next run)
  const patchRow = useCallback((id: number, fn: (r: ClassRow) => ClassRow) => {
    qc.setQueryData<ClassesOut>(["classes", termId, kind, runId, null], (old) => (old ? { ...old, items: old.items.map((r) => (r.id === id ? fn(r) : r)) } : old));
  }, [qc, termId, kind, runId]);

  const saveField = useCallback(async (r: ClassRow, column: string, value: string): Promise<boolean> => {
    const key = `${r.kind}${r.id}:${column}`;
    const prev = r;
    const body: Record<string, unknown> = {};
    if (column === "students") {
      const nVal = value.trim() === "" ? null : Number(value);
      if (nVal !== null && (!Number.isFinite(nVal) || nVal < 0)) return false;
      if (nVal === r.enrolment) return true;
      body.enrolment = nVal;
      patchRow(r.id, (x) => ({ ...x, enrolment: nVal }));
    } else if (column === "reqStatus") {
      if (value === r.req.status) return true;
      body.status = value;
      patchRow(r.id, (x) => ({ ...x, req: { ...x.req, status: value } }));
    } else if (column === "notes") {
      if (value === (r.req.notes ?? "")) return true;
      body.notes = value || null;
      patchRow(r.id, (x) => ({ ...x, req: { ...x.req, notes: value || null } }));
    } else return false;
    setSavingIds((s) => new Set(s).add(key));
    try {
      if (r.kind === "exam") await api.requests.updateExam(r.id, body as never);
      else await api.requests.updateMeeting(r.id, body as never);
      toast.success(`${r.course_code} · ${t("classes.edit.saved")}`, { description: t("classes.edit.nextRun"), duration: 3000 });
      const inverseBody = column === "students" ? { enrolment: prev.enrolment } : column === "reqStatus" ? { status: prev.req.status } : { notes: prev.req.notes };
      useUndoStore.getState().push({
        label: `${r.course_code} · ${t(COLUMN_LABEL[column])}`,
        inverse: async () => {
          await (r.kind === "exam" ? api.requests.updateExam(r.id, inverseBody as never) : api.requests.updateMeeting(r.id, inverseBody as never));
          patchRow(r.id, () => prev);
        },
        forward: async () => {
          await (r.kind === "exam" ? api.requests.updateExam(r.id, body as never) : api.requests.updateMeeting(r.id, body as never));
          void qc.invalidateQueries({ queryKey: ["classes"] });
        },
      });
      return true;
    } catch (e) {
      patchRow(r.id, () => prev);
      toast.error(t("classes.edit.failed", { reason: e instanceof Error ? e.message : String(e) }), {
        action: {
          label: t("classes.retry"),
          onClick: () => {
            patchRow(r.id, (x) => (column === "students" ? { ...x, enrolment: body.enrolment as number | null } : column === "reqStatus" ? { ...x, req: { ...x.req, status: String(body.status) } } : { ...x, req: { ...x.req, notes: (body.notes as string | null) ?? null } }));
            void (r.kind === "exam" ? api.requests.updateExam(r.id, body as never) : api.requests.updateMeeting(r.id, body as never))
              .then(() => toast.success(`${r.course_code} · ${t("classes.edit.saved")}`))
              .catch((err: unknown) => { patchRow(r.id, () => prev); toast.error(String(err)); });
          },
        },
      });
      return false;
    } finally {
      setSavingIds((s) => {
        const next = new Set(s);
        next.delete(key);
        return next;
      });
    }
  }, [patchRow, qc, t]);

  const onCommit = useCallback((e: EditCommit) => saveField(e.row, e.column, e.value), [saveField]);

  const toggleLock = useCallback((r: ClassRow) => {
    if (!r.placement) return;
    void actions.lock(r.placement.assignment_ids, !r.placement.locked, r.course_code);
    patchRow(r.id, (x) => (x.placement ? { ...x, placement: { ...x.placement, locked: !x.placement.locked } } : x));
  }, [actions, patchRow]);

  const lockSelection = (locked: boolean) => {
    const withPlacement = selectedRows.filter((r) => r.placement);
    const skipped = selectedRows.length - withPlacement.length;
    const ids = withPlacement.flatMap((r) => r.placement?.assignment_ids ?? []);
    if (!ids.length) return;
    if (selectedRows.length > 100 && !window.confirm(t("classes.bulk.confirmLarge", { n: selectedRows.length }))) return;
    void actions.lock(ids, locked, withPlacement[0].course_code).then(() => {
      withPlacement.forEach((r) => patchRow(r.id, (x) => (x.placement ? { ...x, placement: { ...x.placement, locked } } : x)));
      if (skipped) toast(t("classes.bulk.result", { a: withPlacement.length, b: skipped, reason: t("classes.bulk.noPlacement") }));
    });
  };

  // ------------------------------------------------------------------ export
  const exportView = () => {
    const cols = view.columns.filter((c) => c !== "select");
    const cell = (r: ClassRow, c: string): string => {
      switch (c) {
        case "course": return `${r.course_code}${r.section ? ` §${r.section}` : ""}`;
        case "status": return t(`classes.status.${r.placement_status}`);
        case "program": return r.program_name ?? "";
        case "faculty": return r.faculty_name ?? "";
        case "year": return r.class_years.join(",");
        case "instructor": return r.instructors.map((i) => i.name).join(" / ");
        case "students": return String(r.enrolment ?? "");
        case "placement": return r.placement ? `${dayName(r.placement.day, locale, "short")} ${periodRangeLabel(r.placement.start_period, r.placement.end_period)} ${r.placement.room_codes.join(" + ")}` : "";
        case "definitive": return r.definitive.room_codes.join(" + ") || (r.definitive.text ?? "");
        case "reqRoom": return r.req.room_text ?? "";
        case "issues": return r.issues.map((i) => i.text[lang]).join("; ");
        case "reqTime": return r.req.day && r.req.start_period && r.req.end_period ? `${dayName(r.req.day, locale, "short")} ${periodRangeLabel(r.req.start_period, r.req.end_period)}` : "";
        case "source": return String(r.provenance.row ?? "");
        case "notes": return r.req.notes ?? "";
        default: return "";
      }
    };
    const esc = (s: string) => (/[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
    const body = [cols.map((c) => t(COLUMN_LABEL[c])).join(","), ...(selectedRows.length ? selectedRows : rows).map((r) => cols.map((c) => esc(cell(r, c))).join(","))].join("\n");
    const blob = new Blob(["﻿", body], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${term?.code ?? "dersler"}-${viewParam}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const download = (format: "planning-list" | "csv") => {
    if (termId === null) return;
    const a = document.createElement("a");
    a.href = classesApi.exportUrl(termId, format, kind, runId);
    a.click();
  };

  // ------------------------------------------------------------------ keyboard + clipboard
  const onKeyAction = useCallback((key: string, row: ClassRow | null): boolean => {
    switch (key) {
      case "l":
        if (row && !readOnly) toggleLock(row);
        return !!row;
      case "o":
        if (row?.placement) router.push(`/timetable?lens=week&subject=room:${row.placement.room_ids[0]}&day=${row.placement.day}&sel=${row.placement.assignment_ids[0]}${runId ? `&run=${runId}` : ""}`);
        return !!row;
      case ".":
        if (row) {
          openRow(row);
          setExplainSignal((x) => x + 1);
        }
        return !!row;
      case "/":
        searchRef.current?.focus();
        return true;
      case "f":
        filterRef.current?.click();
        return true;
      case "mod+a":
        setSelection(new Set(rows.map((r) => r.id)));
        return true;
      case "Escape":
        if (selection.size) setSelection(new Set());
        else if (activeId !== null) setParam({ id: null });
        return true;
      case "mod+s":
        if (modified && savedView?.mine) void saveCurrentRef.current();
        return true;
      default:
        return false;
    }
  }, [readOnly, toggleLock, router, runId, openRow, rows, selection.size, activeId, setParam, modified, savedView]);

  useEffect(() => {
    const onCopy = (e: ClipboardEvent) => {
      if (!selection.size || (document.activeElement && ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName))) return;
      const lines = selectedRows.map((r) => [r.course_code, r.section ?? "", r.program_name ?? "", r.enrolment ?? "", r.placement?.room_codes.join(" + ") ?? "", r.definitive.room_codes.join(" + ")].join("\t"));
      e.clipboardData?.setData("text/plain", lines.join("\n"));
      e.preventDefault();
      toast(t("calendar.insp.copied"));
    };
    const onPaste = (e: ClipboardEvent) => {
      if (readOnly || !selection.size || (document.activeElement && ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName))) return;
      const values = parsePastedColumn(e.clipboardData?.getData("text/plain") ?? "");
      if (!values.length) return;
      e.preventDefault();
      setPaste({ values, rows: rows.filter((r) => selection.has(r.id)) });
    };
    window.addEventListener("copy", onCopy);
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("copy", onCopy);
      window.removeEventListener("paste", onPaste);
    };
  }, [selection, selectedRows, rows, readOnly, t]);

  const applyPaste = async () => {
    if (!paste) return;
    const pairs = paste.rows.map((r, i) => [r, paste.values[i] ?? null] as const).filter(([r, v]) => v !== null && v !== r.enrolment);
    setPaste(null);
    for (const [r, v] of pairs) await saveField(r, "students", String(v));
  };

  // ------------------------------------------------------------------ saved views
  const saveCurrent = async () => {
    if (!savedView) return;
    try {
      if (savedView.local) {
        const next = readLocal().map((v) => (v.id === savedView.id ? { ...v, state: view } : v));
        localStorage.setItem(LOCAL_VIEWS, JSON.stringify(next));
        setLocalViews(next);
      } else await saveView.mutateAsync({ id: savedView.id, name: savedView.name, state: view as unknown as Record<string, unknown>, shared: savedView.shared });
      setDrafts((d) => {
        const next = { ...d };
        delete next[viewParam];
        return next;
      });
      toast.success(t("classes.view.saved"));
    } catch (e) {
      toast.error(String(e));
    }
  };
  useEffect(() => {
    saveCurrentRef.current = saveCurrent;
  });
  const doSaveAs = async () => {
    if (!saveAs?.name.trim()) return;
    try {
      const created = await saveView.mutateAsync({ name: saveAs.name.trim(), state: view as unknown as Record<string, unknown>, shared: saveAs.shared });
      setDrafts((d) => {
        const next = { ...d };
        delete next[viewParam];
        return next;
      });
      setSaveAs(null);
      setParam({ view: created.id });
      toast.success(t("classes.view.saved"));
    } catch {
      const local = { id: `local-${Date.now()}`, name: saveAs.name.trim(), state: view };
      const next = [...readLocal(), local];
      localStorage.setItem(LOCAL_VIEWS, JSON.stringify(next));
      setLocalViews(next);
      setSaveAs(null);
      setParam({ view: local.id });
      toast(t("classes.view.local"));
    }
  };

  // ------------------------------------------------------------------ render
  const collapsed = useMemo(() => new Set(view.collapsed), [view.collapsed]);
  const sumStudents = rows.reduce((s, r) => s + (r.enrolment ?? 0), 0);
  const tabs: { id: string; label: string; count?: number }[] = [
    ...SYSTEM_VIEWS.filter((v) => v === "all" || counts[v] > 0 || viewParam === v).map((v) => ({ id: v, label: t(`classes.view.${v}`), count: counts[v] })),
    ...saved.map((v) => ({ id: v.id, label: v.name })),
  ];
  const noRun = runId === null;
  const toolbarCapsule = "glass-chrome flex h-11 min-w-0 items-center gap-1 rounded-full px-1.5";

  const emptySlot = !classes.isLoading && rows.length === 0 ? (
    <div className="px-4 py-8">
      {allRows.length === 0 ? (
        <EmptyState size="sm" title={t("classes.empty.term")} actions={<Button size="sm" onClick={() => router.push("/import")}>{t("classes.empty.import")}</Button>} />
      ) : view.system === "unplaced" && !view.filters.text ? (
        <EmptyState size="sm" title={t("classes.empty.unplaced")} />
      ) : (
        <EmptyState size="sm" title={t("classes.empty.filtered")} actions={<Button size="sm" variant="secondary" onClick={() => { setView({ filters: defaultView().filters }); setSearch(""); }}>{t("calendar.empty.clearFilters")}</Button>} />
      )}
    </div>
  ) : null;

  const inspector = active ? (
    <ClassInspector
      surface="classes"
      className="h-full"
      termId={termId}
      runId={runId}
      kind={kind}
      row={active}
      readOnly={readOnly}
      onClose={() => setParam({ id: null })}
      onLock={active.placement ? () => toggleLock(active) : undefined}
      onMove={active.placement && !readOnly ? () => { setSelection(new Set([active.id])); setMoveOpen(true); } : undefined}
      onPrev={() => step(-1)}
      onNext={() => step(1)}
      explainSignal={explainSignal}
    />
  ) : null;

  return (
    <div ref={rootRef} className="flex min-h-0 gap-2" style={{ height: fill }} data-testid="classes">
      <section className="flex min-w-0 flex-1 flex-col gap-2">
        {/* title row (not glass) */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className={mobile ? "type-title-1" : "type-title-2"}>{t("classes.title")}</h1>
          <span className="text-[13px] text-label-2 tabular-nums">{term?.name}{runId ? ` · Run #${runId}` : ""}</span>
          {runs.length > 1 ? (
            <select aria-label={t("calendar.sidebar.run")} className="h-8 rounded-lg bg-fill-2 px-2 text-[13px]" value={runId ?? ""} onChange={(e) => setParam({ run: e.target.value })}>
              {runs.map((r) => <option key={r.id} value={r.id}>Run #{r.id} · {t(`runs.status.${r.status}`)}</option>)}
            </select>
          ) : null}
          <div className="ml-auto">
            <SegmentedGlass size="sm" aria-label={t("classes.kind.label")} options={[{ value: "meetings", label: t("classes.kind.meetings") }, { value: "exams", label: t("classes.kind.exams") }]} value={kind} onValueChange={(k) => setParam({ kind: k === "exams" ? "exams" : null, run: null, id: null })} />
          </div>
        </div>

        {/* saved views as tabs */}
        <LayoutGroup id="classes-views">
          <div role="tablist" aria-label={t("classes.view.tabs")} className="flex gap-1 overflow-x-auto pb-0.5 [scrollbar-width:none]" data-testid="view-tabs">
            {tabs.map((tab) => {
              const on = tab.id === viewParam;
              return (
                <button key={tab.id} type="button" role="tab" aria-selected={on} onClick={() => setParam({ view: tab.id === "all" ? null : tab.id, id: null })} className={cn("relative flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium", on ? "text-label-1" : "text-label-2 hover:text-label-1")}>
                  {on ? <motion.span layoutId="view-pill" transition={reduce ? { duration: 0 } : springs.glassMorph} aria-hidden className="absolute inset-0 -z-10 rounded-full bg-fill-2 shadow-[inset_0_0_0_1px_var(--hairline)]" style={{ borderRadius: 999 }} /> : null}
                  {tab.label}
                  {tab.count !== undefined ? <span className="text-[12px] text-label-3 tabular-nums">{n(tab.count)}</span> : null}
                </button>
              );
            })}
          </div>
        </LayoutGroup>

        {/* toolbar capsule ⇄ selection bar (one capsule morphing, motion.md §3.3) */}
        <LayoutGroup id="classes-toolbar">
          {selection.size > 0 && !mobile ? (
            <motion.div layoutId="toolbar-capsule" transition={reduce ? { duration: 0 } : springs.glassMorph} className={toolbarCapsule} data-glass="chrome" role="toolbar" aria-label={t("classes.bulk.label")} data-testid="selection-bar">
              <span className="px-2 text-[13px] font-semibold tabular-nums" aria-live="polite">{selection.size === rows.length && rows.length > 1 ? t("classes.bulk.all", { n: n(rows.length) }) : t("classes.bulk.selected", { n: n(selection.size) })}</span>
              {!readOnly ? <Button size="sm" variant="ghost" onClick={() => lockSelection(true)}><Lock aria-hidden />{t("classes.bulk.lock")}</Button> : null}
              {!readOnly ? <Button size="sm" variant="ghost" onClick={() => lockSelection(false)}><LockOpen aria-hidden />{t("classes.bulk.unlock")}</Button> : null}
              {!readOnly ? <Button size="sm" variant="ghost" onClick={() => setMoveOpen(true)}><MoveRight aria-hidden />{t("classes.bulk.move")}</Button> : null}
              <Button size="sm" variant="ghost" onClick={() => {
                const first = selectedRows.find((r) => r.placement);
                if (first?.placement) router.push(`/timetable?lens=board&day=${first.placement.day}&sel=${first.placement.assignment_ids[0]}${runId ? `&run=${runId}` : ""}`);
              }}><CalendarDays aria-hidden />{t("classes.bulk.calendar")}</Button>
              <Button size="sm" variant="ghost" onClick={exportView}><Download aria-hidden />{t("classes.bulk.export")}</Button>
              <Button size="icon-sm" variant="ghost" className="ml-auto" aria-label={t("classes.bulk.clear")} onClick={() => setSelection(new Set())}><X /></Button>
            </motion.div>
          ) : (
            <motion.div layoutId="toolbar-capsule" transition={reduce ? { duration: 0 } : springs.glassMorph} className={toolbarCapsule} data-glass="chrome" role="toolbar" aria-label={t("classes.display")}>
              <Search className="ml-1.5 size-4 shrink-0 text-label-3" aria-hidden />
              <input ref={searchRef} value={search} onChange={(e) => onSearch(e.target.value)} onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  setSearch("");
                  setView({ filters: { ...view.filters, text: "" } });
                } else if (e.key === "Enter") onSearch(`${search} `);
              }} placeholder={t("classes.search")} aria-label={t("classes.searchLabel")} title={t("classes.tokens.hint")} className="h-8 min-w-0 flex-1 bg-transparent px-1 text-[13px] outline-none placeholder:text-label-3" data-testid="classes-search" />
              <FilterMenu rows={systemRows} filters={view.filters} onChange={(f) => setView({ filters: f })} shownCount={rows.length} triggerRef={filterRef} />
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="ghost" size="sm" data-testid="display-menu" />}><SlidersHorizontal aria-hidden />{!mobile ? t("classes.display") : null}</DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="max-h-[70vh] w-64 overflow-y-auto">
                  <DropdownMenuGroup>
                    <DropdownMenuLabel>{t("classes.groupBy")}</DropdownMenuLabel>
                    <DropdownMenuRadioGroup value={view.group ?? ""} onValueChange={(v) => setView({ group: v || null, subgroup: v ? view.subgroup : null })}>
                      <DropdownMenuRadioItem value="">{t("classes.none")}</DropdownMenuRadioItem>
                      {GROUPS.map((g) => <DropdownMenuRadioItem key={g} value={g}>{t(`classes.f.${g === "status" ? "status" : g === "year" ? "year" : g}` as never)}</DropdownMenuRadioItem>)}
                    </DropdownMenuRadioGroup>
                  </DropdownMenuGroup>
                  {view.group ? (
                    <DropdownMenuGroup>
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel>{t("classes.subgroupBy")}</DropdownMenuLabel>
                      <DropdownMenuRadioGroup value={view.subgroup ?? ""} onValueChange={(v) => setView({ subgroup: v || null })}>
                        <DropdownMenuRadioItem value="">{t("classes.none")}</DropdownMenuRadioItem>
                        {GROUPS.filter((g) => g !== view.group).map((g) => <DropdownMenuRadioItem key={g} value={g}>{t(`classes.f.${g}` as never)}</DropdownMenuRadioItem>)}
                      </DropdownMenuRadioGroup>
                    </DropdownMenuGroup>
                  ) : null}
                  <DropdownMenuSeparator />
                  <DropdownMenuGroup>
                    <DropdownMenuLabel>{t("classes.density")}</DropdownMenuLabel>
                    <DropdownMenuRadioGroup value={view.density} onValueChange={(v) => setView({ density: v as ViewState["density"] })}>
                      {(["compact", "standard", "comfortable"] as const).map((d) => <DropdownMenuRadioItem key={d} value={d}>{t(`calendar.density.${d}`)}</DropdownMenuRadioItem>)}
                    </DropdownMenuRadioGroup>
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuGroup>
                    <DropdownMenuLabel>{t("classes.columns")}</DropdownMenuLabel>
                    {ALL_COLUMNS.filter((c) => c !== "select" && c !== "course").map((c) => (
                      <DropdownMenuCheckboxItem key={c} checked={view.columns.includes(c)} onCheckedChange={(on) => setView({ columns: on ? ALL_COLUMNS.filter((x) => x === c || view.columns.includes(x)) : view.columns.filter((x) => x !== c) })}>{t(COLUMN_LABEL[c])}</DropdownMenuCheckboxItem>
                    ))}
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="ghost" size="sm" data-testid="export-menu" />}><Download aria-hidden />{!mobile ? t("classes.export") : null}</DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-72">
                  {kind === "meetings" ? (
                    <DropdownMenuItem onClick={() => download("planning-list")} data-testid="export-planning-list">
                      <span className="flex flex-col"><span>{t("classes.exp.planning")}</span><span className="text-[11px] text-label-3">{t("classes.exp.planningHint")}</span></span>
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem onClick={exportView}>{t("classes.exp.view")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => download("csv")}>{t("classes.exp.csv")}</DropdownMenuItem>
                  {runId ? <DropdownMenuItem onClick={() => window.open(api.runs.exportUrl(runId, "ics"), "_blank")}>{t("classes.exp.ics")}</DropdownMenuItem> : null}
                </DropdownMenuContent>
              </DropdownMenu>
              {mobile ? (
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("classes.more")} />}><Ellipsis /></DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setSelectMode((v) => !v)}>{t("classes.mobile.select")}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </motion.div>
          )}
        </LayoutGroup>

        <FilterChips rows={systemRows} filters={view.filters} onChange={(f) => setView({ filters: f })} />
        {modified ? (
          <div className="flex flex-wrap items-center gap-2 text-[12px]" role="status" data-testid="view-modified">
            <span className="text-label-2">{t("classes.view.modified")}</span>
            {savedView?.mine ? <Button size="xs" variant="secondary" onClick={() => void saveCurrent()}>{t("classes.view.save")}</Button> : null}
            <Button size="xs" variant="secondary" onClick={() => setSaveAs({ name: "", shared: false })} data-testid="view-save-as">{t("classes.view.saveAs")}</Button>
            <Button size="xs" variant="ghost" onClick={() => { setDrafts((d) => { const next = { ...d }; delete next[viewParam]; return next; }); setSearch(baseline.filters.text); }}>{t("classes.view.reset")}</Button>
          </div>
        ) : null}
        {savedView && !modified ? (
          <div className="flex items-center gap-2 text-[12px] text-label-2">
            {savedView.shared ? t("classes.view.shared") : t("classes.view.mine")}
            {savedView.mine ? <Button size="xs" variant="ghost" onClick={async () => {
              if (savedView.local) {
                const next = readLocal().filter((v) => v.id !== savedView.id);
                localStorage.setItem(LOCAL_VIEWS, JSON.stringify(next));
                setLocalViews(next);
              } else await deleteView.mutateAsync(savedView.id);
              setParam({ view: null });
              toast(t("classes.view.deleted"));
            }}>{t("classes.view.delete")}</Button> : null}
          </div>
        ) : null}
        {noRun && !classes.isLoading ? (
          <div className="flex items-center gap-2 rounded-xl bg-fill-3 px-3 py-2 text-[13px]" role="status">{t("classes.noRunBanner")}<Button size="xs" onClick={() => router.push("/generate")}>{t("classes.generate")}</Button></div>
        ) : null}

        {/* table / cards */}
        <div className="cal-canvas relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
          {classes.isError && !classes.data ? (
            <div className="p-4"><p className="mb-2 text-[13px]">{t("classes.error")}</p><Button size="sm" variant="secondary" onClick={() => void classes.refetch()}>{t("classes.retry")}</Button></div>
          ) : classes.isLoading ? (
            <div aria-busy className="flex flex-col">
              {Array.from({ length: 10 }, (_, i) => (
                <div key={i} className="flex h-11 items-center gap-4 px-4 hairline-b"><span className="h-2 w-[30%] rounded-full bg-fill-2" /><span className="h-2 w-[18%] rounded-full bg-fill-3" /></div>
              ))}
            </div>
          ) : mobile ? (
            <ClassCards rows={rows} group={view.group} runId={runId} selection={selection} selectMode={selectMode} onToggle={(id) => setSelection((s) => { const next = new Set(s); if (next.has(id)) next.delete(id); else next.add(id); return next; })} onOpen={openRow} onLock={toggleLock} onExplain={(r) => { openRow(r); setExplainSignal((x) => x + 1); }} readOnly={readOnly} />
          ) : (
            <ClassTable
              rows={rows}
              columns={view.columns}
              sort={view.sort}
              onSort={(s) => setView({ sort: s })}
              group={view.group}
              subgroup={view.subgroup}
              collapsed={collapsed}
              onCollapsed={(c) => setView({ collapsed: [...c] })}
              density={view.density}
              selection={selection}
              onSelection={setSelection}
              activeId={activeId}
              onOpen={openRow}
              onCommit={onCommit}
              onToggleLock={toggleLock}
              onQuickFilter={(col, r, neg) => {
                if (neg) return;
                const f = view.filters;
                if (col === "faculty" && r.faculty_id) setView({ filters: { ...f, faculty: [r.faculty_id] } });
                else if (col === "program" && r.program_id) setView({ filters: { ...f, program: [r.program_id] } });
                else if (col === "placement" && r.placement) setView({ filters: { ...f, room: r.placement.room_codes.map((c) => c.toLocaleLowerCase("tr-TR").replace(/\s+/g, "")) } });
                else if (col === "status") setView({ filters: { ...f, placement: [r.placement_status] } });
              }}
              onKeyAction={onKeyAction}
              readOnly={readOnly}
              savingIds={savingIds}
              label={t("classes.title")}
              emptySlot={emptySlot}
            />
          )}
          {!mobile ? (
            <footer className="flex h-8 shrink-0 items-center gap-2 px-3 text-[12px] text-label-2 tabular-nums hairline-t">
              {classes.isLoading ? t("classes.loadingFooter") : t("classes.footer", { shown: n(rows.length), total: n(allRows.length), sel: n(selection.size), s: n(sumStudents) })}
            </footer>
          ) : null}
        </div>
        {mobile && selection.size > 0 ? (
          <div className="fixed inset-x-3 bottom-[max(1rem,env(safe-area-inset-bottom))] z-40">
            <SelectionSummary count={selection.size} students={selectedRows.reduce((s, r) => s + (r.enrolment ?? 0), 0)} buildings={new Set(selectedRows.flatMap((r) => r.placement?.room_codes.map((c) => c.split(" ")[0]) ?? [])).size} onLock={readOnly ? undefined : () => lockSelection(true)} onMove={readOnly ? undefined : () => setMoveOpen(true)} onClear={() => { setSelection(new Set()); setSelectMode(false); }} />
          </div>
        ) : null}
      </section>

      {active && !mobile ? (
        <div className={cn("flex min-h-0 w-[400px] shrink-0 flex-col", !wide && "fixed top-20 right-3 bottom-3 z-40")}>{inspector}</div>
      ) : null}
      {mobile ? (
        <Sheet open={active !== null} onOpenChange={(o) => !o && setParam({ id: null })}>
          <SheetContent side="bottom" className="max-h-[92dvh] p-0" showCloseButton={false}>
            <SheetTitle className="sr-only">{active?.course_code ?? ""}</SheetTitle>
            {inspector}
          </SheetContent>
        </Sheet>
      ) : null}

      <BulkMoveDialog open={moveOpen} onOpenChange={setMoveOpen} rows={selectedRows.length ? selectedRows : active ? [active] : []} runId={runId} onApply={async (items) => {
        const res = await actions.move(items, items.length === 1 ? (selectedRows[0]?.course_code ?? "") : "", "");
        if (res.applied) void qc.invalidateQueries({ queryKey: ["classes"] });
        return res.applied;
      }} />

      <Dialog open={saveAs !== null} onOpenChange={(o) => !o && setSaveAs(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("classes.view.saveAs")}</DialogTitle></DialogHeader>
          <label className="flex flex-col gap-1 text-[12px] font-semibold text-label-2">
            {t("classes.view.name")}
            <Input autoFocus value={saveAs?.name ?? ""} onChange={(e) => setSaveAs((s) => (s ? { ...s, name: e.target.value } : s))} onKeyDown={(e) => e.key === "Enter" && void doSaveAs()} data-testid="view-name" />
          </label>
          {!readOnly ? <label className="flex items-center gap-2 text-[13px]"><Switch checked={saveAs?.shared ?? false} onCheckedChange={(v) => setSaveAs((s) => (s ? { ...s, shared: v } : s))} />{t("classes.view.share")}</label> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSaveAs(null)}>{t("calendar.insp.cancel")}</Button>
            <Button onClick={() => void doSaveAs()} disabled={!saveAs?.name.trim()} data-testid="view-save">{t("classes.view.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={paste !== null} onOpenChange={(o) => !o && setPaste(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{paste ? t("classes.edit.paste", { n: Math.min(paste.values.length, paste.rows.length), field: t("classes.col.students").toLocaleLowerCase(locale) }) : ""}</DialogTitle></DialogHeader>
          <ul className="max-h-56 overflow-y-auto text-[12px] tabular-nums">
            {paste?.rows.slice(0, paste.values.length).map((r, i) => (
              <li key={r.id} className="flex gap-2 py-0.5"><span className="w-28 font-semibold">{r.course_code}{r.section ? ` §${r.section}` : ""}</span><span className="text-label-2">{r.enrolment ?? "—"}</span> → <span>{paste.values[i] ?? "—"}</span></li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPaste(null)}>{t("calendar.insp.cancel")}</Button>
            <Button onClick={() => void applyPaste()}>{t("classes.edit.pasteApply")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <p className="sr-only" aria-live="polite">{announce}</p>
    </div>
  );
}
