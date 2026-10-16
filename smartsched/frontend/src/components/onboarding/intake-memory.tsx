"use client";
/**
 * "Hatırlanan kararlar": what the intake remembers from earlier reviews (backend `app/council/memory_admin.py`,
 * `GET /council/memory`) — column mappings, header spellings, sheet kinds, term mappings, merge and rule decisions —
 * grouped by file signature. A group opens to its rows; one row or a whole signature can be forgotten after a
 * confirm (`DELETE /council/memory/{id}`, `DELETE /council/memory?signature=`). A forget is a learning reset of
 * scope `intake`: planning administrators can undo it for 30 days (toast action, or Ayarlar › Öğrenme › Son
 * sıfırlamalar). Readers with planning.view only see the list without file content and no forget buttons.
 *
 * Mounted on the onboarding page (before a new upload) and in Ayarlar › Öğrenme next to the reset controls.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, History, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { HttpError } from "@/lib/api/client";
import { MEMORY_KINDS, councilApi, type IntakeMemoryGroup, type IntakeMemoryItem, type MemoryForgetOut } from "@/lib/api/council";
import { learningApi } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

export const memoryKey = ["council-memory"] as const;
/** the sections of the view, in order (backend `GROUP_OF`) */
export const MEMORY_SECTIONS = ["layout", "term", "lexicon", "merge", "rule"] as const;

type Pending = { kind: "row"; item: IntakeMemoryItem } | { kind: "group"; group: IntakeMemoryGroup };

/** Groups of one section, newest first, with their rows. */
export function sectionGroups(data: { groups: IntakeMemoryGroup[]; items: IntakeMemoryItem[] }, section: string): { group: IntakeMemoryGroup; rows: IntakeMemoryItem[] }[] {
  const byId = new Map(data.items.map((i) => [i.id, i]));
  return data.groups
    .filter((g) => g.group === section)
    .sort((a, b) => b.last_at.localeCompare(a.last_at))
    .map((group) => ({ group, rows: group.ids.map((id) => byId.get(id)).filter((x): x is IntakeMemoryItem => !!x) }));
}

