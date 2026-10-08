"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api/endpoints";
import { sk } from "@/lib/api/studio-hooks";
import type { ClassRow, Fix, MeetingPatch, PrecheckItem } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { useStudio } from "./studio-context";
import { pairLang } from "@/lib/i18n";

const num = (v: unknown): number[] => (Array.isArray(v) ? v.map(Number).filter(Number.isFinite) : []);

/** Apply a pre-check fix into the draft (exclusion, class edit, per-draft rule switch) and undo it. */
export function useApplyFix() {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const { termId, kind, store, dispatch, flush, refresh, classes } = useStudio();
  const [busy, setBusy] = useState<string | null>(null);

  const apply = useCallback(
    async (item: PrecheckItem, fix: Fix): Promise<boolean> => {
      setBusy(`${item.id}:${fix.option}`);
      try {
        await flush();
        const before = store.getState().studio.local;
        const payload = fix.action.payload;
        // remember what the fix overwrites so undo can put it back
        const reqIds = num(payload.request_ids);
        const patch = (payload.patch ?? {}) as Record<string, unknown>;
        const prevRows: ClassRow[] = (classes ?? []).filter((c) => reqIds.includes(c.id));
        const res = await api.studio.applyFix(termId, kind, item.id, fix.option);
        dispatch({ type: "saved", draft: res.draft, sent: [] });
        qc.setQueryData(sk.draft(termId, kind), res.draft);
        store.getState().setPrecheck(res.precheck);
        await refresh(fix.action.type === "meeting_update" || fix.action.type === "exam_update" ? ["classes", "summary", "rules"] : ["summary", "rules"]);
        const label = fix.label[pairLang(locale)] || fix.label.en;
        store.getState().record({
          label,
          undo: async () => {
            if (fix.action.type === "meeting_update" && prevRows.length) {
              const items = prevRows.map((r) => ({ id: r.id, patch: Object.fromEntries(Object.keys(patch).map((k) => [k, k === "locked" ? r.locked : (r as unknown as Record<string, unknown>)[k]])) as MeetingPatch }));
              await api.studio.bulkEdit({ items });
              await refresh(["classes", "summary"]);
            }
            dispatch({ type: "setExcluded", ids: before.excluded });
            // unlock / room / seat fixes live on the draft pins
            dispatch({ type: "setPins", pins: before.pins });
            for (const [id, ov] of Object.entries(before.rule_overrides)) dispatch({ type: "setOverride", ruleId: Number(id), override: ov });
            const nowOv = store.getState().studio.local.rule_overrides;
            for (const id of Object.keys(nowOv)) if (!(id in before.rule_overrides)) dispatch({ type: "setOverride", ruleId: Number(id), override: null });
            const off = new Set(before.disabled_rule_ids);
            for (const id of store.getState().studio.local.disabled_rule_ids) if (!off.has(id)) dispatch({ type: "setRuleInPlay", ruleId: id, inPlay: true });
          },
          redo: async () => {
            await flush();
            const p = await api.studio.precheck(termId, kind);
            store.getState().setPrecheck(p);
            const again = p.items.find((x) => x.id === item.id);
            if (again) {
              const r = await api.studio.applyFix(termId, kind, item.id, fix.option);
              dispatch({ type: "saved", draft: r.draft, sent: [] });
              store.getState().setPrecheck(r.precheck);
              await refresh();
            }
          },
        });
        toast.success(t("studio.check.fixed", { label }), { action: { label: t("common.undo"), onClick: () => void store.getState().undo() }, duration: 8000 });
        return true;
      } catch (e) {
        toast.error(t("studio.check.fixFailed", { reason: e instanceof Error ? e.message : String(e) }));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [flush, store, classes, termId, kind, dispatch, qc, refresh, locale, t],
  );

  return { apply, busy };
}
