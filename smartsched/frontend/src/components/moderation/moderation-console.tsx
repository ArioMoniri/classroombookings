"use client";
/**
 * /moderation (docs/design/v2/phase19-moderation.md §4–§5.1, motion.md §3.9): one console, five entity tabs
 * over the published plan of the working term: Sınıflar (the /classes table core), Kişiler, Talepler,
 * Tercihler, Eşleşmeler. The inspector opens from every table; "Planı yeniden oluştur" starts a minimal-change
 * re-solve whose preview is /moderation/recreate/[runId]. A user without planning.view sees "Taleplerim"
 * (their own requests, Q11) or a plain explanation when no instructor record is linked to the account.
 */
import { CircleDashed, RefreshCw, Search, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePhone } from "./use-media";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { useTermContext } from "@/components/timetable/use-calendar-data";
import { HttpError } from "@/lib/api/client";
import { useBookingContext } from "@/lib/api/crbs";
import { useMatchings, usePeople, usePreferences, type Matching, type PersonRow, type Preference } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { springs, tween, useReduce } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { useHydrated } from "@/lib/use-hydrated";
import { ClassesTab } from "./classes-tab";
import { MatchingInspector } from "./matching-inspector";
import { ModTable, type ModColumn } from "./mod-table";
import {
  MATCH_CHIPS,
  TABS,
  chipCount,
  filterMatchings,
  filterPeople,
  matchingSentence,
  pairText,
  parseTab,
  placeText,
  prefSource,
  reasonText,
  requestedText,
  sortMatchings,
  sortRequests,
  stagedRequestIds,
  termPreferences,
  unmetOf,
  type MatchChip,
  type ModerationTab,
  type PeopleChip,
} from "./moderation-model";
import { RecreateSheet } from "./recreate-sheet";
import { useStaged, useStagedStore } from "./staged-store";
import { SuggestionList } from "@/components/learning/suggestion-list";
import { TierLabel, VerdictBadge } from "./verdict-badge";

const typing = (el: EventTarget | null) => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || (el instanceof HTMLElement && el.isContentEditable);

export function ModerationConsole() {
  const { can, loading } = usePermissions();
  const hydrated = useHydrated();
  if (!hydrated || loading) return <ConsoleSkeleton />;
  return can("planning.view") ? <CoordinatorConsole canEdit={can("planning.edit")} /> : <MyRequests />;
}

function ConsoleSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy>
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-8 w-full max-w-xl" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

