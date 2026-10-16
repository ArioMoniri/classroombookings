"use client";
/**
 * The coordinator's "Akademisyen tercihleri" (P19-T2; owner: moderate each person's requests and preferences from
 * the admin panel, never auto-applied): the term's academician wishes from
 * `GET /terms/{id}/moderation/teacher-preferences?status=all`, pending first, with counts per status. One card per
 * submission: the classes, the person, the wish, what the department asked first ("bölüm odasından sonra"), the
 * note; "Kabul et" switches the rule on for the next solve, "Reddet" needs a written reason (≥ 3 characters, the
 * academician reads it) and an optional reason code. `with_submission` decides every rule of the submission at
 * once unless the coordinator narrows it to one rule.
 */
import { Check, Search, X } from "lucide-react";
import { useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useDecideWish, useTermTeacherPreferences, wishError, type DecideOut, type TeacherPref } from "@/lib/api/teacher-preferences";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { pairText } from "./moderation-model";
import { useDateText, WishStatusBadge } from "./my-wishes";
import { ResponsiveDialog } from "./responsive-dialog";
import { REASON_MAX, REASON_MIN, REJECT_CODES, departmentAsk, filterGroups, groupWishes, isKnownError, isRejectCode, type ReviewFilter, type WishGroup } from "./wish-model";

const FILTERS: readonly ReviewFilter[] = ["pending", "accepted", "rejected", "all"];

/** "Yumuşak kural · bölüm odasından sonra" for an accepted wish (it ranks below the department's own ask) */
export function softRuleKey(kind: string): MessageKey {
  return kind === "room_preference" ? "moderation.review.softRuleRoom" : kind === "building_preference" ? "moderation.review.softRuleBuilding" : "moderation.review.softRule";
}

function decideText(e: unknown, t: (k: MessageKey) => string, lang: "tr" | "en"): string {
  const err = wishError(e);
  if (err && isKnownError(err.code)) return t(`moderation.wish.err.${err.code}` as MessageKey);
  if (err) return (lang === "tr" ? err.message_tr : err.message) || err.message;
  return e instanceof Error ? e.message : String(e);
}

/**
 * Kabul et / Reddet for one submission (the review card and the matching inspector). `onDecided` gets the
 * server's answer (`notified`, `effective`).
 */
