"use client";

import { MoreHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/endpoints";
import type { Preview, PrecheckItem, StudioRule } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { ConfirmDialog } from "./confirm-dialog";
import { RuleCard } from "./rule-card";
import { allowedHardness, isFreeTextRule, issueMessages, plainRuleText, provenanceText, ruleDisplay } from "./rule-helpers";
import { templateIssues, writeField, type Params } from "./rule-sentence";
import { asSource } from "./source-chip";
import { useStudio } from "./studio-context";
import type { EffectiveRule } from "./studio-reducer";
import { useApplyFix } from "./use-fixes";
import { useRuleActions } from "./use-rule-actions";
import { pairLang } from "@/lib/i18n";

/** Flash-outline another card ("Show both"). */
export function flashCard(domId: string, reduce: boolean) {
  const el = document.getElementById(domId);
  if (!el) return;
  el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  el.classList.add("studio-flash");
  window.setTimeout(() => el.classList.remove("studio-flash"), 1600);
}

export function TermRuleCard({ eff, clash, compact }: { eff: EffectiveRule; clash: PrecheckItem | null; compact?: boolean }) {
  const { t, n, locale } = useI18n();
  const { meta, sentence, termId, kind, advanced, goStep, rules } = useStudio();
  const actions = useRuleActions();
  const fixes = useApplyFix();
  const rule = eff.rule;
  const [params, setParams] = useState<Params>(rule.params);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmSoft, setConfirmSoft] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);

  // server copy changed (refetch / undo): drop local edits
  const paramsKey = JSON.stringify(rule.params);
  const [baseKey, setBaseKey] = useState(paramsKey);
  if (baseKey !== paramsKey) {
    setBaseKey(paramsKey);
    setParams(rule.params);
    setPreview(null);
  }
  useEffect(() => () => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    abort.current?.abort();
  }, []);

  // structured rules render from their params in the UI language; free-text rules also keep their own words
  const shown = useMemo(() => ruleDisplay(rule, meta, sentence, params), [rule, meta, sentence, params]);
  const { template, tokens } = shown;
  const domId = `rule-${rule.id}`;
  const unsaved = template ? issueMessages(templateIssues(template, params, sentence), t, (v) => n(v)) : [];

  const onSlot = (name: string, value: unknown) => {
    const field = template?.fields.find((f) => f.name === name);
    if (!field) return;
    const next = writeField(field, params, value, sentence);
    setParams(next);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    abort.current?.abort();
    // an edit that would leave the rule blank or contradictory stays local until it is valid
    if (template && templateIssues(template, next, sentence).length) {
      setPreviewing(false);
      return;
    }
    const ctrl = new AbortController();
    abort.current = ctrl;
    setPreviewing(true);
    saveTimer.current = setTimeout(() => {
      void (async () => {
        try {
          const p = await api.studio.preview({ term_id: termId, kind: rule.kind, params: next, hardness: eff.hardness, draft_kind: kind }, ctrl.signal);
          setPreview(p);
        } catch {
          /* preview is best-effort */
        } finally {
          setPreviewing(false);
        }
        // a free-text rule keeps the planner's own words; a structured rule's text is rebuilt from its params
        await actions.updateParams(rule, next, isFreeTextRule(rule) ? undefined : plainRuleText(meta, rule.kind, next, rule.nl_text, sentence));
        setSaved(true);
        window.setTimeout(() => setSaved(false), 1000);
      })();
    }, 400);
  };

  const onHardness = (h: "hard" | "soft") => {
    if (rule.source === "FILE" && rule.hardness === "hard" && h === "soft") {
      setConfirmSoft(true);
      return;
    }
    actions.setOverride(rule, { hardness: h });
  };

  const other = clash ? clash.constraint_ids.find((id) => id !== rule.id) : undefined;
  const otherRule = other !== undefined ? rules?.rules.find((r) => r.id === other) : undefined;
  const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const affected = {
    count: preview ? preview.affected_count : (rule.affected_count ?? null),
    loading: previewing,
    percent: preview?.percent ?? null,
    targeted: preview ? preview.targeted : true,
  };
  const sub = rule.source_ref && (rule.source_ref as Record<string, unknown>).copied_from ? provenanceText(rule.source_ref, t) : null;

  return (
    <>
      <RuleCard
        domId={domId}
        tokens={tokens}
        fallback={shown.fallback}
        nlText={shown.nlText}
        writtenIn={shown.writtenIn}
        provenance={sub ? null : provenanceText(rule.source_ref, t)}
        subLabel={sub}
        source={asSource(rule.source)}
        hardness={eff.hardness}
        weight={eff.weight}
        allowed={allowedHardness(meta, rule.kind)}
        scale={meta?.weight_scale}
        onHardness={onHardness}
        onWeight={(w) => actions.setOverride(rule, { weight: w })}
        onSlotChange={onSlot}
        affected={affected}
        onShowClasses={() => goStep("classes", { rule: String(rule.id) })}
        enabled={eff.inPlay}
        saved={saved}
        advanced={advanced}
        kind={rule.kind}
        params={params}
        compact={compact}
        issues={unsaved.length ? (JSON.stringify(params) !== paramsKey ? unsaved.map((m) => `${t("studio.builder.notSaved")} ${m}`) : unsaved) : undefined}
        clash={
          clash
            ? {
                other: otherRule ? plainRuleText(meta, otherRule.kind, otherRule.params, otherRule.nl_text, sentence) : clash.message[pairLang(locale)],
                onShowBoth: otherRule ? () => flashCard(`rule-${otherRule.id}`, reduce) : undefined,
                fixes: clash.fixes.slice(0, 2).map((f) => ({ label: f.label[pairLang(locale)] || f.label.en, run: () => void fixes.apply(clash, f) })),
              }
            : null
        }
        menu={
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("studio.rules.more")} className="pointer-coarse:size-11" data-testid="rule-menu" />}>
              <MoreHorizontal aria-hidden />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => actions.setInPlay(rule, !eff.inPlay)}>{eff.inPlay ? t("studio.rules.turnOff") : t("studio.rules.turnOn")}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => void actions.duplicate(rule)}>{t("studio.rules.duplicate")}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={() => void actions.remove(rule)}>
                {t("common.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />
      <ConfirmDialog
        open={confirmSoft}
        onOpenChange={setConfirmSoft}
        title={t("studio.rule.fileSoftTitle")}
        description={t("studio.rule.fileSoftBody")}
        confirmLabel={t("studio.rule.makeTry")}
        onConfirm={() => actions.setOverride(rule, { hardness: "soft" })}
      />
    </>
  );
}

export type { StudioRule };
