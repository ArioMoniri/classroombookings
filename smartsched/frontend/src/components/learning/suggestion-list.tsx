"use client";
/**
 * The suggestion cards of a surface (moderation profile, Moderasyon › Tercihler › Öneriler, the Studio review
 * tray): Bekleyen / Geçmiş, an honest first-use explainer, receipts that stay 8 s (paused while focused or
 * hovered), focus to the next card after an action, and a polite live region. Pull, not push: no toasts for
 * new suggestions, and a first-reveal stagger only on the first render (motion.md §3.10).
 */
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { HttpError } from "@/lib/api/client";
import { lk, useSuggestionActions, useSuggestions, type AcceptScope, type SnoozeUntil, type Suggestion } from "@/lib/api/learning";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { springs, staggerDelay, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { splitSuggestions } from "./learning-model";
import { SuggestionCard, type Receipt } from "./suggestion-card";

const RECEIPT_MS = 8000;
const ANIMATE_MAX = 40;

export function SuggestionList({ termId, personId, canAct, surface, max, compact = false, title, className }: { termId: number; personId?: number; canAct: boolean; surface: "moderation" | "studio" | "intake"; max?: number; compact?: boolean; title?: string; className?: string }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const qc = useQueryClient();
  const q = useSuggestions(termId, personId ?? null);
  const actions = useSuggestionActions();
  const [view, setView] = useState<"pending" | "history">("pending");
  const [receipts, setReceipts] = useState<Map<number, Receipt>>(new Map());
  const [busy, setBusy] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");
  const { can } = usePermissions();
  const canPersist = canAct && can("planning.admin");
  const [persist, setPersist] = useState<{ s: Suggestion; weight: number } | null>(null);
  const held = useRef(new Set<number>());
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  // the stagger is for the first reveal only, never for later inserts (motion.md §3.10)
  const [firstReveal, setFirstReveal] = useState(true);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const id = window.setTimeout(() => setFirstReveal(false), 400);
    const all = timers.current;
    return () => {
      window.clearTimeout(id);
      all.forEach((x) => clearTimeout(x));
    };
  }, []);

  const { pending, history } = useMemo(() => splitSuggestions(q.data ?? []), [q.data]);
  // a decided card keeps its receipt in place until it pops out (it moved to Geçmiş on the server already)
  const shown: Suggestion[] = useMemo(() => {
    const ids = new Set(pending.map((s) => s.id));
    const extra = (q.data ?? []).filter((s) => receipts.has(s.id) && !ids.has(s.id));
    const list = [...pending, ...extra].sort((a, b) => (q.data ?? []).indexOf(a) - (q.data ?? []).indexOf(b));
    return max ? list.slice(0, max) : list;
  }, [pending, q.data, receipts, max]);

  const drop = (id: number) => {
    const tm = timers.current.get(id);
    if (tm) clearTimeout(tm);
    timers.current.set(
      id,
      setTimeout(() => {
        if (held.current.has(id)) return drop(id);
        setReceipts((m) => {
          const next = new Map(m);
          next.delete(id);
          return next;
        });
      }, RECEIPT_MS),
    );
  };

  const focusNext = (id: number) => {
    window.requestAnimationFrame(() => {
      const cards = [...document.querySelectorAll<HTMLElement>('[data-testid="suggestion-card"]')];
      const next = cards.find((c) => Number(c.dataset.suggestionId) !== id);
      if (next) next.focus();
      else heading.current?.focus();
    });
  };

  const run = async (s: Suggestion, fn: () => Promise<Receipt>, live: string) => {
    setBusy(s.id);
    try {
      const r = await fn();
      setReceipts((m) => new Map(m).set(s.id, r));
      drop(s.id);
      setAnnounce(live);
      focusNext(s.id);
    } catch (e) {
      toast.error(e instanceof HttpError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const accept = (s: Suggestion, weight: number, scope: AcceptScope = "term") => void run(s, async () => {
    const out = await actions.accept.mutateAsync({ id: s.id, weight, scope });
    return { kind: "accepted", constraintId: out.constraint_id, scope };
  }, t(scope === "persistent" ? "learning.live.acceptedPersistent" : "learning.live.accepted"));
  const reject = (s: Suggestion, reason?: string) => void run(s, async () => {
    await actions.reject.mutateAsync({ id: s.id, reason });
    return { kind: "dismissed" };
  }, t("learning.live.dismissed"));
  const snooze = (s: Suggestion, until: SnoozeUntil) => void run(s, async () => {
    await actions.snooze.mutateAsync({ id: s.id, until });
    return { kind: "snoozed", until };
  }, t("learning.live.snoozed"));
  /** Geri al on a receipt or in Geçmiş: the decision is undone server-side (restore) and the card is open again */
  const undo = async (s: Suggestion) => {
    try {
      const out = await actions.restore.mutateAsync(s.id);
      // the card is open again in the cache BEFORE its receipt goes: otherwise it leaves the list for a moment
      // (stale data still says accepted / dismissed) and its exit animation swallows the re-entry
      qc.setQueryData<Suggestion[]>(lk.suggestions(termId, personId ?? null), (old) =>
        old?.map((x) => (x.id === s.id ? { ...x, state: out.state, scope: null, decided_at: null, snoozed_until: null, snooze_mode: null, constraint_id: null } : x)),
      );
      setReceipts((m) => {
        const next = new Map(m);
        next.delete(s.id);
        return next;
      });
      await qc.invalidateQueries({ queryKey: lk.suggestions(termId, personId ?? null) });
      setAnnounce(t("learning.live.undone"));
    } catch (e) {
      toast.error(e instanceof HttpError ? e.message : String(e));
    }
  };

  const heading_ = title ?? t(surface === "studio" ? "learning.list.studioTitle" : "learning.list.title", { n: pending.length });

  if (q.isLoading) {
    if (surface === "studio") return null;
    return (
      <div className="flex flex-col gap-2" aria-busy>
        <Skeleton className="h-28 w-full rounded-xl" />
        {max === 1 ? null : <Skeleton className="h-28 w-full rounded-xl" />}
      </div>
    );
  }
  if (q.isError) {
    // a role without planning.view, or the learning lane off: the rest of the surface works (spec §10 Error)
    if (q.error instanceof HttpError && q.error.status === 403) return null;
    return (
      <p role="alert" className="flex items-center gap-2 type-footnote text-label-2">
        {t("learning.list.error")}
        <Button size="xs" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>
      </p>
    );
  }
  const total = (q.data ?? []).length;
  // the Studio tray and compact profile slots stay hidden when there is nothing to review (no empty group)
  if ((surface === "studio" || compact) && shown.length === 0) return null;

  const animate = !reduce && shown.length <= ANIMATE_MAX;
  return (
    <section aria-labelledby={`sugg-${surface}-${personId ?? "all"}`} className={cn("flex flex-col gap-2", className)} data-testid={`suggestions-${surface}`}>
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`sugg-${surface}-${personId ?? "all"}`} ref={heading} tabIndex={-1} className="type-headline outline-hidden">{heading_}</h2>
        {!compact ? (
          <SegmentedControl<"pending" | "history">
            className="ml-auto"
            aria-label={t("learning.list.views")}
            size="sm"
            value={view}
            onValueChange={setView}
            options={[
              { value: "pending", label: t("learning.list.pending", { n: pending.length }) },
              { value: "history", label: t("learning.list.history", { n: history.length }) },
            ]}
          />
        ) : null}
      </div>
      {view === "history" && !compact ? (
        history.length ? (
          <ul className="flex flex-col gap-1" data-testid="suggestion-history">
            {history.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 border-b border-hairline py-1.5 type-footnote" data-testid="history-row" data-state={s.state}>
                <span className="font-semibold">{t(`learning.state.${s.state}`)}</span>
                <span className="min-w-0 flex-1">{s.claim[lang] || s.claim.tr}</span>
                {s.state === "accepted" && s.scope === "persistent" ? <span className="text-label-2">{t("learning.state.persistent")}</span> : null}
                {s.decided_at ? <span className="text-label-3">{new Date(s.decided_at).toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB")}</span> : null}
                {canAct && (s.state === "accepted" || s.state === "dismissed" || s.state === "snoozed") ? (
                  <Button size="xs" variant="ghost" className="max-md:h-11" onClick={() => void undo(s)} data-testid="history-undo">{t("common.undo")}</Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-footnote text-label-2">{t("learning.list.noHistory")}</p>
        )
      ) : shown.length === 0 ? (
        <div className="flex flex-col gap-1" data-testid="suggestions-empty">
          <p className="type-callout">{total === 0 ? t("learning.list.firstUse") : t("learning.list.allDone", { n: history.length })}</p>
          {total === 0 ? <p className="type-footnote text-label-2">{t("learning.list.firstUseHint")}</p> : null}
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          <AnimatePresence initial={false} mode="popLayout">
            {shown.map((s, i) => (
              <motion.li
                key={s.id}
                layout={animate}
                initial={animate && firstReveal ? { opacity: 0, y: 6 } : false}
                animate={{ opacity: 1, y: 0, transition: animate ? { ...springs.smooth, delay: firstReveal ? staggerDelay(i) : 0 } : { duration: 0 } }}
                exit={{ opacity: 0, transition: reduce ? tween.reduced : tween.fadeOut }}
                transition={springs.smooth}
              >
                <SuggestionCard
                  s={s}
                  canAct={canAct}
                  compact={compact}
                  receipt={receipts.get(s.id)}
                  busy={busy === s.id}
                  onAccept={(w) => accept(s, w)}
                  onReject={(r) => reject(s, r)}
                  onSnooze={(u) => snooze(s, u)}
                  onUndo={() => void undo(s)}
                  onAcceptPersistent={canPersist ? (w) => setPersist({ s, weight: w }) : undefined}
                  onHold={(h) => (h ? held.current.add(s.id) : held.current.delete(s.id))}
                />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
      <ResponsiveDialog
        open={persist !== null}
        onOpenChange={(o) => !o && setPersist(null)}
        alert
        title={t("learning.persistent.title")}
        description={persist ? t("learning.persistent.body", { subject: persist.s.subject.label }) : undefined}
        testId="persistent-confirm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPersist(null)}>{t("common.cancel")}</Button>
            <Button onClick={() => { if (persist) accept(persist.s, persist.weight, "persistent"); setPersist(null); }} data-testid="persistent-go">{t("learning.persistent.go")}</Button>
          </>
        }
      >
        <ul className="flex list-disc flex-col gap-1 pl-5 type-footnote text-label-2">
          <li>{t("learning.persistent.point1")}</li>
          <li>{t("learning.persistent.point2")}</li>
          <li>{t("learning.persistent.point3")}</li>
        </ul>
      </ResponsiveDialog>
    </section>
  );
}
