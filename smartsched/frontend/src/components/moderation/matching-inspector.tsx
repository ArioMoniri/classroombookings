"use client";
/**
 * The matching inspector (moderation spec §5.1 right column): what was asked, what was assigned, the verdict
 * per wish (room / building / features / day / time) as ✓ / ✕ words, the reason with its policy step and the
 * winners, the priority editor, and links to the people. Opens from any moderation table (Enter, click).
 */
import { Check, Minus, UserRound, X } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMatching, type Matching } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { pairText, placeText, reasonText, requestedText } from "./moderation-model";
import { PriorityForm } from "./priority-editor";
import { VerdictBadge } from "./verdict-badge";

const FLAGS = ["room", "building", "tags", "day", "period"] as const;

export function FlagList({ m }: { m: Matching }) {
  const { t } = useI18n();
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={t("moderation.inspector.flags")}>
      {FLAGS.map((f) => {
        const v = m.satisfied[f];
        const Icon = v === true ? Check : v === false ? X : Minus;
        return (
          <li key={f} className="inline-flex items-center gap-1 type-footnote text-label-2">
            <Icon className={v === true ? "size-3.5 text-status-feasible-fg" : v === false ? "size-3.5 text-status-infeasible-fg" : "size-3.5 text-label-3"} aria-hidden />
            <span>
              {t(`moderation.flag.${f}` as MessageKey)}: {v === true ? t("moderation.flag.met") : v === false ? t("moderation.flag.unmet") : t("moderation.flag.none")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1 border-t border-hairline pt-3">
      <h3 className="type-footnote font-semibold text-label-2">{title}</h3>
      {children}
    </section>
  );
}

export function MatchingInspector({ termId, requestId, runId, canEdit, siblings, onClose, side = "right" }: { termId: number; requestId: number | null; runId?: number | null; canEdit: boolean; siblings?: (sectionId: number) => number[]; onClose: () => void; side?: "right" | "bottom" }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const q = useMatching(termId, requestId, runId);
  const m = q.data;
  return (
    <Sheet open={requestId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side={side} className="gap-0 overflow-y-auto p-5 sm:max-w-md" data-testid="matching-inspector">
        <SheetHeader className="p-0 pb-3">
          <SheetTitle>{m?.label ?? t("moderation.inspector.title")}</SheetTitle>
          <SheetDescription>{m ? [m.course_name, m.program, m.enrolment !== null ? t("moderation.students", { n: m.enrolment }) : null].filter(Boolean).join(" · ") : t("busy.loading")}</SheetDescription>
        </SheetHeader>
        {q.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : q.isError || !m ? (
          <p role="alert" className="type-callout text-label-2">{t("moderation.inspector.error")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictBadge verdict={m.verdict} text={m.verdict_text} planner={m.source === "planner"} />
            </div>
            <Section title={t("moderation.inspector.requested")}>
              <p className="type-callout">{requestedText(m, lang)}</p>
              {m.requested.room_text ? <p className="type-footnote text-label-2">{t("moderation.timeline.raw")}: “{m.requested.room_text}”</p> : null}
              {m.definitive.rooms.length ? <p className="type-footnote text-label-2">{t("moderation.timeline.definitive")}: {m.definitive.rooms.join(" + ")}</p> : null}
              {m.provenance.row ? <p className="type-caption text-label-3">{t("moderation.provenance", { row: m.provenance.row })}</p> : null}
            </Section>
            <Section title={t("moderation.inspector.assigned")}>
              <p className="type-callout">{m.assigned ? placeText(m.assigned, lang) : "—"}</p>
              <FlagList m={m} />
            </Section>
            {m.reason ? (
              <Section title={t("moderation.inspector.reason")}>
                <p className="type-callout">{reasonText(m.reason, lang)}</p>
                {m.reason.policy_step ? <p className="type-footnote text-label-2">{t("moderation.policyStep")}: {pairText(m.reason.policy_step.text, lang)}</p> : null}
                {m.reason.culprits.length ? (
                  <p className="type-footnote text-label-2">
                    {t("moderation.inspector.winners")}: {m.reason.culprits.map((c) => [c.label, c.room].filter(Boolean).join(" · ")).join(", ")}
                  </p>
                ) : null}
              </Section>
            ) : null}
            <Section title={t("moderation.priority.label")}>
              {canEdit ? (
                <PriorityForm key={m.request_id} target={{ termId, requestId: m.request_id, sectionId: m.section_id, label: m.label, priority: m.priority, sectionRequestIds: siblings?.(m.section_id) }} />
              ) : (
                <p className="type-callout">{t(`moderation.tier.${m.priority.value > 0 ? "high" : m.priority.value < 0 ? "low" : "normal"}`)}</p>
              )}
            </Section>
            {m.instructors.length ? (
              <Section title={t("moderation.inspector.people")}>
                <div className="flex flex-wrap gap-2">
                  {m.instructors.map((i) => (
                    <Button key={i.id} size="sm" variant="secondary" render={<Link href={`/moderation/people/${i.id}`} />} nativeButton={false}>
                      <UserRound aria-hidden />
                      {i.name}
                    </Button>
                  ))}
                </div>
              </Section>
            ) : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
