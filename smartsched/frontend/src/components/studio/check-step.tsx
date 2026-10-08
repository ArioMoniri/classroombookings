"use client";

import { AlertTriangle, CheckCircle2, ChevronDown, Info, Loader2, OctagonX, RefreshCw } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { PrecheckCategory, PrecheckItem, Readiness } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { estimateWords } from "./studio-reducer";
import { useStudio } from "./studio-context";
import { useApplyFix } from "./use-fixes";
import { pairLang } from "@/lib/i18n";

const READY_KEY: Record<Readiness | "unknown" | "checking", MessageKey> = {
  ready: "studio.check.ready",
  needs_look: "studio.check.needsLook",
  blocked: "studio.check.blocked",
  unknown: "studio.check.unknown",
  checking: "studio.check.checking",
};
const READY_HELP: Record<Readiness | "unknown" | "checking", MessageKey> = {
  ready: "studio.check.readyHelp",
  needs_look: "studio.check.needsLookHelp",
  blocked: "studio.check.blockedHelp",
  unknown: "studio.check.unknownHelp",
  checking: "studio.check.checkingHelp",
};
const CAT_KEY: Record<PrecheckCategory, MessageKey> = { impossible: "studio.check.cat.impossible", clash: "studio.check.cat.clash", no_match: "studio.check.cat.no_match", info: "studio.check.cat.info" };
const PAGE = 20;

export function useEstimateText() {
  const { t } = useI18n();
  return (est: { low: number; high: number } | null) =>
    est
      ? estimateWords(est, (k, v) => t(k === "under" ? "studio.estimate.under" : k === "aboutOne" ? "studio.estimate.aboutOne" : k === "about" ? "studio.estimate.about" : "studio.estimate.atMost", v))
      : "—";
}

/** Readiness meter: icon + word (never colour alone), three segments. */
export function ReadinessMeter({ readiness, compact }: { readiness: Readiness | "unknown" | "checking"; compact?: boolean }) {
  const { t } = useI18n();
  const Icon = readiness === "ready" ? CheckCircle2 : readiness === "needs_look" ? AlertTriangle : readiness === "blocked" ? OctagonX : readiness === "checking" ? Loader2 : Info;
  const tone = readiness === "ready" ? "text-status-feasible-fg" : readiness === "needs_look" ? "text-status-warning-fg" : readiness === "blocked" ? "text-status-infeasible-fg" : "text-label-2";
  const level = readiness === "blocked" ? 1 : readiness === "needs_look" ? 2 : readiness === "ready" ? 3 : 0;
  return (
    <div className={cn("space-y-1.5", readiness === "checking" && "studio-pulse")} data-testid="readiness" data-readiness={readiness}>
      <p className={cn("flex items-center gap-1.5 font-semibold", compact ? "text-sm" : "text-base", tone)}>
        <Icon className={cn("size-4", readiness === "checking" && "animate-spin")} aria-hidden /> {t(READY_KEY[readiness])}
      </p>
      <div className="grid grid-cols-3 gap-1" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span key={i} className={cn("h-1.5 rounded-full", i <= level ? (level === 1 ? "bg-status-infeasible-fg" : level === 2 ? "bg-status-warning-fg" : "bg-status-feasible-fg") : "bg-fill-2")} />
        ))}
      </div>
      {!compact ? <p className="text-sm text-label-2">{t(READY_HELP[readiness])}</p> : null}
    </div>
  );
}

