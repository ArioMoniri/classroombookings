"use client";

import { AlertTriangle, Check, ChevronRight, Info, Loader2, OctagonX } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { HardnessControl } from "./hardness-control";
import type { Token, WeightScale } from "./rule-sentence";
import { SlotChip } from "./slot-picker";
import { SourceChip, type SourceKind } from "./source-chip";

export interface AffectedInfo {
  count: number | null;
  loading?: boolean;
  percent?: number | null;
  /** the rule targets specific classes (0 matches is then a problem) */
  targeted?: boolean;
}

export interface ClashInfo {
  other: string;
  onShowBoth?: () => void;
  fixes?: { label: string; run: () => void }[];
}

export interface Candidate {
  text: string;
  options: { id: number; label: string }[];
  onPick: (id: number) => void;
}

export interface RuleCardProps {
  domId: string;
  tokens: Token[] | null;
  /** used when no template matches the kind */
  fallback: string;
  nlText?: string | null;
  provenance?: string | null;
  source: SourceKind;
  subLabel?: string | null;
  proposal?: boolean;
  hardness: "hard" | "soft";
  weight: number;
  allowed?: readonly ("hard" | "soft")[];
  scale?: WeightScale;
  onHardness?: (h: "hard" | "soft") => void;
  onWeight?: (w: number) => void;
  onSlotChange?: (slot: string, value: unknown) => void;
  affected?: AffectedInfo;
  onShowClasses?: () => void;
  clash?: ClashInfo | null;
  issues?: string[];
  candidates?: Candidate[];
  enabled?: boolean;
  readOnly?: boolean;
  saved?: boolean;
  advanced?: boolean;
  kind?: string;
  params?: Record<string, unknown>;
  menu?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  testId?: string;
  onHover?: (hovering: boolean) => void;
}

/** The one rule shape (generator-studio.md §3.3.0): sentence with slots, source chip, Must/Try,
 * importance, "applies to N classes", conflict line. Used for term rules, proposals and pins. */
