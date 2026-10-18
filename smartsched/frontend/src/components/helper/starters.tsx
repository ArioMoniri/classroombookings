"use client";
/** HX-03 (helper.md §6.2): three starters for the reader's role, in the empty sheet and the empty palette. */
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { Chip } from "@/components/ui/chip";

export type StarterRole = "admin" | "planner" | "approver" | "member";

type Can = (perm: string | readonly string[] | undefined) => boolean;

/** admin > planner > approver > academician / staff (the welcome guide's precedence, simplified to 4 sets). */
export function starterRole(can: Can): StarterRole {
  if (can(["setup.users", "setup.settings", "setup.sessions", "setup.schedules"])) return "admin";
  if (can(["planning.admin", "planning.edit"])) return "planner";
  if (can("approvals.decide")) return "approver";
  return "member";
}

const KEYS: Record<StarterRole, [MessageKey, MessageKey, MessageKey]> = {
  member: ["helper.starters.member.0", "helper.starters.member.1", "helper.starters.member.2"],
  approver: ["helper.starters.approver.0", "helper.starters.approver.1", "helper.starters.approver.2"],
  admin: ["helper.starters.admin.0", "helper.starters.admin.1", "helper.starters.admin.2"],
  planner: ["helper.starters.planner.0", "helper.starters.planner.1", "helper.starters.planner.2"],
};

export function useStarters(role: StarterRole): string[] {
  const { t } = useI18n();
  return KEYS[role].map((k) => t(k));
}

/** A starter that is not a question (HB-23c: "Elimde bir dosya var, ne yapayım?" opens the file picker). */
export interface StarterAction {
  label: string;
  onPick: () => void;
}

export function Starters({ role, onPick, first, only }: { role: StarterRole; onPick: (text: string) => void; first?: StarterAction; only?: StarterAction }) {
  const { t } = useI18n();
  const questions = useStarters(role);
  const items = only ? [] : questions;
  const lead = only ?? first;
  return (
    <div className="flex flex-col gap-2" data-testid="helper-starters">
      <p className="type-footnote text-label-2">{t("helper.palette.groups.starters")}</p>
      <ul className="flex flex-wrap gap-2">
        {lead ? (
          <li>
            <Chip onClick={lead.onPick} className="min-h-11 whitespace-normal text-left" data-testid="helper-starter-file">
              {lead.label}
            </Chip>
          </li>
        ) : null}
        {items.map((s) => (
          <li key={s}>
            <Chip onClick={() => onPick(s)} className="min-h-11 whitespace-normal text-left">
              {s}
            </Chip>
          </li>
        ))}
      </ul>
    </div>
  );
}
