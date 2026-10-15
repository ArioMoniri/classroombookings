"use client";

import { Check, Loader2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { NativeSelect } from "@/components/common/native-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { REVIEW_KINDS, type DecisionIn, type ReviewItem, type ReviewOut } from "@/lib/api/council";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

const KIND_LABEL: Record<(typeof REVIEW_KINDS)[number], MessageKey> = {
  classification: "onboarding.kinds.classification",
  mapping: "onboarding.kinds.mapping",
  merge: "onboarding.kinds.merge",
  issue: "onboarding.kinds.issue",
  rule: "onboarding.kinds.rule",
  rule_text: "onboarding.kinds.rule_text",
  plan: "onboarding.kinds.plan",
  file: "onboarding.kinds.file",
};

function decisionLabel(item: ReviewItem): string | null {
  if (!item.decision) return null;
  return item.decision.action;
}

function ItemRow({ item, onDecide, busy }: { item: ReviewItem; onDecide: (d: DecisionIn) => void; busy: boolean }) {
  const { t } = useI18n();
  const [field, setField] = useState<string>(String((item.current?.field as string | null | undefined) ?? ""));
  const [kind, setKind] = useState<string>(String((item.current?.kind as string | undefined) ?? ""));
  const editable = item.kind === "mapping" || item.kind === "classification";
  const rejectable = item.kind !== "plan";
  const done = decisionLabel(item);
  return (
    <li className="space-y-1 py-2" data-testid={`review-${item.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 text-sm">
          <p className="font-medium">{item.title}</p>
          <p className="text-xs text-muted-foreground">
            {item.confidence != null ? `${t("onboarding.confidence")} ${Math.round(item.confidence * 100)} %` : null}
            {item.severity ? ` · ${item.severity}` : null}
            {item.blocking ? ` · ${t("onboarding.blockingItem")}` : null}
          </p>
          {item.samples?.length ? <p className="truncate text-xs text-muted-foreground">{t("onboarding.samples")}: {item.samples.join(" · ")}</p> : null}
        </div>
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
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDecide({ id: item.id, action: "reject" })}>
              <X aria-hidden />
              {t("onboarding.reject")}
            </Button>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function ReviewPanel({ review, busy, onDecide }: { review: ReviewOut; busy: boolean; onDecide: (decisions: DecisionIn[]) => void }) {
  const { t } = useI18n();
  const groups = useMemo(() => {
    const out = new Map<ReviewItem["kind"], ReviewItem[]>();
    for (const it of review.items) out.set(it.kind, [...(out.get(it.kind) ?? []), it]);
    return REVIEW_KINDS.filter((k) => out.has(k)).map((k) => [k, out.get(k) ?? []] as const);
  }, [review.items]);
  const open = review.items.filter((it) => it.blocking && !it.decision);

  return (
    <Card data-testid="onboarding-review">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span>{t("onboarding.review")}</span>
          <span className="flex items-center gap-2 text-sm font-normal">
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
            <Badge variant={open.length ? "destructive" : "secondary"} data-testid="blocking-count">
              {t("onboarding.blocking", { count: open.length })}
            </Badge>
            {open.length ? (
              <Button size="sm" disabled={busy} onClick={() => onDecide(open.map((it) => ({ id: it.id, action: "accept" })))}>
                {t("onboarding.acceptAll")}
              </Button>
            ) : null}
          </span>
        </CardTitle>
        <p className="text-sm text-muted-foreground">{t("onboarding.reviewHint", { threshold: Math.round(review.threshold * 100) })}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {review.errors.length ? <p className="text-sm text-destructive">{review.errors.join("; ")}</p> : null}
        {!review.items.length ? <p className="text-sm text-muted-foreground">{t("onboarding.noItems")}</p> : null}
        {groups.map(([kind, items]) => (
          <section key={kind} aria-label={t(KIND_LABEL[kind])}>
            <h3 className="text-sm font-semibold">
              {t(KIND_LABEL[kind])} <span className="font-normal text-muted-foreground">({items.length})</span>
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
    <div className="grid gap-2 sm:grid-cols-3">
      <label className="text-xs">
        {t("onboarding.termCode")}
        <Input value={value.code} onChange={(e) => onChange({ ...value, code: e.target.value })} data-testid="term-code" />
      </label>
      <label className="text-xs">
        {t("onboarding.termName")}
        <Input value={value.name} onChange={(e) => onChange({ ...value, name: e.target.value })} />
      </label>
      <label className="text-xs">
        {t("onboarding.weekCount")}
        <Input type="number" min={1} max={60} value={value.weekCount} onChange={(e) => onChange({ ...value, weekCount: Number(e.target.value) || 1 })} />
      </label>
    </div>
  );
}
