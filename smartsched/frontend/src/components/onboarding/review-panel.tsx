"use client";

import { Check, History, X } from "lucide-react";
import { useMemo, useState } from "react";
import { NativeSelect } from "@/components/ui/native-select";
import { Badge } from "@/components/ui/badge";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { isReviewKind, REVIEW_KINDS, type DecisionIn, type ReviewItem, type ReviewKind, type ReviewOut } from "@/lib/api/council";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useOnboardingCopy } from "./copy";

/** Intake memory (2026-10-15): `remembered` {at, job, label, label_tr} + `suggestion` {action, value} on an item. */
function memoryOf(item: ReviewItem): { at: string; job: string | number; suggestion: DecisionIn | null } | null {
  const r = item.remembered as Record<string, unknown> | undefined;
  if (!r || typeof r !== "object") return null;
  const sug = item.suggestion as { action?: string; value?: Record<string, unknown> | null } | undefined;
  const action = sug?.action === "accept" || sug?.action === "reject" || sug?.action === "edit" ? sug.action : null;
  return { at: String(r.at ?? "").slice(0, 10), job: (r.job as string | number) ?? "?", suggestion: action ? { id: item.id, action, value: sug?.value ?? null } : null };
}

const KIND_LABEL: Record<Exclude<ReviewKind, "ai_rows">, MessageKey> = {
  classification: "onboarding.kinds.classification",
  mapping: "onboarding.kinds.mapping",
  merge: "onboarding.kinds.merge",
  issue: "onboarding.kinds.issue",
  rule: "onboarding.kinds.rule",
  rule_text: "onboarding.kinds.rule_text",
  plan: "onboarding.kinds.plan",
  file: "onboarding.kinds.file",
};

/** The section label of a kind: ai_rows and kinds this screen does not know yet have labels of their own (T-R1-21). */
function useKindLabel(): (kind: string) => string {
  const { t } = useI18n();
  const c = useOnboardingCopy();
  return (kind) => (kind === "ai_rows" ? c.rowsTitle : isReviewKind(kind) && kind in KIND_LABEL ? t(KIND_LABEL[kind as keyof typeof KIND_LABEL]) : c.kindOther);
}

function decisionLabel(item: ReviewItem, c: ReturnType<typeof useOnboardingCopy>): string | null {
  if (!item.decision) return null;
  return c.decision[item.decision.action] ?? item.decision.action;
}

