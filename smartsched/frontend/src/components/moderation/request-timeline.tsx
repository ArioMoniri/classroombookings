"use client";
/**
 * The person's request history grouped by term, newest first (moderation spec §5.2, R4/R7): each term is a
 * `<section>` with an `<ol>` of outcome-first rows: glyph + word, course, the raw request text, the parsed
 * result, the planner's definitive room, the assigned room, the reason when it was not satisfied, and where
 * the row came from. Term groups collapse with a container FLIP (≤ 40 items, motion.md §3.9); the first load
 * is static (history, nothing performs).
 */
import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { HistoryItem, HistoryTerm } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { isUnsatisfied, pairText, placeText, reasonText, requestedText } from "./moderation-model";
import { PriorityPopover } from "./priority-editor";
import { VerdictBadge } from "./verdict-badge";
import { WishStatusBadge } from "./my-wishes";

const LAYOUT_MAX = 40;

function parsedText(it: HistoryItem, lang: "tr" | "en"): string {
  const p = it.parsed;
  const days = p.day ? [p.day] : (p.days ?? []);
  const parts = [
    days.length ? days.map((d) => dayName(d, lang, "short")).join("/") : null,
    p.start_time && p.end_time ? `${p.start_time.slice(0, 5)}–${p.end_time.slice(0, 5)}` : p.start_period ? `P${p.start_period}${p.end_period && p.end_period !== p.start_period ? `–P${p.end_period}` : ""}` : null,
    p.rooms?.length ? p.rooms.join(" / ") : null,
    p.building ? `${p.building} blok` : null,
    p.tags?.length ? p.tags.join(", ") : null,
    p.capacity ? `≥ ${p.capacity}` : null,
  ].filter(Boolean);
  return parts.join(" · ") || "—";
}

