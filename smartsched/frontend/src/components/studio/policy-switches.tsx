"use client";

import { Shield } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api/endpoints";
import type { StudioRule } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useStudio } from "./studio-context";
import { effectiveRules } from "./studio-reducer";
import { useRuleActions } from "./use-rule-actions";
import { pairLang } from "@/lib/i18n";

interface Policy {
  id: string;
  label: MessageKey;
  match: (r: StudioRule) => boolean;
  make: (programs: string[]) => { kind: string; params: Record<string, unknown>; hardness: "hard" | "soft"; weight: number };
}

/** (g) One-click common university policies; each is a normal rule card once on. */
export const POLICIES: Policy[] = [
  {
    id: "tip",
    label: "studio.policy.tip",
    match: (r) => r.kind === "room_tags" && Array.isArray(r.params.forbidden_tags) && (r.params.forbidden_tags as unknown[]).includes("TIP"),
    make: (programs) => ({ kind: "room_tags", params: { forbidden_tags: ["TIP"], programs: programs.filter((p) => p !== "Tıp") }, hardness: "hard", weight: 5 }),
  },
  {
    id: "evening",
    label: "studio.policy.evening",
    match: (r) => r.kind === "evening_programs_in_buildings",
    make: () => ({ kind: "evening_programs_in_buildings", params: { buildings: ["B", "C"] }, hardness: "soft", weight: 5 }),
  },
  {
    id: "sameRoom",
    label: "studio.policy.sameRoom",
    match: (r) => r.kind === "same_room_across_weeks" && !["event_ids", "programs", "cohorts", "program", "cohort", "match"].some((k) => k in r.params),
    make: () => ({ kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5 }),
  },
  {
    id: "fit",
    label: "studio.policy.fit",
    match: (r) => r.kind === "min_capacity_waste",
    make: () => ({ kind: "min_capacity_waste", params: { unit: 10 }, hardness: "soft", weight: 2 }),
  },
];

export function PolicySwitches() {
  const { t } = useI18n();
  const { rules, local, sentence, refresh } = useStudio();
  const actions = useRuleActions();
  const [busy, setBusy] = useState<string | null>(null);
  const eff = effectiveRules(rules?.rules ?? [], local);

  const toggle = async (p: Policy, on: boolean) => {
    setBusy(p.id);
    try {
      const existing = eff.filter((e) => p.match(e.rule));
      if (on) {
        const off = existing.find((e) => !e.inPlay);
        if (off && !off.rule.enabled) {
          await api.constraints.update(off.rule.id, { enabled: true });
          await refresh(["rules"]);
        }
        if (off) actions.setInPlay(off.rule, true);
        else await actions.create({ ...p.make(sentence.programs), nl_text: t(p.label), source: "ADMIN" });
      } else {
        for (const e of existing.filter((x) => x.inPlay)) actions.setInPlay(e.rule, false);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <fieldset className="rounded-2xl bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)] p-3" data-testid="policy-switches">
      <legend className="px-1 text-sm font-medium">{t("studio.policy.title")}</legend>
      <ul className="grid gap-2 sm:grid-cols-2">
        {POLICIES.map((p) => {
          const on = eff.some((e) => e.inPlay && p.match(e.rule));
          return (
            <li key={p.id}>
              <label className="flex min-h-9 cursor-pointer items-center gap-2.5 text-sm pointer-coarse:min-h-11">
                <Switch checked={on} disabled={busy !== null || !rules} onCheckedChange={(v) => void toggle(p, v)} data-testid={`policy-${p.id}`} />
                <span>{t(p.label)}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

/** Built-in basics (no double-booking, capacity, no clash for a programme-year / instructor). */
export function BuiltinRules() {
  const { t, locale } = useI18n();
  const { rules, local, dispatch, store, isAdmin } = useStudio();
  const list = rules?.builtins ?? [];
  return (
    <ul className="space-y-2" data-testid="builtin-rules">
      {list.map((b) => {
        const enabled = !local.disabled_builtin_kinds.includes(b.kind);
        const reason = !b.disableable ? t("studio.builtin.always") : !isAdmin ? t("studio.builtin.adminOnly") : null;
        return (
          <li key={b.kind} className="flex items-center gap-3 rounded-[var(--radius-md)] border bg-fill-3 p-3 text-sm">
            <Shield className="size-4 shrink-0 text-label-2" aria-hidden />
            <span className="min-w-0 flex-1">
              {b.title[pairLang(locale)] || b.title.en}
              {reason ? <span className="block text-xs text-label-2">{reason}</span> : null}
              {!enabled ? <span className="block text-xs text-status-warning-fg">{t("studio.builtin.offWarning")}</span> : null}
            </span>
            <Switch
              checked={enabled}
              disabled={reason !== null}
              aria-label={`${b.title[pairLang(locale)] || b.title.en}: ${enabled ? t("studio.builtin.on") : t("studio.builtin.off")}`}
              onCheckedChange={(v) => {
                dispatch({ type: "setBuiltin", kind: b.kind, enabled: v });
                store.getState().record({ label: t("studio.history.builtin"), undo: () => dispatch({ type: "setBuiltin", kind: b.kind, enabled: !v }), redo: () => dispatch({ type: "setBuiltin", kind: b.kind, enabled: v }) });
              }}
            />
          </li>
        );
      })}
    </ul>
  );
}
