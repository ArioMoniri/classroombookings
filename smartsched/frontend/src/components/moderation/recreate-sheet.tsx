"use client";
/**
 * "Planı yeniden oluştur", step A (moderation spec §5.4): the server's changes since publish, the method (En az değişiklik =
 * a repair around the changed requests; Baştan çöz = a full re-solve), the time limit, and "Önizleme oluştur".
 * It starts a child run of the published run (`POST /terms/{id}/moderation/resolve`: stability, carried locks,
 * one worker, never activated) and opens its preview. Nothing changes for anyone until "Onayla ve yayınla".
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useQueryClient } from "@tanstack/react-query";
import { moderationApi, refusal, useChanges } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import { ChangesList } from "./changes-list";

const LIMITS = ["60", "120", "300"] as const;

export function RecreateSheet({ open, onOpenChange, termId, baseRunId, staged, side = "right" }: { open: boolean; onOpenChange: (v: boolean) => void; termId: number; baseRunId: number; staged: number[]; side?: "right" | "bottom" }) {
  const { t, locale, n } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const changes = useChanges(termId);
  const [mode, setMode] = useState<"repair" | "full">(staged.length ? "repair" : "full");
  const [limit, setLimit] = useState<(typeof LIMITS)[number]>("120");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const effective = staged.length ? mode : "full";

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await moderationApi.resolve(termId, { base_run_id: baseRunId, changed_request_ids: staged, mode: effective, time_limit_s: Number(limit) });
      void qc.invalidateQueries({ queryKey: ["moderation", "changes", termId] });
      toast.success(t("moderation.recreate.started", { id: out.run_id }));
      onOpenChange(false);
      router.push(`/moderation/recreate/${out.run_id}`);
    } catch (e) {
      setError(refusal(e, locale === "tr" ? "tr" : "en").message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={side} className="gap-4 overflow-y-auto p-6 sm:max-w-xl" data-testid="recreate-sheet">
        <SheetHeader className="p-0">
          <SheetTitle>{t("moderation.recreate.title")}</SheetTitle>
          <SheetDescription>{t("moderation.recreate.base", { id: baseRunId })}</SheetDescription>
        </SheetHeader>
        <section className="flex flex-col gap-1">
          <h3 className="type-headline">{t("moderation.recreate.changes", { n: n(changes.data?.total ?? 0) })}</h3>
          <ChangesList termId={termId} />
          {changes.data?.total ? <p className="type-caption text-label-2">{t("moderation.changes.requests", { n: n(staged.length) })}</p> : null}
        </section>
        <section className="flex flex-col gap-2">
          <h3 className="type-headline">{t("moderation.recreate.method")}</h3>
          <div role="radiogroup" aria-label={t("moderation.recreate.method")} className="flex flex-col gap-2">
            {(["repair", "full"] as const).map((m) => (
              <label key={m} className="flex items-start gap-2 type-callout">
                <input type="radio" name="recreate-mode" className="mt-1 accent-(--accent)" checked={effective === m} disabled={m === "repair" && !staged.length} onChange={() => setMode(m)} />
                <span>
                  <span className="font-semibold">{t(`moderation.recreate.${m}`)}</span>
                  <span className="block type-footnote text-label-2">{t(`moderation.recreate.${m}Hint`)}</span>
                </span>
              </label>
            ))}
          </div>
        </section>
        <section className="flex flex-col gap-1">
          <h3 className="type-headline">{t("moderation.recreate.limit")}</h3>
          <SegmentedControl<(typeof LIMITS)[number]> aria-label={t("moderation.recreate.limit")} size="sm" value={limit} onValueChange={setLimit} options={LIMITS.map((v) => ({ value: v, label: t("moderation.recreate.seconds", { n: v }) }))} />
        </section>
        <p className="type-footnote text-label-2">{t("moderation.recreate.policy")}</p>
        <p className="type-footnote text-label-2">{t("moderation.recreate.info")}</p>
        {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
        <SheetFooter className="flex-row justify-end gap-2 p-0">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <Button onClick={() => void start()} disabled={busy} data-testid="recreate-start" aria-busy={busy || undefined}>
            {busy ? t("busy.working") : t("moderation.recreate.start")}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
