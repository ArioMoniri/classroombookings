"use client";
/**
 * /moderation/people/[id] (moderation spec §5.2): "what does this academician usually ask for, and did they get
 * it?". Header facts, the "N dönemdir karşılanmadı" badge, learned habits (max 3, with their evidence), the
 * suggestion cards for this person (never applied by themselves), and the term-grouped request timeline. An
 * admin can reset what was learned about the person from the ⋯ menu. Viewers get the same page read-only.
 */
import { ArrowLeft, Ellipsis, History } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { ResetDialog } from "@/components/learning/reset-dialog";
import { SuggestionList } from "@/components/learning/suggestion-list";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { HttpError } from "@/lib/api/client";
import { useHistory, usePriorities } from "@/lib/api/moderation";
import { useSuggestions } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { pairText, tierOf } from "./moderation-model";
import { SubjectPriorityForm } from "./priority-editor";
import { RequestTimeline, unsatisfiedStreak } from "./request-timeline";

/** "Kişi önceliği" for the profile's term: inherited by the person's requests without a more specific value */
function PersonPriority({ termId, termCode, instructorId, label }: { termId: number; termCode: string; instructorId: number; label: string }) {
  const { t } = useI18n();
  const q = usePriorities(termId, "person");
  const o = q.data?.items.find((x) => x.subject_id === instructorId);
  return (
    <section aria-labelledby="person-priority-title" className="flex flex-col gap-1 border-t border-hairline pt-3">
      <h2 id="person-priority-title" className="type-headline">{t("moderation.subjectPriority.profileTitle", { term: termCode })}</h2>
      {o?.updated_at ? <p className="type-caption text-label-3">{t("moderation.subjectPriority.current", { tier: t(`moderation.tier.${tierOf(o.priority)}`) })}</p> : null}
      {q.data ? <SubjectPriorityForm subject="person" id={instructorId} termId={termId} label={label} current={o?.priority ?? null} note={o?.note} /> : null}
    </section>
  );
}

