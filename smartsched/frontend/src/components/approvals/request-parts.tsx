"use client";
/**
 * Shared pieces of an approval request (P1): the status pill (glyph + word, never colour alone), the slot
 * line ("A 202 · Çar 18.02.2026 · 3.–5. ders") and the timeline (requested → decisions → waiting / final)
 * that both the approver inbox and the requester's My bookings show.
 */
import { Ban, CheckCircle2, CircleDot, Clock3, Hourglass, Send, Undo2, XCircle, type LucideIcon } from "lucide-react";
import type { ApprovalRequest } from "@/lib/api/wave1";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { DateFormatter } from "@/components/bookings/date-format";
import { requestSlots, statusTone, timeline, type Tone } from "./approvals-model";

const TONE_CLASS: Record<Tone, string> = {
  pending: "bg-tint-soft text-tint-text",
  ok: "bg-status-feasible text-status-feasible-fg",
  bad: "bg-status-infeasible text-status-infeasible-fg",
  muted: "bg-fill-2 text-label-2",
};
const STATUS_ICON: Record<string, LucideIcon> = { PENDING: Hourglass, APPROVED: CheckCircle2, BOOKED: CheckCircle2, REJECTED: XCircle, EXPIRED: Clock3, WITHDRAWN: Undo2, CANCELLED: Ban };
export const STATUS_KEY: Record<string, MessageKey> = {
  PENDING: "wave1.approvals.status.PENDING",
  APPROVED: "wave1.approvals.status.APPROVED",
  BOOKED: "wave1.approvals.status.APPROVED",
  REJECTED: "wave1.approvals.status.REJECTED",
  EXPIRED: "wave1.approvals.status.EXPIRED",
  WITHDRAWN: "wave1.approvals.status.WITHDRAWN",
  CANCELLED: "crbs.status.cancelled",
};

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const { t } = useI18n();
  const Icon = STATUS_ICON[status] ?? CircleDot;
  return (
    <span className={cn("inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 type-caption font-medium", TONE_CLASS[statusTone(status)], className)} data-status={status}>
      <Icon className="size-3.5" aria-hidden />
      {STATUS_KEY[status] ? t(STATUS_KEY[status]!) : status}
    </span>
  );
}

/** "Wed 18.02.2026 · P3 (10:10–11:00)" plus "+ 13 more dates" for a series. */
export function SlotLine({ req, fmt, className }: { req: ApprovalRequest; fmt: DateFormatter; className?: string }) {
  const { t } = useI18n();
  const { dates, first, periods } = requestSlots(req);
  if (!first) return null;
  const time = first.time_start && first.time_end ? ` (${fmt.time(first.time_start)}–${fmt.time(first.time_end)})` : "";
  return (
    <span className={cn("tabular-nums", className)}>
      {fmt.weekday(first.date)} · {periods}
      {time}
      {dates.length > 1 ? ` · ${t("wave1.approvals.moreDates", { n: dates.length - 1 })}` : ""}
    </span>
  );
}

export function RequestTimeline({ req, fmt }: { req: ApprovalRequest; fmt: DateFormatter }) {
  const { t } = useI18n();
  const items = timeline(req);
  return (
    <ol className="relative flex flex-col gap-3 pl-6" aria-label={t("wave1.approvals.timeline")} data-testid="request-timeline">
      <span aria-hidden className="absolute top-2 bottom-2 left-[9px] w-px bg-(--hairline)" />
      {items.map((e, i) => {
        const at = "at" in e && e.at ? fmt.dateTime(e.at) : null;
        let icon: LucideIcon = CircleDot;
        let tone = "text-label-3";
        let title = "";
        let body: string | null = null;
        if (e.kind === "requested") {
          icon = Send;
          title = e.by ? t("wave1.approvals.tl.requestedBy", { name: e.by }) : t("wave1.approvals.tl.requested");
        } else if (e.kind === "decision") {
          icon = e.decision === "approve" ? CheckCircle2 : XCircle;
          tone = e.decision === "approve" ? "text-status-feasible-fg" : "text-status-infeasible-fg";
          title = t(e.decision === "approve" ? "wave1.approvals.tl.approvedBy" : "wave1.approvals.tl.rejectedBy", { name: e.by ?? "—" });
          if (req.steps > 1) title += ` · ${t("wave1.approvals.stepN", { n: e.step, of: req.steps })}`;
          const alt = e.alternative;
          const altText = alt && typeof alt.room_name === "string" ? t("wave1.approvals.tl.alternative", { room: alt.room_name, date: typeof alt.date === "string" ? fmt.short(alt.date) : "", periods: `P${String(alt.start_period ?? "")}–P${String(alt.end_period ?? "")}` }) : null;
          body = [e.note, altText].filter(Boolean).join(" · ") || null;
        } else if (e.kind === "waiting") {
          icon = Hourglass;
          tone = "text-tint-text";
          title = e.steps > 1 ? t("wave1.approvals.tl.waitingStep", { n: e.step, of: e.steps }) : t("wave1.approvals.tl.waiting");
          body = [e.approvers.length ? t("wave1.approvals.tl.approvers", { names: e.approvers.join(", ") }) : null, e.expires ? t("wave1.approvals.tl.expires", { when: fmt.dateTime(e.expires) }) : null].filter(Boolean).join(" · ") || null;
        } else {
          icon = STATUS_ICON[e.status] ?? CircleDot;
          tone = e.status === "APPROVED" ? "text-status-feasible-fg" : e.status === "REJECTED" ? "text-status-infeasible-fg" : "text-label-2";
          title = t(STATUS_KEY[e.status] ?? "wave1.approvals.status.EXPIRED");
        }
        const Icon = icon;
        return (
          <li key={i} className="relative" data-kind={e.kind}>
            <span aria-hidden className={cn("absolute top-0.5 -left-6 flex size-[19px] items-center justify-center rounded-full bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]", tone)}>
              <Icon className="size-3" />
            </span>
            <p className="type-callout text-label-1">{title}</p>
            {body ? <p className="type-footnote text-label-2">{body}</p> : null}
            {at ? <p className="type-caption text-label-3 tabular-nums">{at}</p> : null}
          </li>
        );
      })}
    </ol>
  );
}