function ItemRow({ item, onDecide, busy }: { item: ReviewItem; onDecide: (d: DecisionIn) => void; busy: boolean }) {
  const { t } = useI18n();
  const [field, setField] = useState<string>(String((item.current?.field as string | null | undefined) ?? ""));
  const [kind, setKind] = useState<string>(String((item.current?.kind as string | undefined) ?? ""));
  const editable = item.kind === "mapping" || item.kind === "classification";
  const rejectable = item.kind !== "plan";
  // rows read by the AI model are decided row by row in the rows panel, never as one item (POST /rows/decisions)
  const perRow = item.kind === "ai_rows";
  const c = useOnboardingCopy();
  const done = decisionLabel(item, c);
  const memory = memoryOf(item);
  return (
    <li className="space-y-1 py-2" data-testid={`review-${item.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 text-sm">
          <p className="type-callout font-medium text-label-1">{item.title}</p>
          <p className="type-footnote text-label-2">
            {item.confidence != null ? `${t("onboarding.confidence")} ${c.pct(Math.round(item.confidence * 100))}` : null}
            {item.severity ? ` · ${c.severity[item.severity] ?? item.severity}` : null}
            {item.blocking ? ` · ${t("onboarding.blockingItem")}` : null}
          </p>
          {item.samples?.length ? <p className="truncate type-footnote text-label-2">{t("onboarding.samples")}: {item.samples.join(" · ")}</p> : null}
          {memory ? (
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 type-footnote text-label-2" data-testid="review-remembered">
              <History aria-hidden className="size-3.5 stroke-[1.75]" />
              <span>{c.remembered(memory.at, memory.job)}</span>
              {!done ? <span className="text-label-1">{c.stillDecide}</span> : null}
              {!done && memory.suggestion ? (
                <Button size="xs" variant="secondary" className="pointer-coarse:min-h-11" disabled={busy} onClick={() => onDecide(memory.suggestion as DecisionIn)}>
                  {c.applySuggestion}
                </Button>
              ) : null}
            </p>
          ) : null}
        </div>
        {perRow ? (
          <p className="type-footnote text-label-2">{c.rowsBelow}</p>
        ) : (
        <div className="flex flex-wrap items-center gap-2">
          {done ? <Badge variant="secondary">{done}</Badge> : null}
          {item.kind === "mapping" ? (
            <NativeSelect aria-label={t("onboarding.field")} className="w-40" value={field} onChange={(e) => setField(e.target.value)}>
              {(item.options ?? []).map((o) => (
                <option key={o} value={o}>
                  {o || t("onboarding.notUsed")}
                </option>
              ))}
            </NativeSelect>
          ) : null}
          {item.kind === "classification" ? (
            <NativeSelect aria-label={t("onboarding.kind")} className="w-40" value={kind} onChange={(e) => setKind(e.target.value)}>
              {(item.options ?? []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </NativeSelect>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            className="pointer-coarse:min-h-11"
            disabled={busy}
            onClick={() => {
              const changed = item.kind === "mapping" ? field !== String(item.current?.field ?? "") : item.kind === "classification" ? kind !== item.current?.kind : false;
              if (editable && changed) onDecide({ id: item.id, action: "edit", value: item.kind === "mapping" ? { field } : { kind } });
              else onDecide({ id: item.id, action: "accept" });
            }}
          >
            <Check aria-hidden />
            {t("onboarding.accept")}
          </Button>
          {rejectable ? (
            <Button size="sm" variant="ghost" className="pointer-coarse:min-h-11" disabled={busy} onClick={() => onDecide({ id: item.id, action: "reject" })}>
              <X aria-hidden />
              {t("onboarding.reject")}
            </Button>
          ) : null}
        </div>
        )}
      </div>
    </li>
  );
}

export function ReviewPanel({ review, busy, onDecide }: { review: ReviewOut; busy: boolean; onDecide: (decisions: DecisionIn[]) => void }) {
  const { t } = useI18n();
  const kindLabel = useKindLabel();
  const groups = useMemo(() => {
    const out = new Map<string, ReviewItem[]>();
    for (const it of review.items) out.set(it.kind, [...(out.get(it.kind) ?? []), it]);
    // known kinds in pipeline order, then any kind the screen does not know yet (under "Diğer")
    const order = [...REVIEW_KINDS.filter((k) => out.has(k)), ...[...out.keys()].filter((k) => !isReviewKind(k))];
    return order.map((k) => [k, out.get(k) ?? []] as const);
  }, [review.items]);
  const open = review.items.filter((it) => it.blocking && !it.decision);
  // "accept all blocking" covers the items decided here; AI rows are decided in the rows panel
  const acceptable = open.filter((it) => it.kind !== "ai_rows");
  const c = useOnboardingCopy();

  return (
    <Card data-testid="onboarding-review">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>{t("onboarding.review")}</span>
          <span className="flex items-center gap-2 text-sm font-normal">
            {busy ? <BusyGlyph className="size-4" /> : null}
            <Badge variant={open.length ? "destructive" : "secondary"} data-testid="blocking-count">
              {t("onboarding.blocking", { count: open.length })}
            </Badge>
            {acceptable.length ? (
              <Button size="sm" className="pointer-coarse:min-h-11" disabled={busy} onClick={() => onDecide(acceptable.map((it) => ({ id: it.id, action: "accept" })))}>
                {t("onboarding.acceptAll")}
              </Button>
            ) : null}
          </span>
        </CardTitle>
        <p className="type-callout text-label-2">{t("onboarding.reviewHint", { threshold: Math.round(review.threshold * 100) })}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {review.errors.length ? <p className="type-callout text-status-infeasible-fg">{review.errors.join("; ")}</p> : null}
        {!review.items.length ? <p className="type-callout text-label-2">{t("onboarding.noItems")}</p> : null}
        {!review.content ? (
          // viewers (planning.view only): counts per kind, no samples, texts or names
          <div data-testid="review-counts-only" className="grid gap-2">
            <p className="type-callout text-label-2">{c.viewerOnly}</p>
            <dl className="grid gap-x-6 gap-y-2 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
              {groups.map(([kind, items]) => (
                <div key={kind}>
                  <dt className="type-footnote text-label-2">{kindLabel(kind)}</dt>
                  <dd className="type-headline tnum">{items.length}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
        {review.content && groups.map(([kind, items]) => (
          <section key={kind} aria-label={kindLabel(kind)}>
            <h3 className="type-callout font-semibold">
              {kindLabel(kind)} <span className="font-normal text-label-2">({items.length})</span>
            </h3>
            <ul className="divide-y">
              {items.slice(0, 100).map((it) => (
                <ItemRow key={it.id} item={it} busy={busy} onDecide={(d) => onDecide([d])} />
              ))}
            </ul>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}

export function PlanTermFields({ value, onChange }: { value: { code: string; name: string; weekCount: number }; onChange: (v: { code: string; name: string; weekCount: number }) => void }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(11rem,1fr))]">
      <label className="grid gap-1 type-footnote font-medium text-label-2">
        {t("onboarding.termCode")}
        <Input value={value.code} onChange={(e) => onChange({ ...value, code: e.target.value })} data-testid="term-code" />
      </label>
      <label className="grid gap-1 type-footnote font-medium text-label-2">
        {t("onboarding.termName")}
        <Input value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />
      </label>
      <label className="grid gap-1 type-footnote font-medium text-label-2">
        {t("onboarding.weekCount")}
        <Input type="number" min={1} max={60} value={value.weekCount} onChange={(e) => onChange({ ...value, weekCount: Number(e.target.value) || 1 })} />
      </label>
    </div>
  );
}
