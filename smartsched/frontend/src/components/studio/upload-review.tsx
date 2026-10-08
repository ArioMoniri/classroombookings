"use client";

import { Check, CircleDot, Pencil, ShieldAlert, ShieldCheck, Undo2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { StudioMeta } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ProposalCard } from "./review-tray";
import { confidenceLevel, provenanceText, ruleTokens } from "./rule-helpers";
import { plainSentence } from "./rule-sentence";
import { useStudioData } from "./studio-data";
import type { TrayItem } from "./studio-store";

export type ReviewTab = "all" | "ready" | "look" | "unread";

export function bucketOf(it: TrayItem): Exclude<ReviewTab, "all"> {
  if (it.type === "unparsed") return "unread";
  const status = it.type === "rule" ? it.proposal.status : it.edit.status;
  return status === "ok" ? "ready" : "look";
}

export function reviewCounts(items: TrayItem[]): Record<ReviewTab, number> {
  const out: Record<ReviewTab, number> = { all: items.length, ready: 0, look: 0, unread: 0 };
  for (const it of items) out[bucketOf(it)]++;
  return out;
}

const TAB_KEY: Record<ReviewTab, MessageKey> = { all: "studio.review.tab.all", ready: "studio.review.tab.ready", look: "studio.review.tab.look", unread: "studio.review.tab.unread" };

function refOf(it: TrayItem): Record<string, unknown> | null {
  const r = it.type === "rule" ? it.proposal.source_ref : it.type === "edit" ? it.edit.source_ref : it.unparsed.source_ref;
  return (r as Record<string, unknown> | null | undefined) ?? null;
}
function quoteOf(it: TrayItem): string {
  const ref = refOf(it);
  const ex = typeof ref?.excerpt === "string" ? ref.excerpt : "";
  return it.type === "rule" ? it.proposal.nl_text || ex : it.type === "edit" ? it.edit.nl_text || ex : it.unparsed.text || ex;
}

/**
 * Review table for uploaded files (AirOps / Copy.ai pattern): summary box, tabs
 * All · Ready · Needs a look · Couldn't read, provenance "from file · sheet · row 12", per-row
 * Accept / Edit / Reject, "Accept all ready", "Reject selected", "Rephrase as text…".
 */
