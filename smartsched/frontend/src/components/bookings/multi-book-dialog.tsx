"use client";
/**
 * Multi-booking (CRBS `MultiAgent`): the selected slots become a server-side selection, a dry run shows
 * what would be created and what blocks it, and the confirmation is all-or-nothing (the backend creates
 * every booking in one transaction or none).
 */
import { Loader2, Repeat, CalendarCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Textarea } from "@/components/ui/textarea";
import { BOOKING_KEYS, crbs, crbsError, useCrbsMutation, type Selection } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";
import type { DateFormatter } from "./date-format";
import { parseSlotKey } from "./grid-model";

type Kind = "single" | "recurring";
interface Problem {
  mbs_id: number;
  code: string;
  message: string;
}

export function MultiBookDialog({
  open,
  onOpenChange,
  slotKeys,
  termId,
  fmt,
  onBooked,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  slotKeys: string[];
  termId: number | undefined;
  fmt: DateFormatter;
  onBooked: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="multi-dialog">
        {open ? <MultiBody slotKeys={slotKeys} termId={termId} fmt={fmt} onClose={() => onOpenChange(false)} onBooked={onBooked} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function MultiBody({ slotKeys, termId, fmt, onClose, onBooked }: { slotKeys: string[]; termId: number | undefined; fmt: DateFormatter; onClose: () => void; onBooked: () => void }) {
  const { t } = useI18n();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [kind, setKind] = useState<Kind>("single");
  const [notes, setNotes] = useState("");
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [wouldCreate, setWouldCreate] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const created = useRef(false);
  const selRef = useRef<number | null>(null);

  const make = useCrbsMutation(() => crbs.bookings.select(slotKeys.map(parseSlotKey), termId));
  const makeMutate = make.mutate;
  useEffect(() => {
    makeMutate(undefined, {
      onSuccess: (sel) => {
        selRef.current = sel.id;
        setSelection(sel);
        setKind(sel.can_book_single ? "single" : "recurring");
      },
      onError: (e) => setError(bookingErrorMessage(crbsError(e), t, { formatDate: fmt.short })),
    });
    return () => {
      // an abandoned selection is dropped server-side (CRBS keeps it until the next selection)
      if (selRef.current !== null && !created.current) void crbs.bookings.dropSelection(selRef.current).catch(() => undefined);
    };
    // the selection is made once per opening
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const choices = () => (selection?.slots ?? []).map((s) => ({ mbs_id: s.mbs_id, notes: notes.trim() || null }));
  const dry = useCrbsMutation(() => crbs.bookings.multiDryRun(selection?.id ?? 0, kind, choices()));
  const create = useCrbsMutation(() => crbs.bookings.multiCreate(selection?.id ?? 0, kind, choices()), BOOKING_KEYS);

  const check = () => {
    setError(null);
    dry.mutate(undefined, {
      onSuccess: (res) => {
        if (kind === "single") {
          const p = (res.problems as Problem[] | undefined) ?? [];
          setProblems(p);
          setWouldCreate(Number(res.would_create ?? 0));
        } else {
          const slots = (res.slots as { mbs_id: number; preview: { bookable_count: number; max_instances?: number | null } }[] | undefined) ?? [];
          setProblems([]);
          setWouldCreate(slots.reduce((n, s) => n + Math.min(s.preview.bookable_count, s.preview.max_instances ?? Infinity), 0));
        }
      },
      onError: (e) => setError(bookingErrorMessage(crbsError(e), t, { formatDate: fmt.short })),
    });
  };

  const confirm = () => {
    setError(null);
    create.mutate(undefined, {
      onSuccess: (res) => {
        created.current = true;
        const n = Array.isArray(res.created) ? res.created.length : Array.isArray(res.series) ? (res.series as { created?: unknown[] }[]).reduce((a, s) => a + (s.created?.length ?? 0), 0) : 0;
        toast.success(t("crbs.multi.done", { n }));
        onBooked();
        onClose();
      },
      onError: (e) => {
        const err = crbsError(e);
        const p = (err.data.problems as Problem[] | undefined) ?? null;
        if (p) setProblems(p);
        setError(bookingErrorMessage(err, t, { formatDate: fmt.short }));
      },
    });
  };

  const slotLabel = (mbs: number) => {
    const s = selection?.slots.find((x) => x.mbs_id === mbs);
    return s ? `${s.room_name} · ${fmt.weekday(s.date)} · ${s.period_name ?? ""}` : String(mbs);
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("crbs.multi.title", { n: slotKeys.length })}</DialogTitle>
        <DialogDescription>{t("crbs.multi.allOrNothing")}</DialogDescription>
      </DialogHeader>
      {!selection && !error ? <Loading /> : null}
      {selection ? (
        <div className="flex flex-col gap-3">
          {selection.can_book_single && selection.can_book_recur ? (
            <SegmentedGlass<Kind>
              aria-label={t("crbs.book.kind")}
              value={kind}
              onValueChange={(v) => {
                setKind(v);
                setProblems(null);
                setWouldCreate(null);
              }}
              options={[
                { value: "single", label: t("crbs.book.single"), icon: <CalendarCheck aria-hidden /> },
                { value: "recurring", label: t("crbs.book.recurring"), icon: <Repeat aria-hidden /> },
              ]}
            />
          ) : null}
          <ul className="flex max-h-48 flex-col overflow-auto rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)] scrollbar-thin">
            {selection.slots.map((s) => {
              const problem = problems?.find((p) => p.mbs_id === s.mbs_id);
              return (
                <li key={s.mbs_id} className="flex items-center justify-between gap-2 px-3 py-1.5 type-callout shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                  <span className="text-label-1">
                    {s.room_name} · {fmt.weekday(s.date)} · {s.period_name}
                  </span>
                  <span className={problem ? "type-footnote font-medium text-status-infeasible-fg" : "type-footnote text-label-3"}>{problem ? t("crbs.multi.blocked") : s.status === "free" ? t("crbs.slot.free") : t("crbs.recur.status.booked")}</span>
                </li>
              );
            })}
          </ul>
          {selection.remaining_bookings != null && kind === "single" ? <p className="type-footnote text-label-2">{t("crbs.limits.remaining", { n: selection.remaining_bookings })}</p> : null}
          <Field label={t("crbs.book.notes")} htmlFor="multi-notes" hint={t("crbs.multi.notesHint")}>
            <Textarea id="multi-notes" maxLength={255} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          {problems && problems.length ? (
            <Alert tone="error" title={t("crbs.multi.problems", { n: problems.length })}>
              <ul className="list-disc pl-4">
                {problems.map((p) => (
                  <li key={p.mbs_id}>{slotLabel(p.mbs_id)}</li>
                ))}
              </ul>
            </Alert>
          ) : null}
          {problems && !problems.length && wouldCreate !== null ? <Alert tone="success">{t("crbs.multi.ready", { n: wouldCreate })}</Alert> : null}
        </div>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        {problems === null || problems.length ? (
          <Button variant="outline" onClick={check} disabled={!selection || dry.isPending} data-testid="multi-check">
            {dry.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.multi.check")}
          </Button>
        ) : (
          <Button onClick={confirm} disabled={create.isPending} data-testid="multi-confirm">
            {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.multi.confirm", { n: wouldCreate ?? slotKeys.length })}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
