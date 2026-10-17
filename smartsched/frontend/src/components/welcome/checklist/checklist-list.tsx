"use client";
/**
 * "Başlarken" checklist pieces (spec §4.3, wireframes welcome-checklist-{1440,390}.svg): the progress (bar + "5 adımdan
 * 2'si tamam", `role="progressbar"`), the rows (links named "… , tamamlandı / yapılacak"; done rows muted, never struck
 * through), "Bitti olarak işaretle" for view-only items, "Gizle", and the all-done state.
 *
 * Ticks come from the server (`done` on GET /welcome); a tick announces "{öğe} tamamlandı" once (polite).
 */
import { skipToken, useQuery } from "@tanstack/react-query";
import { Check, ChevronRight } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { welcomeKeys, type WelcomeState, useWelcomeEvent } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { dur, springs, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { itemKey } from "../content";
import { buildChecklist, type ChecklistModel, type ResolvedItem } from "../model";
import { useWelcomeStore } from "../welcome-store";

/** The cached GET /welcome (the provider fetches it; these readers never trigger a call). */
export function useWelcomeData(): WelcomeState | undefined {
  return useQuery<WelcomeState>({ queryKey: welcomeKeys.state, queryFn: skipToken }).data;
}

export function useChecklistModel(): ChecklistModel | null {
  const data = useWelcomeData();
  const localDone = useWelcomeStore((s) => s.localDone);
  const model = buildChecklist(data, new Set(localDone));
  if (!data?.enabled.checklist || !model || model.total === 0) return null;
  return model;
}

/** The actions every checklist surface shares. */
export function useChecklistActions() {
  const event = useWelcomeEvent();
  const markLocalDone = useWelcomeStore((s) => s.markLocalDone);
  const setOpen = useWelcomeStore((s) => s.setChecklistOpen);
  return {
    hide: () => {
      event.mutate({ guide_key: "checklist", event: "hidden" });
      setOpen(false);
    },
    markDone: (key: string) => {
      markLocalDone(key);
      event.mutate({ guide_key: "checklist", event: "item_done", item: key });
    },
  };
}

export function ChecklistProgress({ model, className }: { model: ChecklistModel; className?: string }) {
  const { t } = useI18n();
  const reduce = useReduce();
  const ratio = model.total ? model.done / model.total : 0;
  const text = t("welcome.check.progress", { done: model.done, total: model.total });
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <p className="type-footnote text-label-2 tabular-nums" data-testid="checklist-progress-text">
        {text}
      </p>
      <div role="progressbar" aria-label={t("welcome.check.title")} aria-valuemin={0} aria-valuemax={model.total} aria-valuenow={model.done} aria-valuetext={text} data-testid="checklist-progress" className="h-1.5 w-full overflow-hidden rounded-full bg-fill-1">
        <motion.div className="h-full w-full origin-left rounded-full bg-tint" initial={false} animate={{ scaleX: ratio }} transition={reduce ? { duration: 0 } : springs.ticker} />
      </div>
    </div>
  );
}