export function UploadReview({
  items,
  meta,
  onAccept,
  onReject,
  onUpdate,
  onRephrase,
  onUndo,
}: {
  items: TrayItem[];
  meta: StudioMeta | undefined;
  onAccept: (items: TrayItem[]) => Promise<unknown> | void;
  onReject: (keys: string[]) => void;
  onUpdate: (key: string, p: ProposedConstraint) => void;
  onRephrase: (text: string, key: string) => void;
  onUndo?: () => void;
}) {
  const { t } = useI18n();
  const { sentence } = useStudioData();
  const [tab, setTab] = useState<ReviewTab>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<string | null>(null);
  const [source, setSource] = useState<TrayItem | null>(null);
  const [busy, setBusy] = useState(false);

  const active = items.filter((i) => i.state !== "rejected");
  const pending = active.filter((i) => i.state === "pending");
  const counts = reviewCounts(pending);
  const files = new Set(items.map((i) => i.file ?? "")).size;
  const shown = useMemo(() => active.filter((i) => tab === "all" || (i.state === "pending" && bucketOf(i) === tab)), [active, tab]);
  const ready = pending.filter((i) => bucketOf(i) === "ready");
  if (items.length === 0) return null;

  const run = async (fn: () => Promise<unknown> | void) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  const proposed = (it: TrayItem): string => {
    if (it.type === "rule") {
      const r = ruleTokens(meta, it.proposal.kind, it.proposal.params, sentence);
      return r.tokens ? plainSentence(r.tokens) : (it.proposal.title ?? it.proposal.kind);
    }
    if (it.type === "edit") {
      const ch = Object.entries(it.edit.changes).filter(([, v]) => v !== null && v !== undefined);
      const what = ch.map(([k, v]) => t("studio.review.setField", { field: k === "enrolment" ? t("studio.classes.col.students") : k, value: String(v) })).join(", ");
      return `${what}${it.edit.labels.length ? ` · ${it.edit.labels.join(", ")}` : ""}`;
    }
    return "—";
  };

  return (
    <section aria-labelledby="review-title" className="space-y-3 rounded-xl border bg-card p-3 sm:p-4" data-testid="upload-review">
      <div className="rounded-md bg-muted/60 p-2.5 text-sm" role="status">
        <h3 id="review-title" className="font-semibold">
          {t("studio.review.title")}
        </h3>
        <p className="text-muted-foreground">{t("studio.review.summary", { files, n: pending.length, ready: counts.ready, look: counts.look, unread: counts.unread })}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label={t("studio.review.title")} className="flex flex-wrap gap-1">
          {(["all", "ready", "look", "unread"] as const).map((k) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={cn("rounded-md border px-2 py-1 text-xs pointer-coarse:min-h-11", tab === k ? "border-primary bg-primary-tint font-medium text-primary" : "hover:bg-muted")} data-testid={`review-tab-${k}`}>
              {t(TAB_KEY[k])} <span className="tabular-nums">{k === "all" ? counts.all : counts[k]}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={busy || selected.size === 0} onClick={() => {
            onReject([...selected]);
            setSelected(new Set());
          }}>
            {t("studio.review.rejectSelected", { n: selected.size })}
          </Button>
          <Button size="sm" disabled={busy || ready.length === 0} onClick={() => void run(() => onAccept(ready))} data-testid="review-accept-all">
            <Check aria-hidden /> {t("studio.tray.acceptAll", { n: ready.length })}
          </Button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm" aria-label={t("studio.review.title")}>
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="w-8 py-1.5" scope="col">
                <span className="sr-only">{t("studio.classes.select")}</span>
              </th>
              <th className="py-1.5 pr-2 font-medium" scope="col">{t("studio.review.col.from")}</th>
              <th className="py-1.5 pr-2 font-medium" scope="col">{t("studio.review.col.text")}</th>
              <th className="py-1.5 pr-2 font-medium" scope="col">{t("studio.review.col.rule")}</th>
              <th className="hidden py-1.5 pr-2 font-medium lg:table-cell" scope="col">{t("studio.review.col.confidence")}</th>
              <th className="py-1.5 font-medium" scope="col">{t("common.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((it) => {
              const ref = refOf(it);
              const bucket = bucketOf(it);
              const conf = it.type === "rule" ? it.proposal.confidence : it.type === "edit" ? it.edit.confidence : 0;
              const level = confidenceLevel(conf);
              const issues = it.type === "rule" ? it.proposal.issues : it.type === "edit" ? it.edit.issues : [it.unparsed.reason];
              if (it.state === "accepted") {
                return (
                  <tr key={it.key} className="border-t" data-testid="review-row" data-state="accepted">
                    <td />
                    <td colSpan={5} className="py-2 text-xs text-status-feasible-fg">
                      <span className="inline-flex items-center gap-1.5">
                        <Check className="size-3.5" aria-hidden /> {t("studio.review.added")} · {provenanceText(ref, t) ?? it.file}
                        {onUndo ? (
                          <button type="button" className="ml-2 inline-flex items-center gap-1 underline" onClick={onUndo}>
                            <Undo2 className="size-3" aria-hidden /> {t("common.undo")}
                          </button>
                        ) : null}
                      </span>
                    </td>
                  </tr>
                );
              }
              return [
                <tr key={it.key} className="border-t align-top" data-testid="review-row" data-bucket={bucket} data-state={it.state}>
                  <td className="py-2">
                    <Checkbox checked={selected.has(it.key)} onCheckedChange={(v) => setSelected((s) => {
                      const n = new Set(s);
                      if (v) n.add(it.key);
                      else n.delete(it.key);
                      return n;
                    })} aria-label={t("studio.review.selectRow", { row: String(ref?.row ?? ref?.line ?? ref?.page ?? "") })} />
                  </td>
                  <td className="py-2 pr-2">
                    <button type="button" className="text-left text-xs text-primary underline-offset-2 hover:underline" onClick={() => setSource(it)} data-testid="review-from">
                      {provenanceText(ref, t) ?? it.file}
                    </button>
                  </td>
                  <td className="max-w-56 py-2 pr-2 text-xs">
                    <q lang="tr" className="line-clamp-3 text-muted-foreground">{quoteOf(it)}</q>
                  </td>
                  <td className="py-2 pr-2">
                    <span className="block">{proposed(it)}</span>
                    {it.type === "rule" ? (
                      <span className={cn("mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium", it.proposal.hardness === "hard" ? "bg-foreground text-background" : "border border-border-strong")}>{it.proposal.hardness === "hard" ? t("studio.rule.must") : t("studio.rule.try")}</span>
                    ) : null}
                    {issues.filter(Boolean).length ? <span className="mt-1 block text-xs text-status-warning-fg">{issues.filter(Boolean).join("; ")}</span> : null}
                  </td>
                  <td className="hidden py-2 pr-2 text-xs lg:table-cell">
                    {it.type !== "unparsed" ? (
                      <span className="inline-flex items-center gap-1">
                        {level === "high" ? <ShieldCheck className="size-3.5 text-status-feasible-fg" aria-hidden /> : level === "medium" ? <CircleDot className="size-3.5 text-status-warning-fg" aria-hidden /> : <ShieldAlert className="size-3.5 text-status-infeasible-fg" aria-hidden />}
                        {t(`studio.review.conf.${level}`)}
                      </span>
                    ) : null}
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1">
                      {it.type === "unparsed" ? (
                        <Button size="xs" variant="outline" onClick={() => onRephrase(it.unparsed.text || quoteOf(it), it.key)}>
                          {t("studio.review.rephrase")}
                        </Button>
                      ) : (
                        <>
                          <Button size="xs" onClick={() => void run(() => onAccept([it]))} disabled={busy} aria-label={`${t("studio.tray.accept")}: ${provenanceText(ref, t) ?? ""}`} data-testid="review-accept">
                            <Check aria-hidden />
                            <span className="sr-only sm:not-sr-only">{t("studio.tray.accept")}</span>
                          </Button>
                          {it.type === "rule" ? (
                            <Button size="xs" variant="outline" onClick={() => setEditing(editing === it.key ? null : it.key)} aria-expanded={editing === it.key} aria-label={t("common.edit")}>
                              <Pencil aria-hidden />
                            </Button>
                          ) : null}
                        </>
                      )}
                      <Button size="xs" variant="ghost" onClick={() => onReject([it.key])} aria-label={t("studio.review.reject")} data-testid="review-reject">
                        <X aria-hidden />
                      </Button>
                    </div>
                  </td>
                </tr>,
                editing === it.key && it.type === "rule" ? (
                  <tr key={`${it.key}-edit`}>
                    <td />
                    <td colSpan={5} className="pb-3">
                      <ProposalCard item={it} meta={meta} onAccept={() => void run(() => onAccept([it]))} onReject={() => onReject([it.key])} onChange={(p) => onUpdate(it.key, p)} busy={busy} />
                    </td>
                  </tr>
                ) : null,
              ];
            })}
            {shown.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-sm text-muted-foreground">
                  {t("studio.review.empty")}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <Sheet open={source !== null} onOpenChange={(o) => !o && setSource(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t("studio.review.sourceTitle")}</SheetTitle>
            <SheetDescription>{source ? provenanceText(refOf(source), t) : null}</SheetDescription>
          </SheetHeader>
          {source ? (
            <div className="space-y-3 px-4 pb-4 text-sm">
              <p className="text-xs text-muted-foreground">{t("studio.review.sourceHelp")}</p>
              <blockquote lang="tr" className="rounded-md border-l-4 border-primary bg-muted/60 p-3 whitespace-pre-wrap">
                <mark className="bg-status-warning text-foreground">{quoteOf(source)}</mark>
              </blockquote>
              {source.type === "rule" ? <p>{proposed(source)}</p> : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </section>
  );
}
