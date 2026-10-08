"use client";
/**
 * ClassInspector, shared by /timetable (calendar.md §5.3) and /classes (all-classes.md §9): a non-modal glass
 * panel. Request (as submitted, then as understood) · placement in the selected run with the solver checks ·
 * "Yerleşimi açıkla" (per-assignment explain; deterministic template unless a model paraphrase is grounded) ·
 * provenance file · sheet · row with the raw Excel row · placements across runs.
 */
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Copy, Link2, Lock, LockOpen, MessageSquareText, Minus, MoreHorizontal, MoveRight, X } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { calendarApi, type ExplainOut, type IndexAssignment } from "@/lib/api/calendar";
import { classesApi, useClassDetail, type ClassKind, type ClassRow } from "@/lib/api/classes";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { chipVars } from "@/components/timetable/event-chip";
import { spanText } from "@/components/timetable/model/check";

export interface InspectorProps {
  termId: number | null;
  runId: number | null;
  kind: ClassKind;
  /** calendar: the selected assignment (board rows matched to a request carry `mr`) */
  assignment?: IndexAssignment | null;
  roomName?: (id: number) => string;
  roomCap?: (ids: number[]) => number;
  allWeeks?: number[];
  /** classes: the selected row */
  row?: ClassRow | null;
  readOnly?: boolean;
  onClose: () => void;
  onMove?: () => void;
  /** may return the save promise: the header then shows "Saving…" / "Saved" (calendar.md §9.5) */
  onLock?: (locked: boolean) => void | Promise<unknown>;
  onPrev?: () => void;
  onNext?: () => void;
  surface: "calendar" | "classes";
  className?: string;
  /** focus "why here" (E key) */
  explainSignal?: number;
  /** spring in on mount (motion.md: inspector appear, springs.sheet); off inside a bottom sheet that animates itself */
  appear?: boolean;
}