function StagedPopover({ termId, canEdit }: { termId: number; canEdit: boolean }) {
  const { t } = useI18n();
  const staged = useStaged(termId);
  const remove = useStagedStore((s) => s.remove);
  const reduce = useReduce();
  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="sm" data-testid="staged-link" />}>
        <CircleDashed aria-hidden />
        {/* the bump is the user's own edit only (motion.md §3.9 staged-count-bump); keyed on the count */}
        <motion.span key={staged.length} className="tabular-nums" initial={reduce ? false : { scale: 1.08 }} animate={{ scale: 1 }} transition={springs.bouncySubtle}>
          {t("moderation.staged.link", { count: staged.length })}
        </motion.span>
      </PopoverTrigger>
      <PopoverContent className="w-96" align="start">
        <p className="type-headline">{t("moderation.staged.title")}</p>
        {staged.length === 0 ? (
          <p className="type-footnote text-label-2">{t("moderation.staged.none")}</p>
        ) : (
          <ul className="flex max-h-72 flex-col gap-1 overflow-auto">
            {staged.map((c) => (
              <li key={c.at} className="flex items-center gap-2 type-footnote">
                <span className="min-w-0 flex-1">{c.label}</span>
                <Button variant="ghost" size="icon-xs" aria-label={t("moderation.staged.remove", { label: c.label })} onClick={() => remove(termId, c.at)}>
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {!canEdit ? <p className="type-caption text-label-3">{t("moderation.publishNeedsEdit")}</p> : null}
      </PopoverContent>
    </Popover>
  );
}

function CoordinatorConsole({ canEdit }: { canEdit: boolean }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const params = useSearchParams();
  const reduce = useReduce();
  const mobile = usePhone();
  const tab = parseTab(params.get("tab"));
  const { term, termId } = useTermContext();
  const matchings = useMatchings(termId);
  const people = usePeople(termId);
  const prefs = usePreferences(termId);
  const staged = useStaged(termId);
  const [query, setQuery] = useState("");
  const [chip, setChip] = useState<MatchChip>("unsatisfied");
  const [peopleChip, setPeopleChip] = useState<PeopleChip>("all");
  const [prefView, setPrefView] = useState<"rules" | "suggestions">("rules");
  const [inspect, setInspect] = useState<number | null>(null);
  const [recreate, setRecreate] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  /** the travel direction of the tab switch: content enters from the side of the new tab */
  const [dir, setDir] = useState(1);

  const setTab = useCallback(
    (next: ModerationTab) => {
      setDir(TABS.indexOf(next) >= TABS.indexOf(tab) ? 1 : -1);
      const sp = new URLSearchParams(params.toString());
      sp.set("tab", next);
      router.replace(`/moderation?${sp.toString()}`, { scroll: false });
      // focus lands on the first row, not on the page top (spec §7)
      window.requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-testid="mod-row"][tabindex="0"]')?.focus());
    },
    [params, router, tab],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (/^[1-5]$/.test(e.key)) {
        e.preventDefault();
        setTab(TABS[Number(e.key) - 1]!);
      } else if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "R" && e.shiftKey && canEdit) {
        e.preventDefault();
        setRecreate(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setTab, canEdit]);

  const items = useMemo(() => matchings.data?.items ?? [], [matchings.data]);
  const bySection = useMemo(() => {
    const m = new Map<number, number[]>();
    for (const it of items) m.set(it.section_id, [...(m.get(it.section_id) ?? []), it.request_id]);
    return m;
  }, [items]);
  const counts = matchings.data?.counts ?? {};
  const runId = matchings.data?.run_id ?? null;
  const prefRows = useMemo(() => termPreferences(prefs.data ?? []), [prefs.data]);

  const tabCount = (k: ModerationTab): string => {
    const v = k === "people" ? people.data?.total : k === "preferences" ? (prefs.data ? prefRows.length : undefined) : k === "matchings" ? (matchings.data ? chipCount(counts, "all") : undefined) : matchings.data?.total;
    return v === undefined ? "…" : n(v);
  };

  if (termId === null) {
    return (
      <>
        <PageHeader title={t("moderation.title")} />
        <ConsoleSkeleton />
      </>
    );
  }

  const header = (
    <PageHeader
      title={t("moderation.title")}
      subtitle={
        <>
          {term?.code ?? ""}
          {" · "}
          {matchings.data ? (runId ? t("moderation.publishedRun", { id: runId, rate: matchings.data.match_rate !== null ? Math.round(matchings.data.match_rate * 100) : "—" }) : t("moderation.noPublished")) : <Skeleton className="inline-block h-3 w-40 align-middle" />}
        </>
      }
      actions={
        <>
          <StagedPopover termId={termId} canEdit={canEdit} />
          {canEdit && runId ? (
            <Button variant={staged.length ? "default" : "outline"} onClick={() => setRecreate(true)} aria-keyshortcuts="Shift+R" data-testid="recreate-open">
              <RefreshCw aria-hidden />
              {t("moderation.recreate.open")}
            </Button>
          ) : null}
        </>
      }
    />
  );

  const errorBanner = (e: unknown, retry: () => void) => (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded-xl border border-status-warning-border bg-status-warning px-3 py-2 type-callout text-status-warning-fg">
      {e instanceof HttpError && e.status === 403 ? t("moderation.forbidden") : t("moderation.loadError")}
      <Button size="sm" variant="ghost" onClick={retry}>
        {t("common.retry")}
      </Button>
    </div>
  );

  const searchBox = (
    <label className="relative block w-full sm:w-72">
      <span className="sr-only">{t("moderation.search")}</span>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
      <Input ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("moderation.searchPh")} className="pl-8" aria-keyshortcuts="/" data-testid="moderation-search" />
    </label>
  );

  const open = (m: Matching) => setInspect(m.request_id);

  // ------------------------------------------------------------------ columns
  const personCols: ModColumn<PersonRow>[] = [
    { id: "name", header: t("moderation.col.person"), width: "minmax(14rem,2fr)", cell: (p) => (
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate">{[p.title, p.name].filter(Boolean).join(" ")}</span>
        {p.badge ? <span className="shrink-0 rounded-full bg-status-warning px-2 type-caption text-status-warning-fg" data-testid="streak-badge">{pairText(p.badge, lang)}</span> : null}
      </span>
    ) },
    { id: "unit", header: t("moderation.col.unit"), width: "minmax(10rem,1.4fr)", cell: (p) => p.unit ?? "—" },
    { id: "classes", header: t("moderation.col.classes"), width: "5rem", align: "end", cell: (p) => n(p.sections) },
    { id: "requests", header: t("moderation.col.requests"), width: "5rem", align: "end", cell: (p) => n(p.requests) },
    { id: "met", header: t("moderation.col.met"), width: "6.5rem", align: "end", cell: (p) => `${n(p.counts.satisfied ?? 0)} / ${n((p.counts.satisfied ?? 0) + unmetOf(p))}` },
    { id: "unmet", header: t("moderation.col.unmet"), width: "7rem", align: "end", cell: (p) => n(unmetOf(p)) },
    { id: "priority", header: t("moderation.col.priority"), width: "8rem", cell: (p) => <TierLabel value={p.priority_max} /> },
    { id: "prefs", header: t("moderation.col.prefs"), width: "6rem", align: "end", cell: (p) => n(p.active_preferences) },
    { id: "learned", header: t("moderation.col.learned"), width: "6.5rem", align: "end", cell: (p) => (p.learned_priors === null ? "—" : n(p.learned_priors)) },
    { id: "access", header: t("moderation.col.access"), width: "7rem", cell: (p) => t(p.accessibility === "yes" ? "common.yes" : "common.no") },
  ];
  const requestCols: ModColumn<Matching>[] = [
    { id: "status", header: t("moderation.col.reqStatus"), width: "9rem", cell: (m) => t(`moderation.reqStatus.${m.requested.status ?? "NEW"}` as MessageKey) },
    { id: "course", header: t("moderation.col.course"), width: "minmax(9rem,1fr)", cell: (m) => m.label },
    { id: "who", header: t("moderation.col.who"), width: "minmax(10rem,1.3fr)", cell: (m) => m.instructors.map((i) => i.name).join(", ") || "—" },
    { id: "asked", header: t("moderation.col.asked"), width: "minmax(14rem,2fr)", cell: (m) => <span title={requestedText(m, lang)}>{requestedText(m, lang)}</span> },
    { id: "students", header: t("moderation.col.students"), width: "5rem", align: "end", cell: (m) => (m.enrolment === null ? "—" : n(m.enrolment)) },
    { id: "priority", header: t("moderation.col.priority"), width: "10rem", cell: (m) => <TierLabel value={m.priority.value} source={m.priority.source} /> },
    { id: "source", header: t("moderation.col.source"), width: "7rem", cell: (m) => (m.provenance.row ? `R${m.provenance.row}` : t("moderation.manual")) },
  ];
  const matchCols: ModColumn<Matching>[] = [
    { id: "course", header: t("moderation.col.course"), width: "minmax(9rem,1fr)", cell: (m) => m.label },
    { id: "pair", header: t("moderation.col.pair"), width: "minmax(18rem,2.4fr)", cell: (m) => (
      <span aria-label={matchingSentence(m, lang)} title={matchingSentence(m, lang)}>
        {requestedText(m, lang)} → {m.assigned ? placeText(m.assigned, lang) : "—"}
      </span>
    ) },
    { id: "verdict", header: t("moderation.col.verdict"), width: "11rem", cell: (m) => <VerdictBadge verdict={m.verdict} text={m.verdict_text} planner={m.source === "planner"} /> },
    { id: "reason", header: t("moderation.col.reason"), width: "minmax(12rem,1.6fr)", cell: (m) => <span className="text-label-2" title={reasonText(m.reason, lang)}>{reasonText(m.reason, lang) || "—"}</span> },
    { id: "step", header: t("moderation.col.step"), width: "9rem", cell: (m) => (m.reason?.policy_step ? pairText(m.reason.policy_step.text, lang) : "—") },
    { id: "who", header: t("moderation.col.who"), width: "minmax(9rem,1fr)", cell: (m) => m.instructors.map((i) => i.name).join(", ") || "—" },
  ];
  const prefCols: ModColumn<Preference>[] = [
    { id: "text", header: t("moderation.col.pref"), width: "minmax(18rem,3fr)", cell: (p) => p.nl_text ?? p.kind },
    { id: "kind", header: t("moderation.col.kind"), width: "10rem", cell: (p) => p.kind },
    { id: "weight", header: t("moderation.col.weight"), width: "5.5rem", align: "end", cell: (p) => n(p.weight) },
    { id: "source", header: t("moderation.col.source"), width: "7rem", cell: (p) => t(`moderation.prefSource.${prefSource(p)}`) },
    { id: "enabled", header: t("moderation.col.active"), width: "7rem", cell: (p) => (p.enabled ? `✓ ${t("common.yes")}` : `✕ ${t("common.no")}`) },
  ];

  const matchCard = (m: Matching) => (
    <div className="flex flex-col gap-0.5 rounded-xl border border-hairline bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="type-headline">{m.label}</span>
        <VerdictBadge verdict={m.verdict} text={m.verdict_text} planner={m.source === "planner"} />
      </div>
      <span className="type-footnote text-label-2">{requestedText(m, lang)} → {m.assigned ? placeText(m.assigned, lang) : "—"}</span>
      {m.reason ? <span className="type-footnote text-label-2">{reasonText(m.reason, lang)}</span> : null}
    </div>
  );

  // ------------------------------------------------------------------ body per tab
  const loadingRows = (
    <div className="flex flex-col gap-1" aria-busy>
      {Array.from({ length: 12 }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );

  let body: React.ReactNode;
  if (tab === "classes") {
    body = <ClassesTab termId={termId} runId={runId} onOpen={setInspect} />;
  } else if (tab === "people") {
    const rows = filterPeople(people.data?.items ?? [], peopleChip, query);
    body = people.isError ? errorBanner(people.error, () => void people.refetch()) : !people.data ? loadingRows : (
      <>
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "unmet", "streak"] as const).map((c) => (
            <Chip key={c} selected={peopleChip === c} onSelectedChange={() => setPeopleChip(c)}>
              {t(`moderation.peopleChip.${c}`)}
            </Chip>
          ))}
          <span className="ml-auto">{searchBox}</span>
        </div>
        <ModTable
          rows={rows}
          columns={personCols}
          getId={(p) => p.id}
          caption={t("moderation.caption.people", { shown: n(rows.length), total: n(people.data.total) })}
          onOpen={(p) => router.push(`/moderation/people/${p.id}`)}
          mobile={mobile}
          card={(p) => (
            <div className="flex flex-col gap-0.5 rounded-xl border border-hairline bg-card p-3">
              <span className="type-headline">{[p.title, p.name].filter(Boolean).join(" ")}</span>
              <span className="type-footnote text-label-2">{p.unit ?? "—"} · {t("moderation.peopleCard", { met: n(p.counts.satisfied ?? 0), unmet: n(unmetOf(p)) })}</span>
              {p.badge ? <span className="type-footnote text-status-warning-fg">{pairText(p.badge, lang)}</span> : null}
            </div>
          )}
          testId="people-table"
          empty={<EmptyState size="sm" title={t("moderation.empty.people")} description={t("moderation.empty.peopleHint")} />}
        />
      </>
    );
  } else if (tab === "preferences") {
    body = (
      <>
        <SegmentedControl<"rules" | "suggestions">
          aria-label={t("moderation.tabs.preferences")}
          value={prefView}
          onValueChange={setPrefView}
          size="sm"
          options={[
            { value: "rules", label: t("moderation.prefView.rules") },
            { value: "suggestions", label: t("moderation.prefView.suggestions") },
          ]}
        />
        {prefView === "suggestions" ? (
          <SuggestionList termId={termId} canAct={canEdit} surface="moderation" />
        ) : prefs.isError ? (
          errorBanner(prefs.error, () => void prefs.refetch())
        ) : !prefs.data ? (
          loadingRows
        ) : (
          <ModTable rows={prefRows} columns={prefCols} getId={(p) => p.id} mobile={mobile} card={(p) => (
            <div className="flex flex-col gap-0.5 rounded-xl border border-hairline bg-card p-3">
              <span className="type-callout">{p.nl_text ?? p.kind}</span>
              <span className="type-footnote text-label-2">{t(`moderation.prefSource.${prefSource(p)}`)} · {t("moderation.col.weight")} {n(p.weight)} · {p.enabled ? `✓ ${t("common.yes")}` : `✕ ${t("common.no")}`}</span>
            </div>
          )} caption={t("moderation.caption.prefs", { n: n(prefRows.length) })} testId="prefs-table" empty={<EmptyState size="sm" title={t("moderation.empty.prefs")} description={t("moderation.empty.prefsHint")} actions={<Button size="sm" variant="outline" render={<Link href="/generate?step=rules" />} nativeButton={false}>{t("moderation.empty.prefsAction")}</Button>} />} />
        )}
      </>
    );
  } else {
    const isMatch = tab === "matchings";
    const rows = isMatch ? sortMatchings(filterMatchings(items, chip, query)) : sortRequests(filterMatchings(items, "all", query));
    body = matchings.isError ? errorBanner(matchings.error, () => void matchings.refetch()) : !matchings.data ? loadingRows : (
      <>
        <div className="flex flex-wrap items-center gap-2">
          {isMatch
            ? MATCH_CHIPS.map((c) => (
                <Chip key={c} selected={chip === c} onSelectedChange={() => setChip(c)} data-testid={`chip-${c}`}>
                  {t(`moderation.chip.${c}`)} <span className="tabular-nums">{n(chipCount(counts, c))}</span>
                </Chip>
              ))
            : null}
          <span className="ml-auto">{searchBox}</span>
        </div>
        {isMatch && !runId ? <p className="type-footnote text-label-2">{t("moderation.plannerOnly")}</p> : null}
        <ModTable
          rows={rows}
          columns={isMatch ? matchCols : requestCols}
          getId={(m) => m.request_id}
          activeId={inspect}
          caption={t(isMatch ? "moderation.caption.matchings" : "moderation.caption.requests", { shown: n(rows.length), total: n(items.length) })}
          onOpen={open}
          onKey={(key, m, e) => {
            if (key === "p" || key === "e") {
              open(m);
              return true;
            }
            if (key === "Enter" && e.shiftKey && m.instructors[0]) {
              router.push(`/moderation/people/${m.instructors[0].id}`);
              return true;
            }
            return false;
          }}
          mobile={mobile}
          card={matchCard}
          testId={isMatch ? "matchings-table" : "requests-table"}
          empty={<EmptyState size="sm" title={t(isMatch ? "moderation.empty.matchings" : "moderation.empty.requests")} description={t("moderation.empty.filterHint")} />}
        />
      </>
    );
  }

  return (
    <div className="flex flex-col gap-3" data-testid="moderation-console">
      {header}
      {!canEdit ? <p className="type-footnote text-label-2">{t("moderation.readOnly")}</p> : null}
      <div className="overflow-x-auto">
        <SegmentedControl<ModerationTab>
          aria-label={t("moderation.tabsLabel")}
          value={tab}
          onValueChange={setTab}
          options={TABS.map((k) => ({ value: k, label: <span className="whitespace-nowrap">{t(`moderation.tabs.${k}`)} <span className="tabular-nums text-label-3">{tabCount(k)}</span></span>, controls: "moderation-panel" }))}
        />
      </div>
      {/* moderation.tab-switch: enter-only content, 8 px toward the tab's side, no stagger (motion.md §3.9) */}
      <motion.div
        key={tab}
        id="moderation-panel"
        role="tabpanel"
        className="flex flex-col gap-3"
        initial={reduce ? { opacity: 0 } : { opacity: 0, x: 8 * dir }}
        animate={{ opacity: 1, x: 0 }}
        transition={reduce ? tween.reduced : springs.smooth}
      >
        {body}
      </motion.div>
      <MatchingInspector termId={termId} requestId={inspect} canEdit={canEdit} siblings={(s) => bySection.get(s) ?? []} onClose={() => setInspect(null)} side={mobile ? "bottom" : "right"} />
      {canEdit && runId ? <RecreateSheet open={recreate} onOpenChange={setRecreate} termId={termId} baseRunId={runId} staged={stagedRequestIds(staged)} side={mobile ? "bottom" : "right"} /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ Taleplerim (Q11: own requests only) */

/** the instructor id common to every own request (the scope the backend applied) */
export function ownInstructorId(items: readonly Matching[]): number | null {
  if (!items.length) return null;
  let ids = new Set(items[0]!.instructors.map((i) => i.id));
  for (const it of items.slice(1)) ids = new Set(it.instructors.map((i) => i.id).filter((i) => ids.has(i)));
  return ids.size ? [...ids][0]! : null;
}

function MyRequests() {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  // GET /terms is planning data: an academician's term comes from the booking context (current session)
  const ctx = useBookingContext();
  const session = ctx.data ? (ctx.data.sessions.find((s) => s.id === ctx.data?.current_term_id) ?? ctx.data.sessions.find((s) => s.is_current) ?? ctx.data.sessions[0]) : undefined;
  // the session list hides unselectable terms from a teacher; the current term id still names the term
  const termId = ctx.data?.current_term_id ?? session?.id ?? null;
  const term = session ?? (termId !== null ? { code: "" } : undefined);
  const q = useMatchings(termId);
  const mobile = usePhone();
  const forbidden = q.error instanceof HttpError && q.error.status === 403;
  const items = sortMatchings(q.data?.items ?? []);
  const me = ownInstructorId(items);
  return (
    <div className="flex flex-col gap-3" data-testid="my-requests">
      <PageHeader title={t("moderation.mine.title")} subtitle={term?.code} actions={me ? <Button variant="outline" render={<Link href={`/moderation/people/${me}`} />} nativeButton={false}>{t("moderation.mine.history")}</Button> : null} />
      {forbidden ? (
        <EmptyState data-testid="mine-unlinked" title={t("moderation.mine.unlinkedTitle")} description={t("moderation.mine.unlinked")} />
      ) : q.isError ? (
        <p role="alert" className="type-callout text-label-2">{t("moderation.loadError")}</p>
      ) : ctx.data && termId === null ? (
        <EmptyState title={t("moderation.mine.emptyTitle")} description={t("moderation.mine.noTerm")} />
      ) : !q.data ? (
        <ConsoleSkeleton />
      ) : items.length === 0 ? (
        <EmptyState title={t("moderation.mine.emptyTitle")} description={t("moderation.mine.empty", { term: term?.code ?? "" })} />
      ) : (
        <ModTable
          rows={items}
          columns={[
            { id: "course", header: t("moderation.col.course"), width: "minmax(9rem,1fr)", cell: (m) => m.label },
            { id: "pair", header: t("moderation.col.pair"), width: "minmax(18rem,2.4fr)", cell: (m) => `${requestedText(m, lang)} → ${m.assigned ? placeText(m.assigned, lang) : "—"}` },
            { id: "verdict", header: t("moderation.col.verdict"), width: "11rem", cell: (m) => <VerdictBadge verdict={m.verdict} text={m.verdict_text} planner={m.source === "planner"} /> },
            { id: "reason", header: t("moderation.col.reason"), width: "minmax(12rem,2fr)", cell: (m) => reasonText(m.reason, lang) || "—" },
          ]}
          getId={(m) => m.request_id}
          caption={t("moderation.caption.mine", { n: n(items.length) })}
          mobile={mobile}
          card={(m) => (
            <div className="flex flex-col gap-0.5 rounded-xl border border-hairline bg-card p-3">
              <div className="flex items-center justify-between gap-2"><span className="type-headline">{m.label}</span><VerdictBadge verdict={m.verdict} text={m.verdict_text} /></div>
              <span className="type-footnote text-label-2">{requestedText(m, lang)} → {m.assigned ? placeText(m.assigned, lang) : "—"}</span>
            </div>
          )}
          testId="mine-table"
        />
      )}
    </div>
  );
}
