"use client";
/**
 * Multi-booking (CRBS `MultiAgent`): the selected slots become a server-side selection, a dry run shows
 * what would be created and what blocks it, and the confirmation is all-or-nothing (the backend creates
 * every booking in one transaction or none).
 *
 * Per slot (CRBS multi/single_details.php, recur_defaults.php, recur_preview.php): an include checkbox,
 * notes, department and user (with `set_department` / `set_user`) with "copy to the rows below", and for
 * recurring bookings the start / end of the series plus a per-date book / skip / replace choice from the
 * dry-run preview.
 */
import { ArrowDownToLine, CalendarCheck, Loader2, Repeat } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Textarea } from "@/components/ui/textarea";
import { BOOKING_KEYS, crbs, crbsError, useBookingUsers, useCrbsMe, useCrbsMutation, useDepartments, type InstanceAction, type MultiSlotChoice, type RecurInstance, type Selection } from "@/lib/api/crbs";
import { bookingCapabilities } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { Alert, Field, Loading, SelectField } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";
import type { DateFormatter } from "./date-format";
import { parseSlotKey } from "./grid-model";

type Kind = "single" | "recurring";
interface Problem {
  mbs_id: number;
  code: string;
  message: string;
}
interface Row {
  include: boolean;
  notes: string;
  dept: string;
  user: string;
}
type Instances = Record<string, InstanceAction>;
interface SlotPreview {
  mbs_id: number;
  preview: { bookable_count: number; max_instances?: number | null; instances: RecurInstance[] };
}

const ACTION_KEYS: Record<InstanceAction, MessageKey> = { book: "crbs.recur.action.book", do_not_book: "crbs.recur.action.skip", replace: "crbs.recur.action.replace" };
const EMPTY: Row = { include: true, notes: "", dept: "", user: "" };