export function RuleCard(p: RuleCardProps) {
  const { t, locale } = useI18n();
  const reduce = useReducedMotion();
  const sentenceId = `${p.domId}-sentence`;
  const clashId = `${p.domId}-clash`;
  const zero = p.affected && !p.affected.loading && p.affected.count === 0 && p.affected.targeted !== false;
  const most = p.affected && p.hardness === "hard" && (p.affected.percent ?? 0) > 50;
  return (
    <article
      id={p.domId}
      aria-labelledby={sentenceId}
      aria-describedby={p.clash ? clashId : undefined}
      data-testid={p.testId ?? "rule-card"}
      onMouseEnter={p.onHover ? () => p.onHover?.(true) : undefined}
      onMouseLeave={p.onHover ? () => p.onHover?.(false) : undefined}
      className={cn(
        "group/rule rounded-[var(--radius-md)] border bg-card p-3 text-sm shadow-[var(--shadow-1)] sm:p-4",
        p.proposal && "border-dashed border-primary/50 bg-primary-tint/40",
        p.enabled === false && "opacity-60",
        p.clash && "border-status-infeasible-border",
      )}
    >
      <div className="flex items-start gap-2">
        <SourceChip source={p.source} proposal={p.proposal} className="mt-0.5" />
        <p id={sentenceId} className="min-w-0 flex-1 text-[0.95rem] leading-relaxed">
          {p.tokens
            ? p.tokens.map((tok, i) =>
                tok.kind === "text" ? (
                  <span key={i}>{tok.text}</span>
                ) : (
                  <SlotChip key={`${tok.slot.name}-${i}`} slot={tok.slot} readOnly={p.readOnly || !p.onSlotChange} onChange={p.onSlotChange ? (v) => p.onSlotChange?.(tok.slot.name, v) : undefined} uncertain={p.candidates?.length ? true : undefined} />
                ),
              )
            : p.fallback}
        </p>
        {p.saved ? (
          <motion.span initial={reduce ? false : { opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} className="inline-flex items-center gap-1 text-xs text-status-feasible-fg" role="status">
            <Check className="size-3.5" aria-hidden /> {t("studio.rule.saved")}
          </motion.span>
        ) : null}
        {p.menu}
      </div>
      {p.subLabel ? <p className="mt-1 pl-1 text-xs text-muted-foreground">{p.subLabel}</p> : null}

      {!p.readOnly && p.onHardness && p.onWeight ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
          <HardnessControl hardness={p.hardness} weight={p.weight} allowed={p.allowed} onHardness={p.onHardness} onWeight={p.onWeight} scale={p.scale} advanced={Boolean(p.advanced)} compact={p.compact} idPrefix={p.domId} />
          <AffectedBadge affected={p.affected} onClick={p.onShowClasses} />
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("rounded-full px-2 py-0.5 font-medium", p.hardness === "hard" ? "bg-foreground text-background" : "border border-border-strong text-foreground")}>{p.hardness === "hard" ? t("studio.rule.must") : t("studio.rule.try")}</span>
          <AffectedBadge affected={p.affected} onClick={p.onShowClasses} />
        </div>
      )}

      {zero ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-status-warning-fg" data-testid="matches-none">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> {t("studio.rule.matchesNone")}
        </p>
      ) : null}
      {most ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Info className="size-3.5 shrink-0" aria-hidden /> {t("studio.rule.affectsMost")}
        </p>
      ) : null}

      {p.candidates?.length ? (
        <div className="mt-2 space-y-1.5 rounded-md bg-status-warning/60 p-2 text-xs" data-testid="candidates">
          {p.candidates.map((c) => (
            <div key={c.text} className="flex flex-wrap items-center gap-1.5">
              <span>{t("studio.tray.didYouMean", { text: c.text })}</span>
              {c.options.map((o) => (
                <Button key={o.id} size="xs" variant="outline" onClick={() => c.onPick(o.id)} data-testid="candidate-option">
                  {o.label}
                </Button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
      {p.issues?.length ? (
        <ul className="mt-2 space-y-0.5 text-xs text-status-warning-fg">
          {p.issues.map((x) => (
            <li key={x} className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /> {x}
            </li>
          ))}
        </ul>
      ) : null}

      {p.nlText || p.provenance ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {p.nlText ? (
            <q lang={/[çğıöşüİ]/i.test(p.nlText) ? "tr" : locale}>{p.nlText}</q>
          ) : null}
          {p.nlText && p.provenance ? " · " : null}
          {p.provenance}
        </p>
      ) : null}

      {p.clash ? (
        <div id={clashId} className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-status-infeasible px-2 py-1.5 text-xs text-status-infeasible-fg" data-testid="rule-clash">
          <OctagonX className="size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1">{t("studio.rule.clash", { other: p.clash.other })}</span>
          {p.clash.onShowBoth ? (
            <Button size="xs" variant="outline" onClick={p.clash.onShowBoth}>
              {t("studio.rule.showBoth")}
            </Button>
          ) : null}
          {p.clash.fixes?.map((f) => (
            <Button key={f.label} size="xs" variant="outline" onClick={f.run}>
              {f.label}
            </Button>
          ))}
        </div>
      ) : null}

      {p.advanced && p.kind ? (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none">
            <span className="font-mono">{p.kind}</span> · {t("studio.rule.rawParams")}
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted p-2 font-mono text-[11px]">{JSON.stringify(p.params ?? {}, null, 2)}</pre>
        </details>
      ) : null}

      {p.actions ? <div className="mt-3 flex flex-wrap items-center gap-2">{p.actions}</div> : null}
    </article>
  );
}

export function AffectedBadge({ affected, onClick }: { affected?: AffectedInfo; onClick?: () => void }) {
  const { t, n } = useI18n();
  if (!affected) return null;
  if (affected.loading && affected.count === null) return <span className="inline-block h-5 w-28 animate-pulse rounded-full bg-muted" aria-label={t("common.loading")} />;
  if (affected.count === null) return null;
  const label = t("studio.rule.appliesTo", { n: n(affected.count) });
  const pct = affected.percent !== null && affected.percent !== undefined ? ` (${n(affected.percent, { maximumFractionDigits: 1 })} %)` : "";
  const cls = cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs", affected.count === 0 && affected.targeted !== false ? "border-status-warning-border bg-status-warning text-status-warning-fg" : "bg-background");
  const body = (
    <>
      {affected.loading ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
      <span data-testid="affected-count">{label}</span>
      {pct}
    </>
  );
  return onClick ? (
    <button type="button" onClick={onClick} className={cn(cls, "hover:border-primary hover:text-primary pointer-coarse:min-h-11")}>
      {body}
      <ChevronRight className="size-3" aria-hidden />
    </button>
  ) : (
    <span className={cls}>
      {body}
    </span>
  );
}
