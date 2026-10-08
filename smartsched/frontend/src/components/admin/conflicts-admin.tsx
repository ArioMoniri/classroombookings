"use client";
/**
 * /admin/conflicts (planners, `planning.view`): active bookings that the published timetable or a block now
 * overlaps — what CRBS never had, because CRBS has no timetable. Publishing a run does not cancel anyone's
 * booking; this list shows the clashes so a planner can open each booking and edit or cancel it with a reason
 * (the detail sheet carries the same permissions and scopes as the grid).
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { crbs, crbsError, useBookingConflicts, useBookingContext } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { BookingDetailSheet } from "@/components/bookings/booking-detail-sheet";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { groupConflicts, periodSpan, summariseConflicts, type ConflictHolder } from "./conflicts-model";
import { Alert, Field, Loading, PageTitle, SelectField } from "./kit";

const KIND: Record<ConflictHolder["kind"], { key: MessageKey; tone: "locked" | "warning" | "tint" }> = {
  timetable: { key: "crbs.conflicts.kind.timetable", tone: "locked" },
  block: { key: "crbs.conflicts.kind.block", tone: "warning" },
  booking: { key: "crbs.conflicts.kind.booking", tone: "tint" },
};

export function ConflictsAdmin() {
  const { t, n } = useI18n();
  const fmt = useBookingFormat();
  const ctx = useBookingContext();
  // "" = the current session (CRBS default), "all" = every session
  const [pick, setPick] = useState<string>("");
  const termId = pick === "all" ? undefined : pick ? Number(pick) : (ctx.data?.current_term_id ?? undefined);
  const q = useBookingConflicts(termId, ctx.isSuccess);
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), retry: false });
  const [open, setOpen] = useState<number | null>(null);

  const roomName = useMemo(() => {
    const m = new Map((rooms.data ?? []).map((r) => [r.id, r.name || r.code]));
    return (id: number) => m.get(id) ?? `#${id}`;
  }, [rooms.data]);
  const rows = useMemo(() => groupConflicts(q.data ?? [], roomName), [q.data, roomName]);
  const sum = summariseConflicts(rows);

  return (
    <div className="flex flex-col gap-5">
      <PageTitle
        title={t("crbs.admin.conflicts.title")}
        subtitle={t("crbs.admin.conflicts.lead")}
        actions={
          <Button variant="secondary" size="sm" onClick={() => q.refetch()} disabled={q.isFetching} data-testid="conflicts-refresh">
            <RefreshCw aria-hidden className={q.isFetching ? "motion-safe:animate-spin" : undefined} />
            {t("crbs.conflicts.refresh")}
          </Button>
        }
      />
      <div className="max-w-xs">
        <Field label={t("crbs.export.session")} htmlFor="conflicts-term">
          <SelectField id="conflicts-term" value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">{t("crbs.conflicts.currentSession")}</option>
            {(ctx.data?.sessions ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
            <option value="all">{t("crbs.conflicts.allSessions")}</option>
          </SelectField>
        </Field>
      </div>

      {q.isError ? <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert> : null}

      {q.isSuccess && rows.length > 0 ? (
        <Alert tone="warning" testId="conflicts-summary">
          {t("crbs.conflicts.summary", { bookings: n(sum.bookings), rooms: n(sum.rooms), days: n(sum.days) })} {t("crbs.conflicts.hint")}
        </Alert>
      ) : null}

      <Card variant="glass" className="py-0">
        {q.isLoading || ctx.isLoading ? <Loading className="px-4" /> : null}
        {q.isSuccess && rows.length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2" data-testid="conflicts-empty">
            {t("crbs.conflicts.none")}
          </p>
        ) : null}
        {rows.length > 0 ? (
          <ul data-testid="conflicts-list" aria-label={t("crbs.admin.conflicts.title")}>
            {rows.map((r) => (
              <li key={r.bookingId} className="shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                <button
                  type="button"
                  onClick={() => setOpen(r.bookingId)}
                  aria-label={t("crbs.conflicts.open", { id: r.bookingId, room: roomName(r.roomId), date: fmt.long(r.date) })}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left outline-none hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block type-headline text-label-1">
                      {roomName(r.roomId)} <span className="type-footnote font-normal text-label-2">· {fmt.long(r.date)}</span>
                    </span>
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {r.holders.map((h) => (
                        <Badge key={`${h.kind}-${h.id}`} variant="secondary" tone={KIND[h.kind].tone}>
                          {t(KIND[h.kind].key)} · {h.label} · {t("crbs.conflicts.periods", { span: periodSpan(h) })}
                          {h.run_id ? ` · ${t("crbs.conflicts.run", { id: h.run_id })}` : ""}
                        </Badge>
                      ))}
                    </span>
                  </span>
                  <span className="shrink-0 type-footnote text-label-3 tabular-nums">#{r.bookingId}</span>
                  <ChevronRight className="mt-0.5 size-4 shrink-0 text-label-3" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
      <BookingDetailSheet bookingId={open} onOpenChange={(o) => !o && setOpen(null)} fmt={fmt} />
    </div>
  );
}