export function IntakeMemoryPanel({ compact = false }: { compact?: boolean }) {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const { can } = usePermissions();
  const canForget = can("planning.edit");
  const canUndo = can("planning.admin");
  const memory = useQuery({ queryKey: memoryKey, queryFn: () => councilApi.memory(), staleTime: 15_000 });
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [pending, setPending] = useState<Pending | null>(null);
  const lang = locale === "tr" ? "tr" : "en";
  const date = (iso: string) => new Date(iso).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: memoryKey });
    void qc.invalidateQueries({ queryKey: ["learning"] });
  };
  const undo = useMutation({ mutationFn: (id: number) => learningApi.undoReset(id), onSuccess: refresh });
  const forget = useMutation({
    mutationFn: (p: Pending): Promise<MemoryForgetOut> => (p.kind === "row" ? councilApi.forget(p.item.id) : councilApi.forgetSignature(p.group.signature)),
    onSuccess: (out) => {
      setPending(null);
      refresh();
      const msg = t("intakeMemory.forgotten", { n: n(out.forgotten) });
      if (canUndo && out.undoable) {
        toast.success(msg, {
          action: {
            label: t("common.undo"),
            onClick: () =>
              void undo
                .mutateAsync(out.id)
                .then(() => toast.success(t("intakeMemory.restored")))
                .catch((e: unknown) => toast.error(e instanceof HttpError ? e.message : String(e))),
          },
        });
      } else toast.success(msg, { description: t("intakeMemory.undoHint") });
    },
    onError: (e: unknown) => toast.error(e instanceof HttpError ? e.message : String(e)),
  });

  const toggle = (sig: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(sig)) next.delete(sig);
      else next.add(sig);
      return next;
    });

  const data = memory.data;
  return (
    <Card data-testid="intake-memory">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="size-4 text-label-3" aria-hidden />
          {t("intakeMemory.title")}
        </CardTitle>
        <CardDescription>{t("intakeMemory.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {memory.isError ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">{t("intakeMemory.error")}</p>
        ) : !data ? (
          <Skeleton className="h-24 w-full" />
        ) : data.total === 0 ? (
          <p className="type-callout text-label-2" data-testid="intake-memory-empty">{t("intakeMemory.empty")}</p>
        ) : (
          <>
            <p className="type-footnote text-label-2" data-testid="intake-memory-total">
              {t("intakeMemory.total", { n: n(data.total), groups: n(data.groups.length) })}
              {!data.content ? ` ${t("intakeMemory.noContent")}` : ""}
            </p>
            {MEMORY_SECTIONS.map((section) => {
              const groups = sectionGroups(data, section);
              if (!groups.length) return null;
              const shown = compact ? groups.slice(0, 20) : groups;
              return (
                <section key={section} aria-labelledby={`mem-sec-${section}`} className="grid gap-1.5" data-testid={`intake-memory-section-${section}`}>
                  <h3 id={`mem-sec-${section}`} className="type-headline text-label-1">{t(`intakeMemory.section.${section}`)}</h3>
                  <ul className="grid gap-1.5">
                    {shown.map(({ group, rows }) => {
                      const isOpen = open.has(group.signature);
                      return (
                        <li key={group.signature} className="rounded-lg edge-hairline" data-testid="intake-memory-group" data-signature={group.signature}>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 p-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-auto min-h-11 min-w-0 flex-1 justify-start gap-2 py-1.5 text-left whitespace-normal"
                              aria-expanded={isOpen}
                              aria-controls={`mem-rows-${group.signature}`}
                              onClick={() => toggle(group.signature)}
                              data-testid="intake-memory-group-toggle"
                            >
                              <ChevronRight className={cn("size-4 shrink-0 transition-transform duration-(--dur-fast)", isOpen && "rotate-90")} aria-hidden />
                              <span className="grid min-w-0">
                                <span className="font-medium break-words text-label-1">{group.label[lang]}</span>
                                <span className="type-footnote text-label-2">
                                  {t("intakeMemory.groupMeta", { n: n(group.count), date: date(group.last_at), jobs: group.jobs.map((j) => `#${j}`).join(", ") })}
                                </span>
                              </span>
                            </Button>
                            {canForget ? (
                              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={() => setPending({ kind: "group", group })} data-testid="intake-memory-forget-group">
                                <Trash2 aria-hidden />
                                {t("intakeMemory.forgetAll")}
                              </Button>
                            ) : null}
                          </div>
                          {isOpen ? (
                            <ul id={`mem-rows-${group.signature}`} className="grid border-t border-hairline" data-testid="intake-memory-rows">
                              {rows.map((it) => (
                                <li key={it.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 border-b border-hairline px-3 py-2 last:border-b-0" data-testid="intake-memory-row" data-kind={it.kind}>
                                  <div className="grid min-w-0 flex-1 gap-0.5">
                                    <span className="type-callout break-words text-label-1">{it.description[lang]}</span>
                                    <span className="type-footnote text-label-2">
                                      {t("intakeMemory.rowMeta", {
                                        kind: (MEMORY_KINDS as readonly string[]).includes(it.kind) ? t(`intakeMemory.kind.${it.kind as (typeof MEMORY_KINDS)[number]}`) : it.kind,
                                        who: it.created_by?.name ?? t("intakeMemory.someone"),
                                        date: date(it.created_at),
                                        job: it.job_id,
                                      })}
                                    </span>
                                  </div>
                                  {!it.effective ? <Badge variant="outline">{t("intakeMemory.superseded")}</Badge> : null}
                                  {canForget ? (
                                    <Button variant="ghost" size="sm" className="min-h-11 sm:min-h-8" onClick={() => setPending({ kind: "row", item: it })} aria-label={t("intakeMemory.forgetOneLabel", { what: it.description[lang] })} data-testid="intake-memory-forget-row">
                                      {t("intakeMemory.forget")}
                                    </Button>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                  {shown.length < groups.length ? <p className="type-footnote text-label-2">{t("intakeMemory.more", { n: n(groups.length - shown.length) })}</p> : null}
                </section>
              );
            })}
          </>
        )}
      </CardContent>
      <Dialog open={!!pending} onOpenChange={(o) => !o && !forget.isPending && setPending(null)}>
        <DialogContent className="sm:max-w-md" data-testid="intake-memory-confirm">
          <DialogHeader>
            <DialogTitle>{pending?.kind === "group" ? t("intakeMemory.confirmAllTitle") : t("intakeMemory.confirmOneTitle")}</DialogTitle>
            <DialogDescription>
              {pending?.kind === "group"
                ? t("intakeMemory.confirmAll", { n: n(pending.group.count), what: pending.group.label[lang] })
                : pending?.kind === "row"
                  ? t("intakeMemory.confirmOne", { what: pending.item.description[lang] })
                  : null}
            </DialogDescription>
          </DialogHeader>
          <p className="type-footnote text-label-2">{canUndo ? t("intakeMemory.confirmUndo") : t("intakeMemory.undoHint")}</p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPending(null)} disabled={forget.isPending}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => pending && forget.mutate(pending)} disabled={forget.isPending} aria-busy={forget.isPending || undefined} data-testid="intake-memory-confirm-button">
              <BusyLabel busy={forget.isPending} label={t("busy.working")}>{pending?.kind === "group" ? t("intakeMemory.forgetAll") : t("intakeMemory.forget")}</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