export function DecideControls({ group, onDecided, compact = false }: { group: WishGroup; onDecided?: (out: DecideOut) => void; compact?: boolean }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const decide = useDecideWish();
  const pendingRows = group.items.filter((i) => i.status === "pending");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [onlyThis, setOnlyThis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState(false);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const ids = useId();
  const label = group.labels.slice(0, 3).join(", ") + (group.labels.length > 3 ? " …" : "");
  const head = pendingRows[0];
  if (!head) return null;
  const several = pendingRows.length > 1;

  const done = (out: DecideOut) => {
    toast.success(`${t(out.decision === "accept" ? "moderation.review.accepted" : "moderation.review.rejected")} ${t(out.notified ? "moderation.review.notified" : "moderation.review.notNotified")}`);
    onDecided?.(out);
  };
  const accept = async () => {
    setError(null);
    try {
      done(await decide.mutateAsync({ id: head.id, body: { decision: "accept", with_submission: !onlyThis } }));
    } catch (e) {
      setError(decideText(e, t, lang));
    }
  };
  const reject = async () => {
    setTried(true);
    setError(null);
    if (reason.trim().length < REASON_MIN) {
      reasonRef.current?.focus();
      return;
    }
    try {
      const out = await decide.mutateAsync({ id: head.id, body: { decision: "reject", reason: reason.trim(), reason_code: code || undefined, with_submission: !onlyThis } });
      setRejecting(false);
      done(out);
    } catch (e) {
      setError(decideText(e, t, lang));
    }
  };
  const short = tried && reason.trim().length < REASON_MIN;

  return (
    <div className="flex flex-col gap-2">
      {several ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="type-caption font-semibold text-label-2">{t("moderation.review.scope")}</legend>
          <div className="flex flex-wrap gap-2">
            <Chip size="sm" className="pointer-coarse:h-11" selected={!onlyThis} onSelectedChange={() => setOnlyThis(false)} data-testid="decide-scope-all">{t("moderation.review.scopeAll", { n: n(pendingRows.length) })}</Chip>
            <Chip size="sm" className="pointer-coarse:h-11" selected={onlyThis} onSelectedChange={() => setOnlyThis(true)} data-testid="decide-scope-one">{t("moderation.review.scopeOne")}</Chip>
          </div>
        </fieldset>
      ) : null}
      <div className={cn("flex flex-wrap gap-2", compact && "justify-end")}>
        <Button size="sm" className="max-md:h-11 max-md:flex-1" onClick={() => void accept()} disabled={decide.isPending} aria-label={t("moderation.review.acceptLabel", { label })} data-testid="wish-accept">
          <Check aria-hidden />
          {t("moderation.review.accept")}
        </Button>
        <Button size="sm" variant="outline" className="max-md:h-11 max-md:flex-1" onClick={() => (setRejecting(true), setTried(false), setError(null))} disabled={decide.isPending} aria-label={t("moderation.review.rejectLabel", { label })} data-testid="wish-reject">
          <X aria-hidden />
          {t("moderation.review.reject")}
        </Button>
      </div>
      {error && !rejecting ? <Alert tone="error" data-testid="decide-error">{error}</Alert> : null}
      <ResponsiveDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title={t("moderation.review.rejectTitle", { label })}
        description={t("moderation.review.rejectBody")}
        initialFocus={reasonRef}
        testId="wish-reject-dialog"
        footer={
          <>
            <Button variant="ghost" className="max-md:h-11" onClick={() => setRejecting(false)}>{t("common.cancel")}</Button>
            <Button variant="destructive" className="max-md:h-11" onClick={() => void reject()} disabled={decide.isPending} aria-busy={decide.isPending || undefined} data-testid="wish-reject-confirm">
              {decide.isPending ? t("busy.rejecting") : t("moderation.review.reject")}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="rounded-lg bg-fill-3 px-3 py-2 type-callout">{pairText(head.text, lang)}</p>
          <div className="flex flex-col gap-1">
            <label htmlFor={`${ids}-code`} className="type-footnote font-semibold text-label-2">{t("moderation.review.codeLabel")}</label>
            <NativeSelect id={`${ids}-code`} value={code} onChange={(e) => setCode(e.target.value)} selectClassName="max-md:pointer-coarse:text-base" data-testid="wish-reject-code">
              <option value="">{t("moderation.review.codeNone")}</option>
              {REJECT_CODES.map((c) => (
                <option key={c} value={c}>{t(`moderation.review.codes.${c}`)}</option>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={`${ids}-reason`} className="type-footnote font-semibold text-label-2">{t("moderation.review.reasonLabel")}</label>
            <Textarea
              ref={reasonRef}
              id={`${ids}-reason`}
              rows={3}
              required
              maxLength={REASON_MAX}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("moderation.review.reasonPh")}
              aria-invalid={short || undefined}
              aria-describedby={`${ids}-reason-help`}
              data-testid="wish-reject-reason"
            />
            <span id={`${ids}-reason-help`} className={cn("flex justify-between gap-2 type-caption", short ? "text-status-infeasible-fg" : "text-label-3")}>
              <span>{short ? t("moderation.review.reasonShort", { n: REASON_MIN }) : ""}</span>
              <span>{t("moderation.review.reasonCount", { n: n(reason.trim().length), max: n(REASON_MAX) })}</span>
            </span>
          </div>
          {error ? <Alert tone="error" data-testid="decide-error">{error}</Alert> : null}
        </div>
      </ResponsiveDialog>
    </div>
  );
}

export function WishCard({ group, canEdit }: { group: WishGroup; canEdit: boolean }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const date = useDateText();
  const head = group.items[0]!;
  const ask = departmentAsk(head);
  const decided = group.items.find((i) => i.status !== "pending");
  return (
    <li className="flex flex-col gap-1.5 rounded-xl bg-card p-3 edge-hairline" data-testid="wish-card" data-status={group.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 type-headline">{group.labels.slice(0, 4).join(", ")}{group.labels.length > 4 ? " …" : ""}</span>
        <WishStatusBadge status={group.status} />
      </div>
      <span className="type-footnote text-label-2">
        {[head.instructor?.name ? `${t("moderation.review.who")}: ${head.instructor.name}` : null, pairText(head.kind_label, lang), group.submittedAt ? t("moderation.wish.submittedAt", { date: date(group.submittedAt) }) : null].filter(Boolean).join(" · ")}
      </span>
      {group.items.map((it: TeacherPref) => (
        <p key={it.id} className="type-callout">
          {pairText(it.text, lang)}
          {it.status === "accepted" ? <span className="block type-footnote text-status-feasible-fg" data-testid="wish-soft-rule">{t(softRuleKey(it.kind))}</span> : null}
        </p>
      ))}
      <p className="type-footnote text-label-2">{ask.length ? t("moderation.review.deptFirst", { ask: ask.join(", ") }) : head.kind === "day_window" ? t("moderation.wish.rank") : t("moderation.review.deptNone")}</p>
      {group.items.length > 1 ? <p className="type-caption text-label-3">{t("moderation.review.rules", { n: n(group.items.length) })}</p> : null}
      {head.note ? <p className="type-footnote text-label-2">{t("moderation.review.note")}: “{head.note}”</p> : null}
      {group.status === "rejected" && decided?.reason ? (
        <p className="type-footnote text-status-infeasible-fg">{t("moderation.review.decidedReason", { reason: `${isRejectCode(decided.reason_code) ? `${t(`moderation.review.codes.${decided.reason_code}`)}: ` : ""}${decided.reason}` })}</p>
      ) : null}
      {decided?.decided_at ? <span className="type-caption text-label-3">{t("moderation.wish.decidedAt", { date: date(decided.decided_at) })}</span> : null}
      {canEdit && group.status === "pending" ? <DecideControls group={group} /> : null}
    </li>
  );
}

export function TeacherWishesReview({ termId, canEdit }: { termId: number; canEdit: boolean }) {
  const { t, n } = useI18n();
  const q = useTermTeacherPreferences(termId);
  const [filter, setFilter] = useState<ReviewFilter>("pending");
  const [query, setQuery] = useState("");
  const groups = useMemo(() => groupWishes(q.data?.items ?? []), [q.data]);
  const counts: Record<ReviewFilter, number> = {
    pending: groups.filter((g) => g.status === "pending").length,
    accepted: groups.filter((g) => g.status === "accepted").length,
    rejected: groups.filter((g) => g.status === "rejected").length,
    all: groups.length,
  };
  const shown = filterGroups(groups, filter, query);
  return (
    <section className="flex flex-col gap-3" aria-labelledby="teacher-wishes-title" data-testid="teacher-wishes">
      <div className="flex flex-col gap-1">
        <h2 id="teacher-wishes-title" className="type-title-3">{t("moderation.review.title")}</h2>
        <p className="max-w-3xl type-footnote text-label-2">{t("moderation.review.lead")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("moderation.review.filterLabel")} className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <Chip key={f} className="pointer-coarse:h-11" selected={filter === f} onSelectedChange={() => setFilter(f)} data-testid={`wish-filter-${f}`}>
              {t(`moderation.review.filter.${f}`)} <span className="tabular-nums">{n(counts[f])}</span>
            </Chip>
          ))}
        </div>
        <label className="relative ml-auto block w-full sm:w-64">
          <span className="sr-only">{t("moderation.search")}</span>
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
          <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("moderation.review.searchPh")} className="pl-8" data-testid="wish-search" />
        </label>
      </div>
      {q.isLoading ? (
        <div className="flex flex-col gap-2" aria-busy>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : q.isError ? (
        <Alert tone="error" action={<Button size="sm" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>}>{t("moderation.review.loadError")}</Alert>
      ) : shown.length === 0 ? (
        <EmptyState size="sm" title={t(`moderation.review.empty.${filter}`)} description={t("moderation.review.emptyHint")} data-testid="wish-review-empty" />
      ) : (
        <>
          <p className="type-caption text-label-2" aria-live="polite">{t("moderation.review.caption", { shown: n(shown.length), pending: n(counts.pending) })}</p>
          <ul className="grid gap-2 lg:grid-cols-2">
            {shown.map((g) => (
              <WishCard key={g.key} group={g} canEdit={canEdit} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
