"use client";
/**
 * One learned suggestion (phase19-suggestions.md §5, motion.md §3.10): a proposed SOFT preference plus its
 * evidence, never applied by itself. Dashed = not applied yet. Header kind + confidence word and 3-step meter,
 * the claim, what accepting adds (the backend's own sentence), the evidence (collapsed, "Kanıtı göster"), and
 * three actions: Kabul et (soft only, weight Düşük / Normal), Reddet (with an optional reason), Ertele.
 * After an action the card collapses to a one-line receipt (with Geri al for an accept); the list removes it
 * after 8 s unless it has focus or hover. Keys on the card: a accept · d dismiss · s snooze · Enter evidence.
 */
import { CheckCircle2, ChevronDown, Clock, Repeat2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import type { SnoozeUntil, Suggestion } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { springs, tween, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { ACCEPT_WEIGHTS, evidenceText, levelCode, meterSteps } from "./learning-model";

export type Receipt = { kind: "accepted"; constraintId: number | null } | { kind: "dismissed" } | { kind: "snoozed"; until: SnoozeUntil };

const DISMISS_REASONS = ["stale", "wrongPerson", "differentTerm"] as const;
const SNOOZE: readonly SnoozeUntil[] = ["next_solve", "P7D", "next_term"];
const EVIDENCE_LAYOUT_MAX = 40;

export function ConfidenceMeter({ confidence, label }: { confidence: number; label: string }) {
  const steps = meterSteps(confidence);
  return (
    <span role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={Number(confidence.toFixed(2))} aria-valuetext={label} className="inline-flex items-center gap-0.5" data-steps={steps}>
      {[1, 2, 3].map((i) => (
        <span key={i} aria-hidden className={cn("h-2.5 w-1.5 rounded-sm", i <= steps ? "bg-label-1/60" : "bg-fill-2")} />
      ))}
    </span>
  );
}

export function SuggestionCard({
  s,
  canAct,
  receipt,
  busy,
  onAccept,
  onReject,
  onSnooze,
  onUndo,
  onHold,
  compact = false,
}: {
  s: Suggestion;
  canAct: boolean;
  receipt?: Receipt;
  busy?: boolean;
  onAccept: (weight: number) => void;
  onReject: (reason?: string) => void;
  onSnooze: (until: SnoozeUntil) => void;
  onUndo?: () => void;
  /** the receipt is focused / hovered: the list must not remove it yet */
  onHold?: (held: boolean) => void;
  compact?: boolean;
}) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [other, setOther] = useState("");
  const firstChip = useRef<HTMLButtonElement>(null);
  const level = levelCode(s);
  const levelWord = t(`learning.level.${level}`);
  const evidence = evidenceText(s, lang);
  const kind = t(`learning.kind.${s.attribute}` as MessageKey);
  const terms = s.evidence.terms ?? [];
  const layout = !reduce && terms.length <= EVIDENCE_LAYOUT_MAX;

  useEffect(() => {
    if (dismissing) firstChip.current?.focus();
  }, [dismissing]);

  const onKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget || !canAct || receipt) return;
    if (e.key === "a") onAccept(ACCEPT_WEIGHTS.normal);
    else if (e.key === "d") setDismissing(true);
    else if (e.key === "s") onSnooze("next_solve");
    else if (e.key === "Enter") setOpen((o) => !o);
    else return;
    e.preventDefault();
  };

  if (receipt) {
    const text = receipt.kind === "accepted" ? t("learning.receipt.accepted") : receipt.kind === "dismissed" ? t("learning.receipt.dismissed") : t("learning.receipt.snoozed", { until: t(`learning.snooze.${receipt.until}`) });
    return (
      <motion.div
        layout={!reduce}
        transition={springs.smooth}
        role="status"
        data-testid="suggestion-receipt"
        data-kind={receipt.kind}
        className="flex flex-wrap items-center gap-2 rounded-xl border border-hairline bg-fill-3 px-3 py-2 type-footnote"
        onMouseEnter={() => onHold?.(true)}
        onMouseLeave={() => onHold?.(false)}
        onFocus={() => onHold?.(true)}
        onBlur={() => onHold?.(false)}
      >
        <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden />
        <span className="min-w-0 flex-1">
          {text} · {s.subject.label}
        </span>
        {receipt.kind === "accepted" && receipt.constraintId !== null && onUndo ? (
          <Button size="xs" variant="ghost" onClick={onUndo} data-testid="suggestion-undo">{t("common.undo")}</Button>
        ) : null}
      </motion.div>
    );
  }

  return (
    <motion.article
      layout={layout}
      transition={springs.smooth}
      tabIndex={0}
      onKeyDown={onKey}
      aria-labelledby={`${id}-claim`}
      aria-describedby={`${id}-evidence`}
      aria-keyshortcuts={canAct ? "a d s Enter" : "Enter"}
      data-testid="suggestion-card"
      data-suggestion-id={s.id}
      className="flex flex-col gap-2 rounded-xl border border-dashed border-hairline-strong bg-fill-3 p-4 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)"
    >
      <header className="flex items-center gap-2 type-footnote text-label-2">
        <Repeat2 className="size-4" aria-hidden />
        <span className="font-semibold">{t("learning.card.label")} · {kind}</span>
        <span className="ml-auto inline-flex items-center gap-1.5">
          <span className="text-label-1">{levelWord}</span>
          <ConfidenceMeter confidence={s.confidence} label={t("learning.card.meter", { level: levelWord, evidence })} />
        </span>
      </header>
      <h3 id={`${id}-claim`} className="type-headline">{s.claim[lang] || s.claim.tr}</h3>
      {!compact ? <p className="type-footnote text-label-2">{s.if_accepted[lang] || s.if_accepted.tr}</p> : null}
      <div className="flex flex-wrap items-center gap-2 type-footnote">
        <span id={`${id}-evidence`}>
          {t("learning.card.evidence")} · {evidence}
          {s.cross_season ? ` · ${t("learning.card.crossSeason")}` : ""}
        </span>
        <Button size="xs" variant="ghost" aria-expanded={open} aria-controls={`${id}-list`} onClick={() => setOpen((o) => !o)} data-testid="suggestion-evidence-toggle">
          {t(open ? "learning.card.hideEvidence" : "learning.card.showEvidence")}
          <ChevronDown className={cn("transition-transform duration-(--dur-fast)", open && "rotate-180")} aria-hidden />
        </Button>
      </div>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div id={`${id}-list`} key="ev" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1, transition: reduce ? { duration: 0 } : { ...tween.fadeIn, delay: 0.06 } }} exit={{ opacity: 0, transition: reduce ? { duration: 0 } : tween.fadeOut }} className="flex flex-col gap-1 type-footnote text-label-2">
            <p>{s.explanation[lang] || s.explanation.tr}</p>
            {terms.length ? (
              <ul className="flex flex-col">
                {terms.map((x) => (
                  <li key={`${x.term_id}-${x.code}`} className="flex gap-3 tabular-nums">
                    <span className="w-24 shrink-0 font-semibold text-label-1">{x.code}</span>
                    <span>{t("learning.card.termRows", { pos: n(x.pos), total: n(x.total) })}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {s.impact.request_ids.length ? <p>{t("learning.card.impact", { n: n(s.impact.request_ids.length) })}</p> : null}
            {s.impact.covered_request_ids.length ? <p>⚠ {t("learning.card.covered", { n: n(s.impact.covered_request_ids.length) })}</p> : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
      {!canAct ? (
        <p className="type-caption text-label-3">{t("learning.card.needsEdit")}</p>
      ) : dismissing ? (
        <div className="flex flex-col gap-2" role="group" aria-label={t("learning.card.dismissWhy")}>
          <p className="type-footnote text-label-2">{t("learning.card.dismissWhy")}</p>
          <div className="flex flex-wrap gap-1.5">
            {DISMISS_REASONS.map((r, i) => (
              <Chip key={r} ref={i === 0 ? firstChip : undefined} onClick={() => onReject(t(`learning.dismiss.${r}`))} disabled={busy} data-testid={`dismiss-${r}`}>
                {t(`learning.dismiss.${r}`)}
              </Chip>
            ))}
            <Chip onClick={() => onReject(undefined)} disabled={busy} data-testid="dismiss-skip">{t("learning.dismiss.skip")}</Chip>
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (other.trim()) onReject(other.trim()); }}>
            <Input value={other} onChange={(e) => setOther(e.target.value)} placeholder={t("learning.dismiss.otherPh")} aria-label={t("learning.dismiss.other")} maxLength={500} />
            <Button type="submit" size="sm" variant="secondary" disabled={!other.trim() || busy}>{t("learning.card.reject")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setDismissing(false)} aria-label={t("common.cancel")}><X aria-hidden /></Button>
          </form>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex">
            <Button size="sm" className="rounded-r-none" onClick={() => onAccept(ACCEPT_WEIGHTS.normal)} disabled={busy} data-testid="suggestion-accept" aria-keyshortcuts="a">
              {busy ? t("busy.saving") : t("learning.card.accept", { weight: t("learning.weight.normal") })}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button size="sm" className="rounded-l-none border-l border-white/25 px-2" aria-label={t("learning.card.weightMenu")} disabled={busy} />}>
                <ChevronDown aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {(["low", "normal"] as const).map((w) => (
                  <DropdownMenuItem key={w} onClick={() => onAccept(ACCEPT_WEIGHTS[w])}>
                    {t("learning.card.acceptWeight", { weight: t(`learning.weight.${w}`), n: ACCEPT_WEIGHTS[w] })}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </span>
          <Button size="sm" variant="ghost" onClick={() => setDismissing(true)} disabled={busy} data-testid="suggestion-reject" aria-keyshortcuts="d">
            {t("learning.card.reject")}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="sm" variant="ghost" disabled={busy} data-testid="suggestion-snooze" />}>
              <Clock aria-hidden />
              {t("learning.card.snooze")}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {SNOOZE.map((u) => (
                <DropdownMenuItem key={u} onClick={() => onSnooze(u)}>{t(`learning.snooze.${u}`)}</DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </motion.article>
  );
}