export function IssueCard({ item, onFixed }: { item: PrecheckItem; onFixed?: () => void }) {
  const { t, locale } = useI18n();
  const { advanced, isAdmin } = useStudio();
  const { apply, busy } = useApplyFix();
  const Icon = item.severity === "error" ? OctagonX : item.severity === "warning" ? AlertTriangle : Info;
  const tone = item.severity === "error" ? "text-status-infeasible-fg" : item.severity === "warning" ? "text-status-warning-fg" : "text-label-2";
  return (
    <article tabIndex={-1} data-issue-id={item.id} aria-labelledby={`issue-${item.id}`} className="rounded-[var(--radius-md)] border bg-card p-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50" data-testid="issue-card" data-severity={item.severity}>
      <h4 id={`issue-${item.id}`} className={cn("flex items-start gap-1.5 font-medium", tone)}>
        <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span className="text-foreground">{item.title[pairLang(locale)] || item.title.en}</span>
      </h4>
      <p className="mt-1 pl-5.5 text-label-2">{item.message[pairLang(locale)] || item.message.en}</p>
      {item.fixes.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5 pl-5.5">
          {item.fixes.map((f) => {
            const blocked = f.admin_only && !isAdmin;
            const running = busy === `${item.id}:${f.option}`;
            return (
              <Button
                key={f.option}
                size="sm"
                variant="outline"
                disabled={busy !== null || blocked}
                title={blocked ? t("studio.builtin.adminOnly") : undefined}
                onClick={async () => {
                  if (await apply(item, f)) onFixed?.();
                }}
                className="h-auto min-h-7 py-1 text-left whitespace-normal sm:max-w-80"
                data-testid="fix-button"
              >
                {running ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {f.label[pairLang(locale)] || f.label.en}
              </Button>
            );
          })}
        </div>
      ) : null}
      {advanced && item.detail ? (
        <details className="mt-2 pl-5.5 text-xs text-label-2">
          <summary className="cursor-pointer">{t("studio.check.details")}</summary>
          <p className="mt-1 font-mono">{item.detail}</p>
        </details>
      ) : null}
    </article>
  );
}