export function MultiBookDialog({
  open,
  onOpenChange,
  slotKeys,
  termId,
  termEnd,
  fmt,
  onBooked,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  slotKeys: string[];
  termId: number | undefined;
  termEnd?: string;
  fmt: DateFormatter;
  onBooked: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl" data-testid="multi-dialog">
        {open ? <MultiBody slotKeys={slotKeys} termId={termId} termEnd={termEnd} fmt={fmt} onClose={() => onOpenChange(false)} onBooked={onBooked} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function MultiBody({ slotKeys, termId, termEnd, fmt, onClose, onBooked }: { slotKeys: string[]; termId: number | undefined; termEnd?: string; fmt: DateFormatter; onClose: () => void; onBooked: () => void }) {
  const { t } = useI18n();
  const me = useCrbsMe();
  const caps = bookingCapabilities(me.data?.permissions);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [kind, setKind] = useState<Kind>("single");
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [perRow, setPerRow] = useState(false);
  const [shared, setShared] = useState("");
  const [problems, setProblems] = useState<Problem[] | null>(null);
  const [wouldCreate, setWouldCreate] = useState<number | null>(null);
  const [previews, setPreviews] = useState<SlotPreview[]>([]);
  const [instances, setInstances] = useState<Record<number, Instances>>({});
  const [start, setStart] = useState<{ mode: "session" | "custom"; date: string }>({ mode: "session", date: "" });
  const [end, setEnd] = useState<{ mode: "session" | "custom"; date: string }>({ mode: "session", date: "" });
  const [error, setError] = useState<string | null>(null);
  const created = useRef(false);
  const selRef = useRef<number | null>(null);
  const canDept = kind === "single" ? caps.setDepartment.single : caps.setDepartment.recurring;
  const canUser = kind === "single" ? caps.setUser.single : caps.setUser.recurring;
  const departments = useDepartments(canDept);
  const users = useBookingUsers(canUser);

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

  const slots = selection?.slots ?? [];
  const row = (id: number): Row => rows[id] ?? EMPTY;
  const patch = (id: number, p: Partial<Row>) => {
    setRows((cur) => ({ ...cur, [id]: { ...(cur[id] ?? EMPTY), ...p } }));
    setProblems(null);
    setWouldCreate(null);
  };
  const copyDown = (id: number) => {
    const from = row(id);
    const idx = slots.findIndex((s) => s.mbs_id === id);
    setRows((cur) => {
      const next = { ...cur };
      for (const s of slots.slice(idx + 1)) next[s.mbs_id] = { ...(next[s.mbs_id] ?? EMPTY), notes: from.notes, dept: from.dept, user: from.user };
      return next;
    });
  };
  const included = slots.filter((s) => row(s.mbs_id).include);

  const choices = (): MultiSlotChoice[] =>
    slots.map((s) => {
      const r = row(s.mbs_id);
      const notes = (perRow ? r.notes : shared).trim() || null;
      const c: MultiSlotChoice = { mbs_id: s.mbs_id, create: r.include, notes };
      if (canDept && r.dept !== "") c.department_id = r.dept === "none" ? null : Number(r.dept);
      if (canUser && r.user !== "") c.user_id = r.user === "none" ? null : Number(r.user);
      if (kind === "recurring") {
        c.recurring_start = start.mode === "custom" && start.date ? start.date : null;
        c.recurring_end = end.mode === "custom" && end.date ? end.date : null;
        const inst = instances[s.mbs_id];
        if (inst && Object.keys(inst).length) c.instances = Object.entries(inst).map(([date, action]) => ({ date, action }));
      }
      return c;
    });
  const dry = useCrbsMutation(() => crbs.bookings.multiDryRun(selection?.id ?? 0, kind, choices()));
  const create = useCrbsMutation(() => crbs.bookings.multiCreate(selection?.id ?? 0, kind, choices()), BOOKING_KEYS);

  const resetCheck = () => {
    setProblems(null);
    setWouldCreate(null);
    setPreviews([]);
    setInstances({});
  };

  const check = () => {
    setError(null);
    dry.mutate(undefined, {
      onSuccess: (res) => {
        if (kind === "single") {
          const p = (res.problems as Problem[] | undefined) ?? [];
          setProblems(p);
          setWouldCreate(Number(res.would_create ?? 0));
        } else {
          const list = (res.slots as SlotPreview[] | undefined) ?? [];
          setPreviews(list);
          setProblems([]);
          setWouldCreate(list.reduce((n, s) => n + Math.min(s.preview.bookable_count, s.preview.max_instances ?? Infinity), 0));
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
    const s = slots.find((x) => x.mbs_id === mbs);
    return s ? `${s.room_name} · ${fmt.weekday(s.date)} · ${s.period_name ?? ""}` : String(mbs);
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("crbs.multi.title", { n: included.length || slotKeys.length })}</DialogTitle>
        <DialogDescription>{t("crbs.multi.allOrNothing")}</DialogDescription>
      </DialogHeader>
      {!selection && !error ? <Loading /> : null}
      {selection ? (
        <div className="flex max-h-[60dvh] flex-col gap-3 overflow-y-auto pr-1">
          {selection.can_book_single && selection.can_book_recur ? (
            <SegmentedGlass<Kind>
              aria-label={t("crbs.book.kind")}
              value={kind}
              onValueChange={(v) => {
                setKind(v);
                resetCheck();
              }}
              options={[
                { value: "single", label: t("crbs.book.single"), icon: <CalendarCheck aria-hidden /> },
                { value: "recurring", label: t("crbs.book.recurring"), icon: <Repeat aria-hidden /> },
              ]}
            />
          ) : null}
          <label className="flex items-center gap-2 type-callout text-label-1">
            <Checkbox checked={perRow} onCheckedChange={(v) => setPerRow(v === true)} data-testid="multi-per-row" />
            {t("reserve.multi.perRow")}
          </label>
          <ul className="flex flex-col rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]" data-testid="multi-rows">
            {slots.map((s, i) => {
              const r = row(s.mbs_id);
              const problem = problems?.find((p) => p.mbs_id === s.mbs_id);
              const label = slotLabel(s.mbs_id);
              const prev = previews.find((p) => p.mbs_id === s.mbs_id);
              return (
                <li key={s.mbs_id} className="flex flex-col gap-2 px-3 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none" data-mbs-id={s.mbs_id}>
                  <div className="flex items-center justify-between gap-2 type-callout">
                    <label className="flex min-h-11 items-center gap-2 text-label-1 sm:min-h-0">
                      <Checkbox checked={r.include} onCheckedChange={(v) => patch(s.mbs_id, { include: v === true })} aria-label={t("reserve.multi.include", { slot: label })} data-testid={`multi-include-${s.mbs_id}`} />
                      <span className={r.include ? "" : "text-label-3 line-through"}>{label}</span>
                    </label>
                    <span className={problem ? "type-footnote font-medium text-status-infeasible-fg" : "type-footnote text-label-3"}>{problem ? t("crbs.multi.blocked") : s.status === "free" ? t("crbs.slot.free") : t("crbs.recur.status.booked")}</span>
                  </div>
                  {perRow && r.include ? (
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <div className="grid gap-2 sm:grid-cols-3">
                        <Input aria-label={`${t("crbs.book.notes")}: ${label}`} placeholder={t("crbs.book.notes")} maxLength={255} value={r.notes} onChange={(e) => patch(s.mbs_id, { notes: e.target.value })} data-testid={`multi-notes-${s.mbs_id}`} />
                        {canDept ? (
                          <SelectField aria-label={`${t("crbs.book.department")}: ${label}`} value={r.dept} onChange={(e) => patch(s.mbs_id, { dept: e.target.value })}>
                            <option value="">{t("crbs.book.departmentMine")}</option>
                            <option value="none">{t("crbs.book.departmentNone")}</option>
                            {(departments.data ?? []).map((d) => (
                              <option key={d.id} value={d.id}>
                                {d.name}
                              </option>
                            ))}
                          </SelectField>
                        ) : null}
                        {canUser ? (
                          <SelectField aria-label={`${t("crbs.book.user")}: ${label}`} value={r.user} onChange={(e) => patch(s.mbs_id, { user: e.target.value })}>
                            <option value="">{t("crbs.book.userMe")}</option>
                            <option value="none">{t("crbs.book.userNone")}</option>
                            {(users.data ?? []).map((u) => (
                              <option key={u.id} value={u.id}>
                                {u.name}
                              </option>
                            ))}
                          </SelectField>
                        ) : null}
                      </div>
                      {i < slots.length - 1 ? (
                        <Button variant="ghost" size="sm" onClick={() => copyDown(s.mbs_id)} data-testid={`multi-copy-${s.mbs_id}`}>
                          <ArrowDownToLine aria-hidden />
                          {t("reserve.multi.copyDown")}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                  {kind === "recurring" && prev && r.include ? (
                    <details className="type-footnote">
                      <summary className="cursor-pointer text-label-2">{t("reserve.multi.dates", { slot: label })}</summary>
                      <ul className="mt-1 flex flex-col gap-1">
                        {prev.preview.instances
                          .filter((x) => x.actions.length > 1)
                          .map((x) => (
                            <li key={x.date} className="flex items-center justify-between gap-2">
                              <span className="text-label-1">
                                {fmt.weekday(x.date)} · {x.held?.label ?? x.booking?.room_name ?? x.status}
                              </span>
                              <SelectField
                                aria-label={t("crbs.recur.actionFor", { date: fmt.short(x.date) })}
                                value={instances[s.mbs_id]?.[x.date] ?? x.actions[0]}
                                onChange={(e) => setInstances((cur) => ({ ...cur, [s.mbs_id]: { ...(cur[s.mbs_id] ?? {}), [x.date]: e.target.value as InstanceAction } }))}
                              >
                                {x.actions.map((a) => (
                                  <option key={a} value={a}>
                                    {t(ACTION_KEYS[a])}
                                  </option>
                                ))}
                              </SelectField>
                            </li>
                          ))}
                      </ul>
                    </details>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {kind === "recurring" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("crbs.recur.start")} htmlFor="multi-start">
                <SelectField id="multi-start" value={start.mode} onChange={(e) => (setStart((c) => ({ ...c, mode: e.target.value as "session" | "custom" })), resetCheck())}>
                  <option value="session">{t("crbs.recur.startSession")}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {start.mode === "custom" ? <Input type="date" aria-label={t("crbs.recur.startDate")} value={start.date} onChange={(e) => (setStart((c) => ({ ...c, date: e.target.value })), resetCheck())} /> : null}
              </Field>
              <Field label={t("crbs.recur.end")} htmlFor="multi-end">
                <SelectField id="multi-end" value={end.mode} onChange={(e) => (setEnd((c) => ({ ...c, mode: e.target.value as "session" | "custom" })), resetCheck())}>
                  <option value="session">{t("crbs.recur.endSession", { date: termEnd ? fmt.short(termEnd) : "" })}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {end.mode === "custom" ? <Input type="date" aria-label={t("crbs.recur.endDate")} value={end.date} onChange={(e) => (setEnd((c) => ({ ...c, date: e.target.value })), resetCheck())} /> : null}
              </Field>
            </div>
          ) : null}
          {selection.remaining_bookings != null && kind === "single" ? <p className="type-footnote text-label-2">{t("crbs.limits.remaining", { n: selection.remaining_bookings })}</p> : null}
          {!perRow ? (
            <Field label={t("crbs.book.notes")} htmlFor="multi-notes" hint={t("crbs.multi.notesHint")}>
              <Textarea id="multi-notes" maxLength={255} rows={2} value={shared} onChange={(e) => setShared(e.target.value)} />
            </Field>
          ) : null}
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
          <Button variant="outline" onClick={check} disabled={!selection || dry.isPending || !included.length} data-testid="multi-check">
            {dry.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {kind === "recurring" ? t("reserve.multi.previewDates") : t("crbs.multi.check")}
          </Button>
        ) : (
          <Button onClick={confirm} disabled={create.isPending || !included.length} data-testid="multi-confirm">
            {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.multi.confirm", { n: wouldCreate ?? included.length })}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
