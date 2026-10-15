"use client";
/**
 * The requester's side of P1 in My bookings: my requests (GET /approvals/mine), newest first, each with its
 * timeline, a Withdraw button while it is open and, when it was rejected, the rooms the approver (or the
 * service) suggested, each opening Find a room prefilled. `?request=<id>` (the in-app notification) opens
 * and scrolls to that request. Without any request the section is not shown (CRBS default: no approvals).
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Search, Undo2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog, SectionTitle } from "@/components/admin/kit";
import type { DateFormatter } from "@/components/bookings/date-format";
import { APPROVAL_KEYS, errorText, pickLang, suggestionsOf, useMyRequests, wave1, wave1Error, type ApprovalRequest } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { isOpen, requestSlots, suggestionRooms } from "./approvals-model";
import { RequestTimeline, SlotLine, StatusPill } from "./request-parts";

export function MyRequests({ fmt }: { fmt: DateFormatter }) {
  const { t } = useI18n();
  const mine = useMyRequests();
  const params = useSearchParams();
  const asked = Number(params.get("request")) || null;
  const rows = mine.data ?? [];
  if (!rows.length) return null;
  const open = rows.filter(isOpen).length;
  return (
    <section aria-labelledby="mine-requests" data-testid="my-requests">
      <SectionTitle id="mine-requests">
        {t("wave1.mine.title")}
        {open ? <span className="ml-2 type-callout font-normal text-label-2">{t("wave1.mine.openN", { n: open })}</span> : null}
      </SectionTitle>
      <Card variant="glass" className="gap-0 overflow-hidden py-0">
        <ul>
          {rows.map((r) => (
            <RequestRow key={r.id} req={r} fmt={fmt} initiallyOpen={r.id === asked} />
          ))}
        </ul>
      </Card>
    </section>
  );
}

function RequestRow({ req: r, fmt, initiallyOpen }: { req: ApprovalRequest; fmt: DateFormatter; initiallyOpen: boolean }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(initiallyOpen);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (initiallyOpen) ref.current?.scrollIntoView?.({ block: "center" });
  }, [initiallyOpen]);
  const suggestions = r.status === "REJECTED" ? suggestionRooms(suggestionsOf(r)) : [];
  const { first } = requestSlots(r);
  const withdraw = async () => {
    setBusy(true);
    try {
      await wave1.approvals.withdraw(r.id);
      await Promise.all(APPROVAL_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      toast.success(t("wave1.mine.withdrawn"));
      setConfirm(false);
    } catch (e) {
      toast.error(errorText(wave1Error(e), locale));
    } finally {
      setBusy(false);
    }
  };
  const findHref = (date: string | null) => {
    const q = new URLSearchParams();
    if (date ?? first?.date) q.set("date", (date ?? first?.date)!);
    if (first?.headcount) q.set("headcount", String(first.headcount));
    return `/find-room?${q.toString()}`;
  };
  const panel = `req-panel-${r.id}`;
  return (
    <li ref={ref} className={cn("shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none", initiallyOpen && "bg-tint-soft/40")} data-request-id={r.id} data-status={r.status}>
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        aria-expanded={expanded}
        aria-controls={panel}
        className="flex w-full items-center gap-3 px-4 py-3 text-left outline-none hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)"
        data-testid={`my-request-${r.id}`}
      >
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="type-headline text-label-1">{r.room_name}</span>
            <StatusPill status={r.status} />
          </span>
          <SlotLine req={r} fmt={fmt} className="block type-footnote text-label-2" />
        </span>
        <ChevronDown className={cn("size-4 shrink-0 text-label-3 transition-transform duration-(--dur-fast)", expanded && "rotate-180")} aria-hidden />
      </button>
      {expanded ? (
        <div id={panel} className="flex flex-col gap-3 px-4 pb-4">
          <RequestTimeline req={r} fmt={fmt} />
          {suggestions.length ? (
            <div className="flex flex-col gap-1.5" data-testid="request-suggestions">
              <p className="type-footnote font-medium text-label-2">{t("wave1.mine.suggested")}</p>
              <ul className="flex flex-col gap-1">
                {suggestions.map((s) => (
                  <li key={`${s.roomId}-${s.date}-${s.start}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-fill-3 px-3 py-2">
                    <span className="min-w-0">
                      <span className="block type-callout text-label-1">
                        {s.name}
                        {s.date ? <span className="ml-1.5 type-footnote text-label-3 tabular-nums">{fmt.short(s.date)}{s.start ? ` · P${s.start}${s.end && s.end !== s.start ? `–P${s.end}` : ""}` : ""}</span> : null}
                      </span>
                      {s.reason ? <span className="block type-footnote text-label-2">{pickLang(s.reason, locale)}</span> : null}
                    </span>
                    <Button size="sm" variant="outline" render={<Link href={findHref(s.date)} />} nativeButton={false}>
                      <Search aria-hidden />
                      {t("wave1.mine.findAgain")}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {isOpen(r) ? (
            <Button variant="outline" className="self-start" onClick={() => setConfirm(true)} data-testid={`withdraw-${r.id}`}>
              <Undo2 aria-hidden />
              {t("wave1.mine.withdraw")}
            </Button>
          ) : null}
        </div>
      ) : null}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t("wave1.mine.withdrawTitle", { room: r.room_name ?? "" })}
        description={t("wave1.mine.withdrawBody")}
        confirmLabel={busy ? t("crbs.common.loading") : t("wave1.mine.withdraw")}
        destructive
        busy={busy}
        onConfirm={() => void withdraw()}
      />
    </li>
  );
}