export function CheckStep() {
  const { t, n, locale } = useI18n();
  const reduce = useReducedMotion();
  const { precheck, checking, precheckError, runPrecheck, summary, summaryData } = useStudio();
  const est = useEstimateText();
  const [cat, setCat] = useState<PrecheckCategory | "all">("all");
  const [open, setOpen] = useState<Record<string, number>>({});
  const heading = useRef<HTMLHeadingElement>(null);
  const items = useMemo(() => (precheck?.items ?? []).filter((i) => cat === "all" || i.category === cat), [precheck, cat]);
  const groups = useMemo(() => {
    const order = precheck?.groups.length ? precheck.groups.map((g) => g.group) : [...new Set(items.map((i) => i.group))];
    const by = new Map<string, PrecheckItem[]>();
    for (const it of items) by.set(it.group, [...(by.get(it.group) ?? []), it]);
    return order.filter((g) => by.has(g)).map((g) => ({ group: g, items: by.get(g) ?? [], meta: precheck?.groups.find((x) => x.group === g) }));
  }, [items, precheck]);
  const many = items.length > PAGE;

  const focusNext = (id: string) =>
    window.requestAnimationFrame(() => {
      const cards = Array.from(document.querySelectorAll<HTMLElement>("[data-issue-id]")).filter((el) => el.dataset.issueId !== id);
      if (cards[0]) cards[0].focus();
      else heading.current?.focus();
    });

  const human = summaryData?.human_summary[pairLang(locale)];

  return (
    <div className="space-y-4" data-testid="check-step">
      <div className="grid gap-4 rounded-xl border bg-card p-4 md:grid-cols-[1fr_auto]">
        <div>
          <h3 ref={heading} tabIndex={-1} className="sr-only outline-none">
            {t("studio.step.check")}
          </h3>
          <ReadinessMeter readiness={summary.readiness} />
          <p className="mt-2 text-sm" aria-live="polite">
            {precheck ? precheck.summary[pairLang(locale)] : null}
          </p>
          {precheckError ? (
            <p role="alert" className="mt-2 text-sm text-status-warning-fg">
              {t("studio.check.failed")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <Button variant="outline" size="sm" onClick={() => void runPrecheck()} disabled={checking} data-testid="recheck">
            <RefreshCw className={cn(checking && "animate-spin")} aria-hidden /> {checking ? t("studio.check.checking") : t("studio.check.again")}
          </Button>
          <p className="text-sm text-label-2">{t("studio.check.estimate", { words: est(summary.estimate) })}</p>
        </div>
      </div>

      {human ? <p className="rounded-md bg-fill-2/50 p-3 text-sm">{human}</p> : null}

      {precheck ? (
        <>
          <div role="tablist" aria-label={t("studio.check.categories")} className="flex flex-wrap gap-1.5">
            {(["all", "impossible", "clash", "no_match", "info"] as const).map((c) => {
              const count = c === "all" ? precheck.items.length : (precheck.counts[c] ?? precheck.items.filter((i) => i.category === c).length);
              return (
                <button key={c} type="button" role="tab" aria-selected={cat === c} onClick={() => setCat(c)} className={cn("rounded-xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] px-2.5 py-1 text-xs pointer-coarse:min-h-11", cat === c ? "border-primary bg-tint-soft font-medium text-tint-text" : "hover:bg-fill-2")} data-testid={`check-tab-${c}`}>
                  {c === "all" ? t("studio.check.cat.all") : t(CAT_KEY[c])} <span className="tabular-nums">{n(count)}</span>
                </button>
              );
            })}
          </div>
          <div className={cn("space-y-4 transition-opacity", checking && "opacity-60")} role="tabpanel">
            {items.length === 0 ? (
              <p className="flex items-center gap-2 rounded-md border p-4 text-sm text-status-feasible-fg">
                <CheckCircle2 className="size-4" aria-hidden /> {t("studio.check.nothing")}
              </p>
            ) : (
              groups.map((g) => {
                const shown = open[g.group] ?? (many ? (g.items.length > 3 ? 0 : g.items.length) : g.items.length);
                const head = g.meta?.title?.[pairLang(locale)];
                return (
                  <section key={g.group} aria-label={g.group} className="space-y-2" data-testid="issue-group">
                    {many || g.items.length > 3 ? (
                      <button type="button" aria-expanded={shown > 0} onClick={() => setOpen((o) => ({ ...o, [g.group]: shown > 0 ? 0 : Math.min(PAGE, g.items.length) }))} className="flex w-full items-center gap-2 rounded-md border bg-fill-3 px-3 py-2 text-left text-sm hover:bg-fill-2 pointer-coarse:min-h-11">
                        <ChevronDown className={cn("size-4 transition-transform", shown === 0 && "-rotate-90")} aria-hidden />
                        <span className="flex-1">{t("studio.check.group", { n: n(g.items.length), cause: groupLabel(g.group, t, head) })}</span>
                      </button>
                    ) : null}
                    <ul className="space-y-2">
                      <AnimatePresence initial={false}>
                        {g.items.slice(0, shown).map((it) => (
                          <motion.li key={it.id} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={reduce ? { opacity: 0, transition: { duration: 0.1 } } : { opacity: 0, height: 0, transition: { duration: 0.18 } }}>
                            <IssueCard item={it} onFixed={() => focusNext(it.id)} />
                          </motion.li>
                        ))}
                      </AnimatePresence>
                    </ul>
                    {shown > 0 && shown < g.items.length ? (
                      <Button size="sm" variant="ghost" onClick={() => setOpen((o) => ({ ...o, [g.group]: Math.min(g.items.length, shown + PAGE) }))}>
                        {t("studio.check.showMore", { n: n(Math.min(PAGE, g.items.length - shown)) })}
                      </Button>
                    ) : null}
                  </section>
                );
              })
            )}
          </div>
        </>
      ) : checking ? (
        <p className="studio-pulse text-sm text-label-2" role="status">
          {t("studio.check.checking")}
        </p>
      ) : null}
    </div>
  );
}

const GROUP_KEYS: Record<string, MessageKey> = Object.fromEntries(
  (["capacity", "room_tags", "room_pin", "no_room", "blocked", "bad_time", "out_of_horizon", "no_time", "cohort_clash", "instructor_clash", "locked_overlap", "locked_ineligible", "locked_small", "locked_blocked", "pigeonhole", "rule_no_match", "rule_duplicate", "rule_conflict", "utilisation", "other"] as const).map((g) => [g, `studio.check.groupName.${g}` as MessageKey]),
);
function groupLabel(group: string, t: (k: MessageKey) => string, fallback?: string): string {
  return GROUP_KEYS[group] ? t(GROUP_KEYS[group]) : (fallback ?? group);
}