function SectionBlock({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  return (
    <section className="flex flex-col gap-1.5 py-3 hairline-t first:shadow-none" aria-labelledby={id}>
      <h3 id={id} className="text-[11px] font-semibold text-label-3">{title}</h3>
      {children}
    </section>
  );
}

function WeekSquares({ all, placed, label }: { all: number[]; placed: number[]; label: string }) {
  const set = new Set(placed);
  return (
    <span className="flex flex-wrap items-center gap-[3px]" role="img" aria-label={label}>
      {all.map((w) => (
        <span key={w} aria-hidden className={cn("size-2.5 rounded-[2px]", set.has(w) ? "bg-label-2" : "shadow-[inset_0_0_0_1px_var(--hairline-strong)]")} title={String(w)} />
      ))}
    </span>
  );
}

const ORIGINS = { SOLVER: 1, MANUAL: 1, IMPORT: 1, AI_EDIT: 1 } as const;

function weeksText(ws: number[]): string {
  if (!ws.length) return "—";
  const s = [...ws].sort((a, b) => a - b);
  return s.every((w, i) => i === 0 || w === s[i - 1] + 1) ? (s.length > 1 ? `${s[0]}–${s[s.length - 1]}` : String(s[0])) : s.join(",");
}

export function ClassInspector(p: InspectorProps) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const mr = p.row?.id ?? p.assignment?.mr ?? null;
  const detail = useClassDetail(p.termId, mr, p.kind, p.runId);
  const row = p.row ?? detail.data?.row ?? null;
  const [explain, setExplain] = useState<{ state: "idle" | "loading" | "done" | "error"; out?: ExplainOut }>({ state: "idle" });
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const [save, setSave] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
  }, []);
  const abort = useRef<AbortController | null>(null);
  const whyRef = useRef<HTMLButtonElement>(null);
  const aid = p.assignment?.id ?? row?.placement?.assignment_ids[0] ?? null;
  const exactAssignment = p.assignment ? true : row?.placement?.matched === "request";

  useEffect(() => {
    abort.current?.abort();
    // a different class: drop the previous explanation
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExplain({ state: "idle" });
    setShowRaw(false);
  }, [aid, mr]);

  useEffect(() => {
    if (p.explainSignal) whyRef.current?.focus();
  }, [p.explainSignal]);

  const runExplain = useCallback(async () => {
    if (p.runId === null || aid === null) return;
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    setExplain({ state: "loading" });
    try {
      const out = await calendarApi.explain(p.runId, aid, lang, ctl.signal);
      setExplain({ state: "done", out });
    } catch (e) {
      if ((e as { name?: string }).name === "AbortError" || ctl.signal.aborted) setExplain({ state: "idle" });
      else setExplain({ state: "error" });
    }
  }, [p.runId, aid, lang]);

  const onLock = p.onLock;
  async function lockNow(next: boolean) {
    if (!onLock) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    setSave("saving");
    try {
      if ((await onLock(next)) === false) {
        setSave("error");
        return;
      }
      setSave("saved");
      saveTimer.current = setTimeout(() => setSave("idle"), 1000);
    } catch {
      setSave("error");
    }
  }
  const copyLink = () => {
    void navigator.clipboard?.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  const a = p.assignment;
  const code = row?.course_code ?? a?.code ?? a?.label ?? "";
  const section = row?.section ?? a?.sec ?? null;
  const slot = row?.faculty_slot ?? a?.slot ?? 8;
  const name = row?.course_name ?? a?.name ?? null;
  const prog = row?.program_name ?? a?.prog ?? null;
  const years = row?.class_years?.length ? row.class_years : a?.year ? [a.year] : [];
  const placement = row?.placement;
  const day = a?.day ?? placement?.day ?? row?.req.day ?? null;
  const sp = a?.sp ?? placement?.start_period ?? row?.req.start_period ?? null;
  const ep = a?.ep ?? placement?.end_period ?? row?.req.end_period ?? null;
  const rooms = a ? a.rooms.map((r) => p.roomName?.(r) ?? String(r)) : (placement?.room_codes ?? []);
  const cap = a ? (p.roomCap?.(a.rooms) ?? a.cap ?? 0) : (placement?.capacity ?? 0);
  const size = a?.size ?? row?.enrolment ?? 0;
  const locked = a?.locked ?? placement?.locked ?? false;
  const conflictText = row?.issues.find((i) => i.severity === "hard")?.text[lang] ?? (a?.reasons.length ? a.reasons[0] : null);
  const statusLine = (() => {
    if (row?.placement_status === "unplaced") return { tone: "warning", text: t("classes.insp.unplacedReason", { reason: row.issues[0]?.text[lang] ?? "" }), glyph: <Minus className="size-3.5" /> };
    if (conflictText && (row?.placement_status === "conflict" || (a && a.reasons.some((r) => !r.startsWith("capacity"))))) return { tone: "infeasible", text: `${t("calendar.state.conflict")}: ${conflictText}`, glyph: <AlertTriangle className="size-3.5" /> };
    if (row?.placement_status === "no_room_needed") return { tone: "neutral", text: t("classes.status.no_room_needed"), glyph: <Minus className="size-3.5" /> };
    if (row?.placement_status === "partial") return { tone: "warning", text: `${t("classes.status.partial")} · ${row.placement?.weeks_placed.length ?? 0}/${row.req.weeks.length}`, glyph: <Minus className="size-3.5" /> };
    return { tone: "feasible", text: `${t("calendar.state.placed")}${locked ? ` · ${t("calendar.state.locked")}` : ""}`, glyph: <Check className="size-3.5" /> };
  })();
  const fit = cap ? Math.round((size / cap) * 100) : null;
  const origin = a?.origin ?? placement?.origin ?? null;
  const allWeeks = p.allWeeks ?? row?.req.weeks ?? [];
  const placedWeeks = a?.weeks.length ? a.weeks : (placement?.weeks_placed ?? []);
  const checks = explain.out?.checks?.length ? explain.out.checks : (detail.data?.checks ?? []);
  const prov = row?.provenance;
  const raw = detail.data?.raw_row ?? null;
  const calendarHref = (() => {
    const sel = aid ? `&sel=${aid}` : "";
    const roomId = a?.rooms[0] ?? placement?.room_ids[0];
    return `/timetable?lens=week${roomId ? `&subject=room:${roomId}` : ""}${day ? `&day=${day}` : ""}${p.runId ? `&run=${p.runId}` : ""}${sel}`;
  })();

  return (
    <motion.aside
      className={cn("glass-thick flex min-h-0 flex-col overflow-hidden rounded-2xl text-label-1", p.className)}
      aria-label={t("calendar.insp.label")}
      data-glass="thick"
      data-testid="class-inspector"
      initial={p.appear === false ? false : reduce ? { opacity: 0 } : { opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={reduce ? { duration: 0.1 } : { x: springs.sheet, opacity: { duration: 0.1 } }}
    >
      <header className="flex items-start gap-3 px-4 pt-4 pb-3" style={chipVars(slot)}>
        <span aria-hidden className="mt-1 h-10 w-[3px] shrink-0 rounded-full" style={{ background: "var(--chip-bar)" }} />
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] leading-[22px] font-semibold">{code}{section ? ` §${section}` : ""}</h2>
          {name ? <p className="truncate text-[13px] text-label-2">{name}</p> : null}
          <p className="truncate text-[12px] text-label-2">{[prog, years.length ? (lang === "tr" ? `${years.join("–")}. sınıf` : `year ${years.join("–")}`) : null].filter(Boolean).join(" · ")}</p>
          <p className={cn("mt-1 flex items-center gap-1.5 text-[12px] font-medium", statusLine.tone === "feasible" && "text-status-feasible-fg", statusLine.tone === "warning" && "text-status-warning-fg", statusLine.tone === "infeasible" && "text-status-infeasible-fg", statusLine.tone === "neutral" && "text-label-2")} data-testid="inspector-status">
            <span aria-hidden>{statusLine.glyph}</span>
            <span className="min-w-0">{statusLine.text}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center">
          {save !== "idle" ? (
            <span role="status" className={cn("mr-1 text-[11px] font-medium", save === "error" ? "text-status-infeasible-fg" : "text-label-2")} data-testid="inspector-save">
              {save === "saving" ? t("calendar.insp.saving") : save === "saved" ? t("calendar.insp.saved") : t("calendar.insp.saveFailed")}
            </span>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("calendar.insp.more")} data-testid="inspector-more" />}>
              <MoreHorizontal />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-48">
              <DropdownMenuItem onClick={copyLink}><Link2 aria-hidden />{t("calendar.insp.copyLink")}</DropdownMenuItem>
              {p.runId !== null ? <DropdownMenuItem render={<Link href={`/runs/${p.runId}?tab=chat`} />}><MessageSquareText aria-hidden />{t("calendar.insp.openChat")}</DropdownMenuItem> : null}
            </DropdownMenuContent>
          </DropdownMenu>
          {copied ? <span role="status" className="sr-only">{t("calendar.insp.linkCopied")}</span> : null}
          {p.onPrev ? <Button variant="ghost" size="icon-sm" aria-label={t("classes.insp.prev")} onClick={p.onPrev}><ChevronLeft /></Button> : null}
          {p.onNext ? <Button variant="ghost" size="icon-sm" aria-label={t("classes.insp.next")} onClick={p.onNext}><ChevronRight /></Button> : null}
          <Button variant="ghost" size="icon-sm" aria-label={t("calendar.insp.close")} onClick={p.onClose}><X /></Button>
        </div>
      </header>
      {!p.readOnly && aid !== null ? (
        <div className="flex flex-wrap gap-1.5 px-4 pb-3">
          {p.onMove ? <Button size="sm" variant="secondary" onClick={p.onMove} data-testid="inspector-move"><MoveRight aria-hidden />{t("calendar.insp.move")}</Button> : null}
          {onLock ? <Button size="sm" variant="secondary" disabled={save === "saving"} onClick={() => void lockNow(!locked)} data-testid="inspector-lock">{locked ? <LockOpen aria-hidden /> : <Lock aria-hidden />}{locked ? t("calendar.insp.unlock") : t("calendar.insp.lock")}</Button> : null}
          {p.surface === "calendar" && mr ? <Button size="sm" variant="ghost" render={<Link href={`/classes?id=${mr}${p.runId ? `&run=${p.runId}` : ""}`} />}>{t("calendar.insp.openClasses")}</Button> : null}
          {p.surface === "classes" ? <Button size="sm" variant="ghost" render={<Link href={calendarHref} />} data-testid="open-in-calendar">{t("calendar.insp.openCalendar")}</Button> : null}
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        <SectionBlock title={p.surface === "classes" ? t("classes.insp.request") : t("calendar.insp.whenWhere")}>
          {row?.req.room_text ? <p className="text-[12px] text-label-2 italic">“{row.req.room_text}”</p> : null}
          {day && sp && ep ? (
            <p className="text-[13px] tabular-nums">
              {dayName(day, locale)} {spanText(sp, ep)} <span className="text-label-2">(P{sp}–P{ep})</span>
            </p>
          ) : null}
          {row?.definitive.room_codes.length || row?.definitive.text ? (
            <p className="text-[13px]"><span className="text-label-2">{t("calendar.insp.definitive")}:</span> <span className="font-semibold">{row.definitive.room_codes.join(" + ") || row.definitive.text}</span></p>
          ) : null}
          {rooms.length ? (
            <p className="text-[13px]" data-testid="inspector-room">
              <span className="text-label-2">{t("calendar.insp.placement")}:</span> <span className="font-semibold">{rooms.join(" + ")}</span>
              {cap ? <span className="text-label-2 tabular-nums"> · {t("calendar.insp.studentsLine", { size, cap, fit: fit ?? 0 })}</span> : null}
            </p>
          ) : null}
          {rooms.length && cap && fit !== null ? (
            <span aria-hidden className="relative h-1 w-full max-w-[220px] overflow-hidden rounded-full bg-fill-2" data-testid="inspector-fit">
              <span className={cn("absolute inset-y-0 left-0 rounded-full", fit > 100 ? "bg-status-infeasible-fg" : fit < 35 ? "bg-status-warning-fg" : "bg-status-feasible-fg")} style={{ width: `${Math.min(100, fit)}%` }} />
            </span>
          ) : null}
          {origin && rooms.length ? (
            <p className="text-[12px] text-label-2">{t("calendar.insp.originLine", { origin: t(`calendar.insp.origin.${(origin in ORIGINS ? origin : "SOLVER") as keyof typeof ORIGINS}`) })}{locked ? ` · ${t("calendar.state.locked")}` : ""}</p>
          ) : null}
          {allWeeks.length > 1 ? (
            <div className="flex items-center gap-2 text-[12px] text-label-2">
              <span>{t("calendar.insp.weeks", { weeks: weeksText(placedWeeks.length ? placedWeeks : allWeeks) })}{placedWeeks.length ? "" : ` · ${t("classes.insp.requestedWeeks")}`}</span>
              <WeekSquares all={allWeeks} placed={placedWeeks} label={t("calendar.insp.weeks", { weeks: weeksText(placedWeeks.length ? placedWeeks : allWeeks) })} />
            </div>
          ) : null}
          {row?.req.warnings.length ? <ul className="text-[12px] text-status-warning-fg">{row.req.warnings.slice(0, 3).map((w) => <li key={w}>{w}</li>)}</ul> : null}
          {placement?.matched === "board" ? <p className="text-[11px] text-label-3">{t("calendar.insp.matchedBoard")}</p> : null}
        </SectionBlock>

        <SectionBlock title={t("calendar.insp.who")}>
          <p className="text-[13px] tabular-nums">{size || "—"} {lang === "tr" ? "öğrenci" : "students"}{cap ? ` · ${cap} ${lang === "tr" ? "koltuk" : "seats"}` : ""}</p>
          {(row?.instructors.length ? row.instructors.map((i) => ({ id: i.id ?? null, name: i.name })) : (a?.instr ?? []).map((n, i) => ({ id: a?.instr_ids[i] ?? null, name: n }))).map((i) => (
            i.id ? <Link key={`${i.id}-${i.name}`} href={`/timetable?lens=week&subject=instructor:${i.id}${p.runId ? `&run=${p.runId}` : ""}`} className="w-fit text-[13px] text-tint-text hover:underline">{i.name}</Link> : <span key={i.name} className="text-[13px]">{i.name}</span>
          ))}
          {prog && (row?.program_id ?? a?.prog_id) && years[0] ? (
            <Link href={`/timetable?lens=week&subject=cohort:${row?.program_id ?? a?.prog_id}:${years[0]}${p.runId ? `&run=${p.runId}` : ""}`} className="w-fit text-[13px] text-tint-text hover:underline">{t("calendar.subject.cohortLabel", { program: prog, year: years[0] })}</Link>
          ) : null}
        </SectionBlock>

        <SectionBlock title={t("calendar.insp.why")}>
          {checks.length ? (
            <ul className="flex flex-col gap-1 text-[12px]">
              {checks.map((c) => (
                <li key={c.key} className="flex items-start gap-1.5">
                  <span aria-hidden className={cn("mt-px", c.state === "ok" ? "text-status-feasible-fg" : c.state === "fail" ? "text-status-infeasible-fg" : "text-label-3")}>{c.state === "ok" ? "✓" : c.state === "fail" ? "✕" : "–"}</span>
                  <span className="sr-only">{c.state === "ok" ? "✓" : c.state === "fail" ? "✕" : "–"}</span>
                  <span>{c.text[lang]}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {row?.placement_status === "unplaced" ? (
            <p className="text-[12px] text-label-2">{t("classes.insp.unplacedHint")}</p>
          ) : null}
          {row?.placement_status === "no_room_needed" ? <p className="text-[12px] text-label-2">{t("classes.insp.noRoomHint")}</p> : null}
          {(row?.issues ?? []).filter((i) => i.code !== "unplaced").slice(0, 4).map((i, k) => (
            <p key={k} className={cn("text-[12px]", i.severity === "hard" ? "text-status-infeasible-fg" : "text-status-warning-fg")}>{i.severity === "hard" ? "▲" : "•"} {i.text[lang]}</p>
          ))}
          {aid !== null && exactAssignment !== false && p.runId !== null ? (
            <div className="flex flex-col gap-2">
              {explain.state === "idle" ? (
                <Button ref={whyRef} size="sm" variant="secondary" className="w-fit" onClick={() => void runExplain()} data-testid="explain-placement">
                  <MessageSquareText aria-hidden />{t("calendar.insp.explain")}
                </Button>
              ) : null}
              {explain.state === "loading" ? (
                <div className="flex items-center gap-2 text-[12px]" role="status">
                  <span className={cn("font-medium", !reduce && "cal-thinking")}>{t("calendar.insp.explaining")}</span>
                  <Button size="xs" variant="ghost" onClick={() => abort.current?.abort()}>{t("calendar.insp.cancel")}</Button>
                </div>
              ) : null}
              {explain.state === "error" ? (
                <p className="flex items-center gap-2 text-[12px] text-status-infeasible-fg" role="alert">
                  {t("calendar.insp.explainError")}
                  <Button size="xs" variant="ghost" onClick={() => void runExplain()}>{t("calendar.retry")}</Button>
                </p>
              ) : null}
              {explain.state === "done" && explain.out ? (
                <div className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3" data-testid="explain-result">
                  {explain.out.sections.filter((s) => s.key !== "why" || explain.out?.source === "model").map((s) => (
                    <div key={s.key} className="flex flex-col gap-0.5">
                      <p className="text-[12px] font-semibold">{s.title}</p>
                      {s.lines.map((l, i) => <p key={i} className="text-[12px] leading-[17px] text-label-1">{l}</p>)}
                    </div>
                  ))}
                  <div className="flex items-center gap-2 pt-1 text-[11px] text-label-3">
                    <span>{explain.out.source === "model" ? t("calendar.insp.sourceModel") : t("calendar.insp.sourceTemplate")}</span>
                    <Button size="xs" variant="ghost" onClick={() => void runExplain()}>{t("calendar.insp.regenerate")}</Button>
                    <Button
                      size="xs"
                      variant="ghost"
                      onClick={() => {
                        void navigator.clipboard?.writeText(explain.out?.text ?? "").then(() => {
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1200);
                        });
                      }}
                    >
                      <Copy aria-hidden />{copied ? t("calendar.insp.copied") : t("calendar.insp.copy")}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </SectionBlock>

        {prov || mr ? (
          <SectionBlock title={t("calendar.insp.source")}>
            {prov ? (
              <p className="text-[13px]" data-testid="inspector-source">
                {t("calendar.insp.sourceLine", { file: prov.file_name ?? (prov.kind === "exam-list" ? t("calendar.insp.examList") : t("calendar.insp.planningList")), sheet: prov.sheet ?? "—", row: prov.row ?? "—" })}
              </p>
            ) : a && !a.mr ? (
              <p className="text-[13px]">{t("calendar.insp.board")}</p>
            ) : detail.isLoading ? (
              <p className="text-[12px] text-label-3">{t("calendar.loading")}</p>
            ) : null}
            <div className="flex flex-wrap gap-1.5">
              {raw ? <Button size="xs" variant="ghost" onClick={() => setShowRaw((v) => !v)} aria-expanded={showRaw}>{showRaw ? t("calendar.insp.hideRow") : t("calendar.insp.showRow")}</Button> : null}
              {prov?.import_job_id ? <Button size="xs" variant="ghost" render={<a href={classesApi.importFileUrl(prov.import_job_id)} />}>{t("calendar.insp.download")}</Button> : null}
            </div>
            {showRaw && raw ? (
              <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-3 gap-y-1 rounded-xl bg-fill-3 p-2.5 text-[12px]" data-testid="raw-row">
                {Object.entries(raw).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-label-2">{k}</dt>
                    <dd className={cn("break-words", (v === null || String(v).trim() === "") && "text-label-3")}>{v === null || String(v).trim() === "" ? "—" : String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </SectionBlock>
        ) : null}

        {detail.data && !detail.data.history.length && p.runId !== null ? (
          <SectionBlock title={t("calendar.insp.history")}>
            <p className="text-[12px] text-label-2">{t("calendar.insp.noHistory")}</p>
          </SectionBlock>
        ) : null}
        {detail.data?.history.length ? (
          <SectionBlock title={t("calendar.insp.history")}>
            <ul className="flex flex-col gap-1 text-[12px] tabular-nums">
              {detail.data.history.map((h) => (
                <li key={h.run_id} className={cn("flex items-baseline gap-2", h.run_id === p.runId && "font-semibold")}>
                  <span className="w-14 shrink-0">Run #{h.run_id}</span>
                  <span className="min-w-0 flex-1 truncate">{h.room_codes.join(" + ") || "—"}{h.day && h.start_period ? ` · ${dayName(h.day, locale, "short")} ${PERIODS[h.start_period - 1]?.start ?? ""}` : ""}</span>
                  {h.locked ? <Lock className="size-3 shrink-0 text-label-3" aria-label={t("calendar.state.locked")} /> : null}
                </li>
              ))}
            </ul>
          </SectionBlock>
        ) : null}
      </div>
    </motion.aside>
  );
}

/** Multi-selection summary (calendar.md §5.3 end; all-classes.md §9): counts and bulk actions. */
export function SelectionSummary({ count, students, buildings, onLock, onUnlock, onMove, onClear, className, extra }: { count: number; students: number; buildings: number; onLock?: () => void; onUnlock?: () => void; onMove?: () => void; onClear: () => void; className?: string; extra?: ReactNode }) {
  const { t, n } = useI18n();
  return (
    <aside className={cn("glass-thick flex flex-col gap-3 rounded-2xl p-4", className)} aria-label={t("classes.bulk.label")} data-glass="thick">
      <p className="type-headline" aria-live="polite">{t("calendar.insp.selection", { n: n(count), students: n(students), buildings })}</p>
      <div className="flex flex-wrap gap-1.5">
        {onLock ? <Button size="sm" variant="secondary" onClick={onLock}><Lock aria-hidden />{t("classes.bulk.lock")}</Button> : null}
        {onUnlock ? <Button size="sm" variant="secondary" onClick={onUnlock}><LockOpen aria-hidden />{t("classes.bulk.unlock")}</Button> : null}
        {onMove ? <Button size="sm" variant="secondary" onClick={onMove}><MoveRight aria-hidden />{t("classes.bulk.move")}</Button> : null}
        {extra}
        <Button size="sm" variant="ghost" onClick={onClear}>{t("calendar.insp.clearSelection")}</Button>
      </div>
    </aside>
  );
}
