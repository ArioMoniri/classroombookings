"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api/endpoints";
import { useI18n } from "@/lib/i18n/provider";
import { ConfirmDialog } from "./confirm-dialog";
import { useStudio } from "./studio-context";

interface GenerateCtx {
  generate: () => Promise<void>;
  busy: boolean;
}
const Ctx = createContext<GenerateCtx | null>(null);

export function useGenerate(): GenerateCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useGenerate outside <GenerateProvider>");
  return c;
}

/** Generate = flush the draft → pre-check → (blocked? confirm) → POST /terms/{id}/studio/generate. */
export function GenerateProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const { termId, kind, flush, runPrecheck, store, summary, local, goStep } = useStudio();
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState<number | null>(null);

  const start = useCallback(async () => {
    setBusy(true);
    try {
      const parent = summary.lastGoodRunId;
      const stability = parent !== null && local.params.stability !== false;
      const res = await api.studio.generate(termId, kind, {
        label: (local.params.label as string | undefined) || null,
        params: { time_limit_s: local.params.time_limit_s, seed: local.params.seed, workers: local.params.workers, weights: local.params.weights },
        parent_run_id: stability ? parent : null,
        stability,
      });
      store.getState().setActiveRun({ runId: res.run_id, previousRunId: parent, startedAt: Date.now() });
      void qc.invalidateQueries({ queryKey: ["runs"] });
      goStep("run");
      toast.success(t("studio.run.started", { id: res.run_id }), { action: { label: t("studio.run.viewRun"), onClick: () => router.push(`/runs/${res.run_id}`) } });
      window.requestAnimationFrame(() => document.getElementById("run-status-title")?.focus());
    } catch (e) {
      toast.error(t("studio.run.startFailed", { reason: e instanceof Error ? e.message : String(e) }));
    } finally {
      setBusy(false);
    }
  }, [summary.lastGoodRunId, local.params, termId, kind, store, qc, goStep, t, router]);

  const generate = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    const ok = await flush();
    if (!ok) {
      setBusy(false);
      toast.error(t("studio.save.error"));
      return;
    }
    const p = await runPrecheck();
    setBusy(false);
    if (p && p.readiness === "blocked") {
      setBlocked(p.counts.blocked_classes ?? p.items.filter((i) => i.severity === "error").length);
      return;
    }
    // a failed pre-check never blocks Generate ("Couldn't check right now. You can still generate")
    await start();
  }, [busy, flush, runPrecheck, start, t]);

  return (
    <Ctx.Provider value={{ generate, busy }}>
      {children}
      <ConfirmDialog
        open={blocked !== null}
        onOpenChange={(v) => !v && setBlocked(null)}
        title={t("studio.check.blocked")}
        description={t("studio.check.blockedConfirm", { n: blocked ?? 0 })}
        confirmLabel={t("studio.check.fixFirst")}
        cancelLabel={t("studio.check.generateAnyway")}
        onConfirm={() => goStep("check")}
        onCancel={() => void start()}
        testId="blocked-confirm"
      />
    </Ctx.Provider>
  );
}