export function PersonProfile({ instructorId }: { instructorId: number }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const { can } = usePermissions();
  const canView = can("planning.view");
  const canEdit = can("planning.edit");
  const isAdmin = can("planning.admin");
  const q = useHistory(instructorId);
  const [tab, setTab] = useState<"timeline" | "suggestions">("timeline");
  const [reset, setReset] = useState<"person" | "erase" | null>(null);
  const terms = q.data?.terms ?? [];
  // the working term of the shell when the person has requests in it, else their newest term
  const working = useActiveTerm({ enabled: canView }).term?.id ?? null;
  const current = terms.find((g) => g.term_id === working) ?? terms[0];
  const sugg = useSuggestions(canView ? (current?.term_id ?? null) : null, instructorId);
  const openSugg = (sugg.data ?? []).filter((s) => s.state === "open").length;

  if (q.isError) {
    const forbidden = q.error instanceof HttpError && q.error.status === 403;
    const missing = q.error instanceof HttpError && q.error.status === 404;
    return (
      <EmptyState
        title={forbidden ? t("moderation.profile.forbiddenTitle") : missing ? t("moderation.profile.missingTitle") : t("moderation.loadError")}
        description={forbidden ? t("moderation.profile.forbidden") : missing ? t("moderation.profile.missing") : undefined}
        actions={<Button variant="outline" render={<Link href="/moderation?tab=people" />} nativeButton={false}>{t("moderation.profile.back")}</Button>}
      />
    );
  }
  if (!q.data) {
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  const ins = q.data.instructor;
  const streak = unsatisfiedStreak(terms);
  const habits = (current?.learned ?? []).filter((p) => p.explanation.tr || p.explanation.en).sort((a, b) => b.score - a.score).slice(0, 3);
  const judged = current ? (current.counts.satisfied ?? 0) + (current.counts.partial ?? 0) + (current.counts.not_as_requested ?? 0) + (current.counts.unplaced ?? 0) : 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]" data-testid="person-profile">
      <div className="flex min-w-0 flex-col gap-4">
        <Button variant="ghost" size="sm" className="self-start" render={<Link href={canView ? "/moderation?tab=people" : "/moderation"} />} nativeButton={false}>
          <ArrowLeft aria-hidden />
          {canView ? t("moderation.tabs.people") : t("moderation.mine.title")}
        </Button>
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="type-large-title" data-testid="profile-name">{[ins.title, ins.name].filter(Boolean).join(" ")}</h1>
            <p className="type-callout text-label-2">{t("moderation.profile.terms", { n: n(terms.length) })}</p>
          </div>
          {streak >= 2 ? (
            <span className="rounded-full bg-status-warning px-2.5 py-0.5 type-footnote font-semibold text-status-warning-fg" data-testid="profile-streak">
              ⚠ {t("moderation.profile.streak", { n: streak })}
            </span>
          ) : null}
          {isAdmin ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("moderation.profile.more")} />}>
                <Ellipsis aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setReset("person")}>{t("learning.reset.personAction")}</DropdownMenuItem>
                <DropdownMenuItem onClick={() => setReset("erase")}>{t("learning.erase.action")}</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
        {!canEdit && canView ? <p className="type-footnote text-label-2">{t("moderation.readOnly")}</p> : null}

        {canView ? (
          <section aria-labelledby="habits-title" className="flex flex-col gap-1">
            <h2 id="habits-title" className="type-headline">{t("moderation.profile.habits")}</h2>
            {habits.length ? (
              <ul className="flex flex-col gap-1" data-testid="habits">
                {habits.map((h) => (
                  <li key={h.id} className="flex items-start gap-2 type-callout">
                    <History className="mt-0.5 size-4 shrink-0 text-label-2" aria-hidden />
                    <span>
                      {pairText(h.explanation, lang)}
                      <span className="block type-caption text-label-3">{t("moderation.profile.habitEvidence", { k: h.terms_count, rows: h.support, total: h.total })}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="type-footnote text-label-2">{current?.learned === null ? t("moderation.profile.learningOff") : t("moderation.profile.noHabits")}</p>
            )}
          </section>
        ) : null}

        {canView && current ? (
          <SegmentedControl<"timeline" | "suggestions">
            aria-label={t("moderation.profile.tabs")}
            value={tab}
            onValueChange={setTab}
            size="sm"
            options={[
              { value: "timeline", label: t("moderation.profile.timeline") },
              { value: "suggestions", label: <span>{t("moderation.profile.suggestions")} <span className="tabular-nums text-label-3">{sugg.data ? n(openSugg) : "…"}</span></span> },
            ]}
          />
        ) : null}
        {tab === "suggestions" && current ? (
          <SuggestionList termId={current.term_id} personId={instructorId} canAct={canEdit} surface="moderation" />
        ) : (
          <>
            {canView && current && openSugg > 0 ? <SuggestionList termId={current.term_id} personId={instructorId} canAct={canEdit} surface="moderation" max={2} compact /> : null}
            <RequestTimeline terms={terms} canEdit={canEdit} />
          </>
        )}
      </div>

      <aside className="flex flex-col gap-2 lg:sticky lg:top-4 lg:self-start" aria-label={t("moderation.profile.facts")}>
        <h2 className="type-headline">{t("moderation.profile.facts")}</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 type-footnote">
          <dt className="text-label-2">{t("moderation.profile.thisTerm")}</dt>
          <dd>{current ? `${current.term_name || current.term_code} · ${t("moderation.profile.rows", { n: n(current.items.length) })}` : "—"}</dd>
          <dt className="text-label-2">{t("moderation.col.met")}</dt>
          <dd className="tabular-nums">{current ? `${n(current.counts.satisfied ?? 0)} / ${n(judged)}` : "—"}</dd>
          {/* R1-A-12: "Erişilebilirlik ihtiyacı: yok", not a bare "Erişilebilirlik: Hayır" */}
          <dt className="text-label-2">{t("moderation.profile.accessNeed")}</dt>
          <dd>{t(q.data.accessibility === "yes" ? "moderation.profile.accessYes" : "moderation.profile.accessNo")}</dd>
          <dt className="text-label-2">{t("moderation.profile.account")}</dt>
          <dd>{ins.linked_user ? t("moderation.profile.linked") : t("moderation.profile.unlinked")}</dd>
        </dl>
        {isAdmin && current ? <PersonPriority termId={current.term_id} termCode={current.term_code} instructorId={ins.id} label={[ins.title, ins.name].filter(Boolean).join(" ")} /> : null}
      </aside>
      {reset ? <ResetDialog open onOpenChange={(o) => !o && setReset(null)} scope={reset === "erase" ? "erase" : "person"} subject={{ id: ins.id, label: [ins.title, ins.name].filter(Boolean).join(" ") }} /> : null}
    </div>
  );
}
