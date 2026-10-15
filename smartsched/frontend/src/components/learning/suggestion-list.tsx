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
import { lk, useSuggestionActions, useSuggestions, type SnoozeUntil, type Suggestion } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import { springs, staggerDelay, tween, useReduce } from "@/lib/motion";
import { splitSuggestions } from "./learning-model";
import { SuggestionCard, type Receipt } from "./suggestion-card";

const RECEIPT_MS = 8000;
const ANIMATE_MAX = 40;

export function SuggestionList({ termId, personId, canAct, surface, max, compact = false, title }: { termId: number; personId?: number; canAct: boolean; surface: "moderation" | "studio" | "intake"; max?: number; compact?: boolean; title?: string }) {
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
  const held = useRef(new Set<number>());
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const firstReveal = useRef(true);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const id = window.setTimeout(() => (firstReveal.current = false), 400);
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

  const accept = (s: Suggestion, weight: number) => void run(s, async () => {
    const out = await actions.accept.mutateAsync({ id: s.id, weight });
    return { kind: "accepted", constraintId: out.constraint_id };
  }, t("learning.live.accepted"));
  const reject = (s: Suggestion, reason?: string) => void run(s, async () => {
    await actions.reject.mutateAsync({ id: s.id, reason });
    return { kind: "dismissed" };
  }, t("learning.live.dismissed"));
  const snooze = (s: Suggestion, until: SnoozeUntil) => void run(s, async () => {
    await actions.snooze.mutateAsync({ id: s.id, until });
    return { kind: "snoozed", until };
  }, t("learning.live.snoozed"));
  const undo = async (s: Suggestion, constraintId: number) => {
    try {
      await actions.undoAccept.mutateAsync(constraintId);
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
    <section aria-labelledby={`sugg-${surface}-${personId ?? "all"}`} className="flex flex-col gap-2" data-testid={`suggestions-${surface}`}>
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
              <li key={s.id} className="flex flex-wrap gap-2 border-b border-hairline py-1.5 type-footnote">
                <span className="font-semibold">{t(`learning.state.${s.state}`)}</span>
                <span className="min-w-0 flex-1">{s.claim[lang] || s.claim.tr}</span>
                {s.decided_at ? <span className="text-label-3">{new Date(s.decided_at).toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB")}</span> : null}
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
                initial={animate && firstReveal.current ? { opacity: 0, y: 6 } : false}
                animate={{ opacity: 1, y: 0, transition: animate ? { ...springs.smooth, delay: firstReveal.current ? staggerDelay(i) : 0 } : { duration: 0 } }}
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
                  onUndo={() => {
                    const r = receipts.get(s.id);
                    if (r?.kind === "accepted" && r.constraintId !== null) void undo(s, r.constraintId);
                  }}
                  onHold={(h) => (h ? held.current.add(s.id) : held.current.delete(s.id))}
                />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}
