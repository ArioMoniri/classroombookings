"use client";

import { useCallback } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api/endpoints";
import type { Constraint, ProposedConstraint } from "@/lib/api/schemas";
import type { ProposedSectionEdit, StudioRule } from "@/lib/api/studio-schemas";
import { useI18n } from "@/lib/i18n/provider";
import { useStudio } from "./studio-context";
import type { TrayItem } from "./studio-store";

export interface NewRule {
  kind: string;
  params: Record<string, unknown>;
  hardness: "hard" | "soft";
  weight: number;
  nl_text: string | null;
  source?: Constraint["source"];
}

/** Every rule mutation in the studio, each recorded on the undo stack with its inverse. */
export function useRuleActions() {
  const { t } = useI18n();
  const { termId, store, dispatch, refresh, local } = useStudio();

  const undoToast = useCallback(
    (message: string) =>
      toast.success(message, {
        duration: 8000,
        action: {
          label: t("common.undo"),
          onClick: () => {
            void store.getState().undo();
          },
        },
      }),
    [store, t],
  );

  const setOverride = useCallback(
    (rule: StudioRule, next: { hardness?: "hard" | "soft"; weight?: number }) => {
      const prev = store.getState().studio.local.rule_overrides[String(rule.id)] ?? null;
      const merged = { hardness: next.hardness ?? prev?.hardness ?? null, weight: next.weight ?? prev?.weight ?? null };
      // an override equal to the stored rule is no override
      const clean = { hardness: merged.hardness === rule.hardness ? null : merged.hardness, weight: merged.weight === rule.weight ? null : merged.weight };
      dispatch({ type: "setOverride", ruleId: rule.id, override: clean });
      store.getState().record({
        label: t("studio.history.ruleChanged"),
        undo: () => dispatch({ type: "setOverride", ruleId: rule.id, override: prev }),
        redo: () => dispatch({ type: "setOverride", ruleId: rule.id, override: clean }),
      });
    },
    [dispatch, store, t],
  );

  const setInPlay = useCallback(
    (rule: StudioRule, inPlay: boolean) => {
      dispatch({ type: "setRuleInPlay", ruleId: rule.id, inPlay });
      store.getState().record({
        label: inPlay ? t("studio.history.ruleOn") : t("studio.history.ruleOff"),
        undo: () => dispatch({ type: "setRuleInPlay", ruleId: rule.id, inPlay: !inPlay }),
        redo: () => dispatch({ type: "setRuleInPlay", ruleId: rule.id, inPlay }),
      });
    },
    [dispatch, store, t],
  );

  const updateParams = useCallback(
    async (rule: StudioRule, params: Record<string, unknown>, nlText?: string | null) => {
      const before = { params: rule.params, nl_text: rule.nl_text };
      await api.constraints.update(rule.id, { params, ...(nlText !== undefined ? { nl_text: nlText } : {}) });
      await refresh(["rules", "classes"]);
      store.getState().record({
        label: t("studio.history.ruleChanged"),
        undo: async () => {
          await api.constraints.update(rule.id, before);
          await refresh(["rules", "classes"]);
        },
        redo: async () => {
          await api.constraints.update(rule.id, { params });
          await refresh(["rules", "classes"]);
        },
      });
    },
    [refresh, store, t],
  );

  const create = useCallback(
    async (r: NewRule, label?: string): Promise<number> => {
      const body = { term_id: termId, run_id: null, kind: r.kind, params: r.params, hardness: r.hardness, weight: r.weight, source: r.source ?? "ADMIN", nl_text: r.nl_text, enabled: true } as const;
      let created = await api.constraints.create(body);
      await refresh(["rules", "classes", "summary"]);
      store.getState().record({
        label: label ?? t("studio.history.ruleAdded"),
        undo: async () => {
          await api.constraints.remove(created.id);
          await refresh(["rules", "classes", "summary"]);
        },
        redo: async () => {
          created = await api.constraints.create(body);
          await refresh(["rules", "classes", "summary"]);
        },
      });
      return created.id;
    },
    [termId, refresh, store, t],
  );

  const remove = useCallback(
    async (rule: StudioRule) => {
      await api.constraints.remove(rule.id);
      await refresh(["rules", "classes", "summary"]);
      let id = rule.id;
      const body = { term_id: termId, run_id: null, kind: rule.kind, params: rule.params, hardness: rule.hardness, weight: rule.weight, source: (["FILE", "ADMIN", "AI", "UPLOAD"].includes(rule.source) ? rule.source : "ADMIN") as Constraint["source"], nl_text: rule.nl_text, enabled: rule.enabled };
      store.getState().record({
        label: t("studio.history.ruleDeleted"),
        undo: async () => {
          id = (await api.constraints.create(body)).id;
          await refresh(["rules", "classes", "summary"]);
        },
        redo: async () => {
          await api.constraints.remove(id);
          await refresh(["rules", "classes", "summary"]);
        },
      });
      undoToast(t("studio.rules.deleted"));
    },
    [termId, refresh, store, t, undoToast],
  );

  const duplicate = useCallback(
    async (rule: StudioRule) => {
      await create({ kind: rule.kind, params: rule.params, hardness: rule.hardness, weight: rule.weight, nl_text: rule.nl_text, source: "ADMIN" }, t("studio.history.ruleDuplicated"));
      toast.success(t("studio.rules.duplicated"));
    },
    [create, t],
  );

  /** Accept review-tray items (NL proposals, upload rows, section edits) in one call. */
  const accept = useCallback(
    async (items: TrayItem[]): Promise<number> => {
      const proposals: ProposedConstraint[] = [];
      const edits: ProposedSectionEdit[] = [];
      for (const it of items) {
        if (it.type === "rule") proposals.push(it.proposal);
        else if (it.type === "edit") edits.push(it.edit);
      }
      if (!proposals.length && !edits.length) return 0;
      const res = await api.studio.accept(termId, proposals, edits);
      const keys = items.map((i) => i.key);
      store.getState().setTrayState(keys, "accepted", res.created);
      await refresh(["rules", "classes", "summary"]);
      const added = res.created.length + edits.length;
      store.getState().record({
        label: t("studio.history.accepted", { n: added }),
        undo: async () => {
          await Promise.all(res.created.map((id) => api.constraints.remove(id)));
          store.getState().setTrayState(keys, "pending");
          await refresh(["rules", "classes", "summary"]);
        },
        redo: async () => {
          const again = await api.studio.accept(termId, proposals, edits);
          store.getState().setTrayState(keys, "accepted", again.created);
          await refresh(["rules", "classes", "summary"]);
        },
      });
      if (res.rejected.length) toast.warning(t("studio.tray.someRejected", { n: res.rejected.length }), { description: res.rejected.map((r) => String(r.reason ?? r.error ?? "")).filter(Boolean).join("; ") });
      return added;
    },
    [termId, refresh, store, t],
  );

  return { setOverride, setInPlay, updateParams, create, remove, duplicate, accept, undoToast, local };
}
