"use client";
/**
 * Yönetim › Ayarlar › Rezervasyonlar › Rezervasyon onayı (F-01 S01, F-11 S07): the organisation setting
 * `bookings.approval_mode` (`PUT /org/settings {"approval_mode": "rules" | "all"}`, backend
 * `app/services/approvals.py`):
 * - `rules` — only rooms with an approval rule go to an approver (the CRBS default of empty installs);
 * - `all` — every request for a free slot goes to an administrator first, who approves or rejects with a reason.
 * Who books directly in both modes: approvers (`approvals.decide`), planning administrators and roles holding
 * `bookings.skip_approval` (granted in Yönetim › Roller, never beyond what the granting admin holds).
 *
 * A controlled field group: the organisation form owns the draft, the unsaved-changes guard and the save bar.
 */
import Link from "next/link";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export type ApprovalMode = "rules" | "all";

export function BookingApprovalFields({ value, onChange, className }: { value: ApprovalMode; onChange: (mode: ApprovalMode) => void; className?: string }) {
  const { t } = useI18n();
  const modes: { value: ApprovalMode; label: string; hint: string }[] = [
    { value: "rules", label: t("approvals.mode.rules"), hint: t("approvals.mode.rulesHint") },
    { value: "all", label: t("approvals.mode.all"), hint: t("approvals.mode.allHint") },
  ];
  return (
    <div className={cn("flex flex-col gap-3 py-3.5", className)} data-testid="approval-mode">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <p id="approval-mode-label" className="type-callout font-medium text-label-1">
            {t("approvals.mode.title")}
          </p>
          <p className="type-footnote text-label-2">{t("approvals.mode.lead")}</p>
        </div>
        <SegmentedControl<ApprovalMode>
          semantics="radiogroup"
          aria-labelledby="approval-mode-label"
          aria-describedby="approval-mode-hints"
          value={value}
          onValueChange={onChange}
          options={modes.map((m) => ({ value: m.value, label: m.label, text: m.label, testId: `approval-mode-${m.value}` }))}
          className="sm:shrink-0"
          data-testid="approval-mode-control"
        />
      </div>
      <ul id="approval-mode-hints" className="flex flex-col gap-1.5">
        {modes.map((m) => (
          <li key={m.value} className={cn("rounded-lg px-3 py-2 type-footnote", value === m.value ? "bg-tint-soft text-label-1" : "text-label-2")} data-active={value === m.value || undefined}>
            <span className="font-medium">{m.label}:</span> {m.hint}
          </li>
        ))}
      </ul>
      <p className="type-footnote text-label-2" data-testid="approval-mode-direct">
        {t("approvals.mode.direct", { perm: t("approvals.perm.bookings_skip_approval") })}{" "}
        <Link href="/admin/roles" className="text-tint-text underline-offset-2 hover:underline">
          {t("approvals.mode.rolesLink")}
        </Link>
        {" · "}
        <Link href="/admin/approval-rules" className="text-tint-text underline-offset-2 hover:underline">
          {t("approvals.mode.rulesLink")}
        </Link>
      </p>
    </div>
  );
}