/** A check circle: fill, then the path draws (transitions.dev checkbox-check, retimed; instant under reduced motion). */
function Tick({ done }: { done: boolean }) {
  const reduce = useReduce();
  return (
    <span aria-hidden className={cn("relative flex size-6 shrink-0 items-center justify-center rounded-full", done ? "" : "edge-control")}>
      {done ? (
        <motion.span className="absolute inset-0 rounded-full bg-status-feasible" initial={reduce ? false : { scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={reduce ? { duration: 0 } : { duration: dur.fast }} />
      ) : null}
      {done ? (
        <svg viewBox="0 0 16 16" className="relative size-3.5 text-status-feasible-fg">
          <motion.path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={reduce ? { duration: 0 } : { duration: dur.slow, delay: dur.fast }} />
        </svg>
      ) : null}
    </span>
  );
}

export function ChecklistRows({ model, onNavigate, phone }: { model: ChecklistModel; onNavigate?: () => void; phone?: boolean }) {
  const { t } = useI18n();
  const actions = useChecklistActions();
  const [live, setLive] = useState("");
  const prev = useRef<Set<string> | null>(null);
  useEffect(() => {
    const now = new Set(model.items.filter((i) => i.done).map((i) => i.key));
    if (prev.current) {
      const fresh = [...now].find((k) => !prev.current!.has(k));
      if (fresh) setLive(t("welcome.check.ticked", { item: t(itemKey(fresh, "title")) }));
    }
    prev.current = now;
  }, [model.items, t]);
  const row = (i: ResolvedItem) => {
    const title = t(itemKey(i.key, "title"));
    const state = i.done ? t("welcome.check.stateDone") : t("welcome.check.stateTodo");
    return (
      <li key={i.key} className="flex items-center gap-1 not-last:edge-hairline-b" data-testid={`checklist-item-${i.key}`} data-done={i.done}>
        <Link
          href={i.href}
          onClick={onNavigate}
          aria-label={`${title}, ${state}`}
          className={cn("flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", phone ? "min-h-16" : "min-h-[52px]")}
        >
          <Tick done={i.done} />
          <span className="min-w-0 flex-1">
            <span className={cn("block type-callout font-medium", i.done ? "text-label-3" : "text-label-1")}>{title}</span>
            <span className="block truncate type-footnote text-label-3">{t(itemKey(i.key, "sub"))}</span>
          </span>
          <ChevronRight aria-hidden className="size-4 shrink-0 text-label-3" />
        </Link>
        {i.manual && !i.done ? (
          <Button variant="ghost" size="sm" className="shrink-0 pointer-coarse:min-h-11" onClick={() => actions.markDone(i.key)} data-testid={`checklist-mark-${i.key}`}>
            <Check aria-hidden /> {t("welcome.check.markDone")}
          </Button>
        ) : null}
      </li>
    );
  };
  return (
    <>
      <ul className="flex flex-col" data-testid="checklist-rows">
        {model.visible.map(row)}
      </ul>
      <p className="sr-only" aria-live="polite" data-testid="checklist-live">
        {live}
      </p>
    </>
  );
}

/** The all-done state: a disc that pops in with a drawn check (transitions.dev success-check without rotate / blur). */
export function ChecklistAllDone() {
  const { t } = useI18n();
  const reduce = useReduce();
  return (
    <div className="flex items-center gap-3 rounded-xl bg-fill-3 p-3" data-testid="checklist-all-done">
      <motion.span aria-hidden className="flex size-7 shrink-0 items-center justify-center rounded-full bg-status-feasible text-status-feasible-fg" initial={reduce ? false : { scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={reduce ? { duration: 0 } : springs.bouncySubtle}>
        <Check className="size-4" />
      </motion.span>
      <p className="type-callout text-label-1">{t("welcome.check.allDone")}</p>
    </div>
  );
}

/** Title + progress + rows + Gizle: the popover panel, the phone list and the home card share it. */
export function ChecklistPanel({ model, onNavigate, phone, headingId, headingRef }: { model: ChecklistModel; onNavigate?: () => void; phone?: boolean; headingId?: string; headingRef?: React.Ref<HTMLHeadingElement> }) {
  const { t } = useI18n();
  const actions = useChecklistActions();
  return (
    <div className="flex flex-col gap-3" data-testid="checklist-panel">
      <div className="flex items-start justify-between gap-3">
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 outline-hidden">
          {t("welcome.check.title")}
        </h2>
        <Button variant="ghost" size="sm" className="pointer-coarse:min-h-11" onClick={actions.hide} data-testid="checklist-hide">
          {t("welcome.check.hide")}
        </Button>
      </div>
      <ChecklistProgress model={model} />
      {model.allDone ? <ChecklistAllDone /> : null}
      <ChecklistRows model={model} onNavigate={onNavigate} phone={phone} />
    </div>
  );
}