export function TimelineRow({ it, termId, canEdit }: { it: HistoryItem; termId: number; canEdit: boolean }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const name = `${it.label}, ${pairText(it.verdict_text, lang)}`;
  return (
    <li aria-label={name} className="flex flex-col gap-0.5 border-b border-hairline py-2 last:border-b-0" data-testid="timeline-row" data-verdict={it.verdict}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <VerdictBadge verdict={it.verdict} text={it.verdict_text} planner={it.source === "planner"} />
        <span className="type-callout font-semibold">{it.label}</span>
        {it.course_name ? <span className="type-footnote text-label-2">{it.course_name}</span> : null}
        <span className="ml-auto">
          <PriorityPopover disabled={!canEdit} target={{ termId, requestId: it.request_id, sectionId: it.section_id, label: it.label, priority: it.priority }} />
        </span>
      </div>
      <p className="type-footnote text-label-1">
        {requestedText(it, lang)} → {it.assigned ? placeText(it.assigned, lang) : t("moderation.timeline.notAssigned")}
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 type-footnote text-label-2">
        <dt>{t("moderation.timeline.raw")}</dt>
        <dd>{it.raw.room_text ? `“${it.raw.room_text}”` : "—"}{it.raw.notes ? ` · ${it.raw.notes}` : ""}</dd>
        <dt>{t("moderation.timeline.parsed")}</dt>
        <dd>{parsedText(it, lang)}{it.parsed.warnings?.length ? ` · ⚠ ${it.parsed.warnings.join("; ")}` : ""}</dd>
        <dt>{t("moderation.timeline.definitive")}</dt>
        <dd>{it.definitive.rooms.length ? it.definitive.rooms.join(" + ") : (it.definitive.text ?? "—")}</dd>
        <dt>{t("moderation.timeline.assigned")}</dt>
        <dd>{it.assigned?.rooms.length ? it.assigned.rooms.join(" + ") : "—"}</dd>
      </dl>
      {it.reason && (isUnsatisfied(it.verdict) || it.reason.code === "planner_decision") ? (
        <p className="type-footnote text-label-2">
          <span className="font-semibold">{t("moderation.timeline.reason")}:</span> {reasonText(it.reason, lang)}
          {it.reason.policy_step ? ` (${pairText(it.reason.policy_step.text, lang)})` : ""}
          {it.reason.culprits.length ? ` · ${it.reason.culprits.map((c) => c.label).join(", ")}` : ""}
        </p>
      ) : null}
      {it.teacher_preferences.length ? (
        <ul className="flex flex-col gap-0.5" aria-label={t("moderation.inspector.wishes")} data-testid="timeline-wishes">
          {it.teacher_preferences.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-1.5 type-footnote text-label-2">
              <WishStatusBadge status={w.status} />
              <span className="min-w-0">{pairText(w.text, lang)}{w.status === "rejected" && w.reason ? ` · ${t("moderation.review.decidedReason", { reason: w.reason })}` : ""}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="type-caption text-label-3">
        {it.raw.row ? t("moderation.provenance", { row: it.raw.row }) : t("moderation.manual")}
        {it.planner_edits.length ? ` · ${t("moderation.timeline.edits", { n: it.planner_edits.length })}` : ""}
      </p>
    </li>
  );
}

export function TermGroup({ g, canEdit, defaultOpen = true }: { g: HistoryTerm; canEdit: boolean; defaultOpen?: boolean }) {
  const { t, n } = useI18n();
  const reduce = useReduce();
  const [open, setOpen] = useState(defaultOpen);
  const id = `term-${g.term_id}`;
  const animate = !reduce && g.items.length <= LAYOUT_MAX;
  const src = g.run ? (g.run.published ? t("moderation.timeline.published", { label: g.run.label ?? `#${g.run.id}` }) : t("moderation.timeline.run", { id: g.run.id })) : t("moderation.timeline.plannerOnly");
  const met = g.counts.satisfied ?? 0;
  const judged = met + (g.counts.partial ?? 0) + (g.counts.not_as_requested ?? 0) + (g.counts.unplaced ?? 0);
  return (
    <motion.section layout={animate ? "position" : false} transition={springs.smooth} aria-labelledby={id} className="flex flex-col" data-testid="term-group">
      <div className="flex items-center gap-2 border-b border-hairline pb-1">
        <h3 id={id} className="type-headline">{g.term_code}</h3>
        <span className="type-footnote text-label-2">{src}</span>
        {judged ? <span className="type-footnote text-label-2 tabular-nums">· {t("moderation.timeline.met", { met: n(met), of: n(judged) })}</span> : null}
        <Button variant="ghost" size="icon-xs" className="ml-auto" aria-expanded={open} aria-controls={`${id}-list`} aria-label={t(open ? "moderation.timeline.collapse" : "moderation.timeline.expand", { term: g.term_code })} onClick={() => setOpen((o) => !o)}>
          <ChevronDown className={cn("transition-transform duration-(--dur-fast)", !open && "-rotate-90")} aria-hidden />
        </Button>
      </div>
      {open ? (
        <motion.ol id={`${id}-list`} layout={animate} initial={animate ? { opacity: 0 } : false} animate={{ opacity: 1 }} transition={animate ? { ...springs.smooth, opacity: { duration: 0.12, delay: 0.06 } } : { duration: 0 }}>
          {g.items.length ? g.items.map((it) => <TimelineRow key={it.request_id} it={it} termId={g.term_id} canEdit={canEdit} />) : <li className="py-2 type-footnote text-label-2">{t("moderation.timeline.noRequests")}</li>}
        </motion.ol>
      ) : null}
    </motion.section>
  );
}

export function RequestTimeline({ terms, canEdit }: { terms: readonly HistoryTerm[]; canEdit: boolean }) {
  const { t } = useI18n();
  if (!terms.length) return <p className="type-callout text-label-2">{t("moderation.timeline.empty")}</p>;
  return (
    <div className="flex flex-col gap-6" data-testid="request-timeline">
      {terms.map((g, i) => <TermGroup key={g.term_id} g={g} canEdit={canEdit} defaultOpen={i < 2} />)}
    </div>
  );
}

/** "N dönemdir karşılanmadı" (Q6, backend `_streak`): terms in a row, newest first, with an unsatisfied request;
 *  a term without requests neither counts nor breaks the run */
export function unsatisfiedStreak(terms: readonly HistoryTerm[]): number {
  let streak = 0;
  for (const g of terms) {
    if (!g.items.length) continue;
    if (g.items.some((i) => isUnsatisfied(i.verdict))) streak++;
    else break;
  }
  return streak;
}
