"use client";
/**
 * /approvals (P1, docs/product/wave1-api.md §4): the inbox of designated approvers (`approvals.decide`).
 * Open requests whose current step the approver decides, and the ones they decided. A request opens in a
 * drawer: who asked, for what (dates, periods, headcount, notes), the room's day, competing requests for the
 * same slot, the timeline; Approve (A), Reject (D) with a note, or Another room (R): approve in another free
 * room, or reject and suggest it. A series can be approved for some dates only (the others are declined).
 * Approving re-checks the slot on the backend: a 409 shows the reason and the free alternatives to approve in.
 *
 * Deep link: `?request=<id>` (the in-app notification); approver links for a multi-period submission also carry
 * `&group=<id>` (`data.group_id`, `data.request_ids`): the drawer opens the submission's first open period with
 * the whole submission in the group bar, so one click decides all of it. Rejecting always asks for a reason code
 * and a written reason (RejectDialog; owner requirement 2026-10-15). Withdrawn and expired requests the approver
 * was asked to decide are listed under "Karara bağlanan" (M-34).
 *
 * Motion: the drawer's own; none on the list.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, DoorOpen, Inbox, Users, XCircle } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useEffectEvent, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { KbdHint } from "@/components/ui/kbd-hint";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { Alert, Loading, NoAccess, PageTitle } from "@/components/admin/kit";
import { useBookingFormat, useProfileLanguage } from "@/components/bookings/use-booking-format";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { roomDay } from "@/components/bookings/reserve-model";
import { reasonKey } from "@/components/bookings/booking-grid";
import { focusAfter } from "@/components/bookings/focus-after";
import { crbs, crbsKeys, type GridQuery } from "@/lib/api/crbs";
import { APPROVAL_KEYS, errorText, pickLang, useApprovalInbox, useApprovalRequest, wave1, wave1Error, type ApprovalRequest, type DecideIn } from "@/lib/api/wave1";
import { usePermissions } from "@/lib/permissions";
import { useHydrated } from "@/lib/use-hydrated";
import { useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { conflictAlternatives, groupInbox, isOpen, openDates, pickAsked, requestSlots, type DecideAlternative } from "./approvals-model";
import { RejectDialog, type RejectReason } from "./reject-dialog";
import { GroupSlotLine, RequestReason, RequestTimeline, SlotLine, StatusPill } from "./request-parts";

type Box = "open" | "decided";

/** MOBILE.md M-02 (loop-r1-laneB2): the period chips of a submission are 32 px pills; on coarse pointers they grow to
 *  44 px so their tap zones never overlap the group buttons under them. */
export const SIBLING_CHIP_CLASS = "pointer-coarse:h-11 pointer-coarse:min-w-11 pointer-coarse:px-4";

export function ApprovalsView() {
  const { t } = useI18n();
  useProfileLanguage();
  const { can, loading } = usePermissions();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const fmt = useBookingFormat();
  const hydrated = useHydrated();
  const decider = can("approvals.decide");
  const [box, setBox] = useState<Box>("open");
  const list = useApprovalInbox(box, decider);
  const askedRequest = Number(params.get("request")) || null;
  const askedGroup = Number(params.get("group")) || null;
  const rows = list.data ?? [];
  // A-12: one row per submission; the drawer still decides each period, or the whole submission at once
  const entries = groupInbox(rows);
  const asked = askedRequest;
  const [openId, setOpenId] = useState<number | null>(askedRequest);
  // a shortcut pressed on a list row, run by the drawer once the request is loaded (T-R1-18)
  const [pendingKey, setPendingKey] = useState<"a" | "d" | "r" | null>(null);
  // a later notification click on the same page changes ?request= / ?group=. A group link is resolved once the
  // inbox answered: the submission's first open period (the link's own request may be decided already).
  const linkKey = askedRequest !== null || askedGroup !== null ? `${askedRequest ?? ""}|${askedGroup ?? ""}` : null;
  const [seenLink, setSeenLink] = useState<string | null>(askedGroup === null ? linkKey : null);
  if (linkKey !== seenLink && (askedGroup === null || list.isFetched || !decider)) {
    setSeenLink(linkKey);
    if (linkKey !== null) setOpenId(pickAsked(entries, askedRequest, askedGroup));
  }
  const groupOf = (id: number | null) => (id === null ? [] : (entries.find((e) => e.requests.some((r) => r.id === id))?.requests ?? []));

  // permission-dependent markup only after hydration (the user can arrive mid-hydration: React #418)
  if (!hydrated || loading) return <Loading />;
  if (!decider) {
    return (
      <div className="flex flex-col gap-4">
        <NoAccess title={t("wave1.approvals.noAccessTitle")} body={t("wave1.approvals.noAccessBody")} />
        <Link href={asked ? `/my-bookings?request=${asked}` : "/my-bookings"} className="self-center type-callout text-tint-text hover:underline">
          {t("wave1.approvals.toMine")}
        </Link>
      </div>
    );
  }

  const close = () => {
    setOpenId(null);
    setPendingKey(null);
    if (params.get("request") || params.get("group")) router.replace(pathname);
  };
  const nextOpen = (id: number) => rows.find((r) => r.id !== id && isOpen(r))?.id ?? null;

  return (
    <div className="flex flex-col gap-5" data-testid="approvals">
      <PageTitle title={t("wave1.approvals.title")} subtitle={t("wave1.approvals.lead")} />
      <h2 tabIndex={-1} data-approvals-heading className="sr-only">
        {t("wave1.approvals.box")}
      </h2>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl<Box>
          aria-label={t("wave1.approvals.box")}
          value={box}
          onValueChange={setBox}
          options={[
            { value: "open", label: t("wave1.approvals.boxOpen") },
            { value: "decided", label: t("wave1.approvals.boxDecided") },
          ]}
        />
        <p className="hidden items-center gap-2 type-footnote text-label-3 md:flex pointer-coarse:hidden">
          <KbdHint keys={["A"]} /> {t("wave1.approvals.approve")} <KbdHint keys={["D"]} /> {t("wave1.approvals.reject")} <KbdHint keys={["R"]} /> {t("wave1.approvals.otherRoom")}
        </p>
      </div>
      <Card variant="glass" className="gap-0 overflow-hidden py-0">
        {list.isLoading ? (
          <Loading className="px-4" />
        ) : rows.length === 0 ? (
          <p className="flex items-center gap-2 px-4 py-6 type-callout text-label-2" data-testid="approvals-empty">
            <Inbox className="size-4 text-label-3" aria-hidden />
            {box === "open" ? t("wave1.approvals.emptyOpen") : t("wave1.approvals.emptyDecided")}
          </p>
        ) : (
          <ul data-testid="approvals-list" onKeyDown={moveInList}>
            {entries.map(({ key, requests }) => {
              const r = requests[0]!;
              return (
              <li key={key} className="hairline-b last:shadow-none">
                <Button
                  variant="ghost" shape="rect" className="h-auto w-full rounded-none whitespace-normal font-normal active:not-aria-[haspopup]:scale-100 focus-visible:-outline-offset-2 flex-col items-stretch justify-start gap-1 px-4 py-3 text-left hover:bg-fill-3 sm:flex-row sm:items-center sm:gap-4"
                  onClick={() => setOpenId(r.id)}
                  onKeyDown={(e) => {
                    // T-R1-18 (R1-M-23): the legend's A / D / R work on a focused row too (they open the request)
                    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat || !isOpen(r)) return;
                    const k = e.key.toLowerCase();
                    if (k !== "a" && k !== "d" && k !== "r") return;
                    e.preventDefault();
                    setPendingKey(k);
                    setOpenId(r.id);
                  }}
                  data-testid={`approval-${r.id}`}
                  data-approval-row
                  aria-label={t("wave1.approvals.openRequest", { room: r.room_name ?? "", name: r.requester_name ?? "" })}
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="type-headline text-label-1">{r.room_name}</span>
                      <StatusPill status={r.status} />
                      {requests.length > 1 ? (
                        <span className="inline-flex h-5 items-center rounded-full bg-fill-2 px-2 type-caption text-label-2" data-testid={`approval-group-${r.id}`}>
                          {t("wave1.approvals.groupN", { n: requests.length })}
                        </span>
                      ) : null}
                      {r.competing.length ? (
                        <span className="inline-flex items-center gap-1 type-caption text-status-warning-fg">
                          <Users className="size-3.5" aria-hidden />
                          {t("wave1.approvals.competingN", { n: r.competing.length })}
                        </span>
                      ) : null}
                    </span>
                    <GroupSlotLine reqs={requests} fmt={fmt} className="block type-footnote text-label-2" />
                  </span>
                  <span className="shrink-0 type-footnote text-label-2 sm:text-right">
                    <span className="block text-label-1">{r.requester_name}</span>
                    {r.requested_at ? <span className="block text-label-3 tabular-nums">{fmt.dateTime(r.requested_at)}</span> : null}
                  </span>
                </Button>
              </li>
              );
            })}
          </ul>
        )}
      </Card>
      <RequestDrawer
        id={openId}
        onClose={close}
        onSwitch={(next) => (setPendingKey(null), setOpenId(next))}
        group={groupOf(openId)}
        pendingKey={pendingKey}
        onDone={(id) => {
          const next = box === "open" ? nextOpen(id) : null;
          if (next) {
            setPendingKey(null);
            setOpenId(next);
            // T-R1-12 (R1-M-22): the drawer now shows the next request; its title takes the focus (never the bell)
            focusAfter(["[data-approval-title]"], 0);
          } else {
            close();
            // the decided row leaves the open list: keep focus in the list, not on <body> or the bell (motion audit T4)
            focusAfter([nextRowSelector(entries, id), "[data-approvals-heading]"]);
          }
        }}
      />
    </div>
  );
}

/**
 * T-R2-12 (R2-S-17): roving focus on the inbox list. j / ArrowDown and k / ArrowUp move between the submission rows,
 * Home / End jump to the first and last one (F-13 C02: "j → next row"). Enter / Space on a row open it (its button).
 */
function moveInList(e: KeyboardEvent<HTMLUListElement>) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  const step = k === "j" || k === "ArrowDown" ? 1 : k === "k" || k === "ArrowUp" ? -1 : k === "Home" ? -Infinity : k === "End" ? Infinity : 0;
  if (!step) return;
  const rows = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-approval-row]"));
  if (!rows.length) return;
  const active = document.activeElement;
  const i = rows.findIndex((el) => el === active || el.contains(active));
  const next = step === -Infinity ? 0 : step === Infinity ? rows.length - 1 : Math.min(rows.length - 1, Math.max(0, (i < 0 ? (step > 0 ? -1 : rows.length) : i) + step));
  e.preventDefault();
  rows[next]?.focus();
}

/** After the drawer's exit, focus the next submission's row (rows are one per submission, A-12), else the heading. */
function nextRowSelector(entries: { requests: ApprovalRequest[] }[], id: number): string {
  const i = entries.findIndex((e) => e.requests.some((r) => r.id === id));
  const next = entries[i + 1] ?? entries[i - 1];
  return next ? `[data-testid="approval-${next.requests[0]!.id}"]` : "[data-approvals-heading]";
}

/* --------------------------------------------------------------------------------------- drawer */

function RequestDrawer({ id, onClose, onSwitch, onDone, group, pendingKey }: { id: number | null; onClose: () => void; onSwitch: (id: number) => void; onDone: (id: number) => void; group: ApprovalRequest[]; pendingKey: "a" | "d" | "r" | null }) {
  const phone = useIsPhone();
  // the app's reduced-motion switch or the OS setting: the drawer appears and leaves at once (no slide)
  const reduce = useReduce();
  const popupRef = useRef<HTMLDivElement>(null);
  return (
    <Sheet open={id !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        ref={popupRef}
        side={phone ? "bottom" : "right"}
        // T-R2-12 (R2-M-09): the drawer opens with focus on its title, never on the first field (the note textarea
        // swallowed the A / D / R keys). While the request is still loading the popup itself takes the focus and
        // RequestDetail moves it to the title once rendered.
        initialFocus={() => popupRef.current?.querySelector<HTMLElement>("[data-approval-title]") ?? popupRef.current ?? true}
        // phone: a 92 % bottom sheet, full width and flush with the bottom (F-01 mobile, MOBILE.md M-04)
        className={cn("gap-0 data-[side=right]:sm:max-w-lg", phone && "inset-x-0! bottom-0! h-[92dvh] max-h-[92dvh]! rounded-b-none!", reduce && "transition-none! data-starting-style:translate-x-0! data-starting-style:translate-y-0! data-ending-style:translate-x-0! data-ending-style:translate-y-0!")}
        data-testid="approval-drawer"
        data-reduced-motion={reduce || undefined}
      >
        {id !== null ? <RequestDetail key={`${id}|${pendingKey ?? ""}`} id={id} onSwitch={onSwitch} onDone={onDone} group={group} pendingKey={pendingKey} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function RequestDetail({ id, onSwitch, onDone, group, pendingKey }: { id: number; onSwitch: (id: number) => void; onDone: (id: number) => void; group: ApprovalRequest[]; pendingKey: "a" | "d" | "r" | null }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const qc = useQueryClient();
  const phone = useIsPhone();
  const req = useApprovalRequest(id);
  const r = req.data;
  const [note, setNote] = useState("");
  // a shortcut pressed on the list row (T-R1-18): D opens the reject dialog, R the other rooms; A opens the request
  const [picking, setPicking] = useState(pendingKey === "r");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<{ text: string; alternatives: DecideAlternative[] } | null>(null);
  const pending = r ? openDates(r) : [];
  const [instances, setInstances] = useState<Set<string> | null>(null);
  const chosen = instances ?? new Set(pending);
  const open = !!r && isOpen(r);
  const siblings = group.length > 1 ? group : [];
  const openSiblings = siblings.filter(isOpen);
  const [groupBusy, setGroupBusy] = useState<"approve" | "reject" | null>(null);
  // the reject dialog: this period, the whole submission, or "reject and suggest" another room
  const [rejecting, setRejecting] = useState<{ scope: "one" | "group"; alternative?: NonNullable<DecideIn["alternative"]>; suggestion?: string } | null>(pendingKey === "d" ? { scope: "one" } : null);
  const [rejectError, setRejectError] = useState<string | null>(null);
  const askReject = (scope: "one" | "group", alternative?: NonNullable<DecideIn["alternative"]>, suggestion?: string) => {
    setRejectError(null);
    setRejecting({ scope, alternative, suggestion });
  };
  const decideAll = async (decision: "approve" | "reject", reason?: RejectReason) => {
    const gid = r?.group_id;
    if (!gid || groupBusy) return;
    setGroupBusy(decision);
    setError(null);
    try {
      const body = decision === "reject" ? { decision, reason: reason?.reason ?? null, reason_code: reason?.reason_code ?? null } : { decision, note: note.trim() || null };
      await wave1.approvals.decideGroup(gid, body);
      await Promise.all(APPROVAL_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      toast.success(t(decision === "approve" ? "wave1.approvals.groupApproved" : "wave1.approvals.groupRejected", { n: openSiblings.length, room: r?.room_name ?? "" }));
      setRejecting(null);
      onDone(r!.id);
    } catch (e) {
      if (decision === "reject") setRejectError(errorText(wave1Error(e), locale));
      else setError({ text: errorText(wave1Error(e), locale), alternatives: [] });
    } finally {
      setGroupBusy(null);
    }
  };

  const decide = async (decision: "approve" | "reject", alternative?: DecideIn["alternative"], reason?: RejectReason) => {
    if (!r || busy) return;
    if (decision === "approve" && pending.length > 1 && chosen.size === 0) {
      setError({ text: t("wave1.approvals.pickDates"), alternatives: [] });
      return;
    }
    setBusy(decision);
    setError(null);
    try {
      const body: DecideIn = decision === "reject" ? { decision, reason: reason?.reason ?? null, reason_code: reason?.reason_code ?? null, alternative: alternative ?? null } : { decision, note: note.trim() || null, alternative: alternative ?? null };
      if (decision === "approve" && pending.length > 1 && chosen.size < pending.length) body.instances = [...chosen].sort();
      const out = await wave1.approvals.decide(r.id, body);
      await Promise.all(APPROVAL_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      if (out.status === "PENDING") toast.success(t("wave1.approvals.stepDone", { n: out.step, of: out.steps }));
      else toast.success(t(decision === "approve" ? "wave1.approvals.approved" : "wave1.approvals.rejected", { room: alternative?.room_id ? (out.bookings[0]?.room_name ?? r.room_name ?? "") : (r.room_name ?? "") }));
      setRejecting(null);
      onDone(r.id);
    } catch (e) {
      const err = wave1Error(e);
      if (decision === "reject" && rejecting && !(err.status === 409 && err.code === "not_pending")) {
        // the reason stays in the dialog; the backend's sentence is shown there
        setRejectError(errorText(err, locale));
        return;
      }
      setRejecting(null);
      if (err.status === 409 && err.code === "not_pending") {
        toast.message(errorText(err, locale));
        await Promise.all(APPROVAL_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      }
      setError({ text: errorText(err, locale), alternatives: err.status === 409 ? conflictAlternatives(err.data) : [] });
    } finally {
      setBusy(null);
    }
  };

  const run = (k: string): boolean => {
    if (k === "a") void decide("approve");
    else if (k === "d") askReject("one");
    else if (k === "r") setPicking((p) => !p);
    else return false;
    return true;
  };
  // T-R1-18 (R1-M-23): A / D / R act on the open request wherever the focus is in the drawer (its "Kapat" too) or
  // still on the page behind it, except in a text field and while the reject dialog is open
  const onKey = useEffectEvent((e: globalThis.KeyboardEvent) => {
    if (!open || rejecting || e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
    const el = e.target as HTMLElement | null;
    if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
    if (el?.closest('[role="alertdialog"], [data-testid="reject-dialog"]')) return;
    if (run(e.key.toLowerCase())) e.preventDefault();
  });
  useEffect(() => {
    const h = (e: globalThis.KeyboardEvent) => onKey(e);
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, []);
  // T-R2-12 (R2-M-09): once the request is rendered, focus the title if the popup opened before it existed (the
  // focus then sits on the sheet container or fell to <body>), so A / D / R act at once after Enter on a row.
  const loaded = !!r;
  useEffect(() => {
    if (!loaded) return;
    const active = document.activeElement;
    if (active && active !== document.body && active.getAttribute("data-slot") !== "sheet-content") return;
    document.querySelector<HTMLElement>("[data-approval-title]")?.focus();
  }, [loaded]);

  if (req.isLoading) return <Loading className="px-5 pt-5" />;
  if (!r) return <Alert tone="error" className="m-5">{req.error ? errorText(wave1Error(req.error), locale) : t("crbs.errors.not_found")}</Alert>;
  const { dates, first } = requestSlots(r);
  const head = first?.headcount;
  // the whole-submission actions: in the group bar on desktop, in the sticky footer on phones (T-R2-12, R2-S-05:
  // the primary "N saatin hepsini onayla" sat at y 318 inside the scrolling body, outside MOBILE.md M-05's bottom 40 %)
  const groupActions = (
    <div className={cn("flex flex-wrap gap-2", phone && "w-full [&>button]:flex-1")}>
      <Button size={phone ? "md" : "sm"} variant="outline" className="text-status-infeasible-fg" onClick={() => askReject("group")} {...busyProps(groupBusy === "reject", groupBusy !== null || busy !== null)} data-testid="approval-group-reject">
        <BusyLabel busy={groupBusy === "reject"} label={t("busy.rejecting")}>{t("wave1.approvals.rejectAll", { n: openSiblings.length })}</BusyLabel>
      </Button>
      <Button size={phone ? "md" : "sm"} onClick={() => void decideAll("approve")} {...busyProps(groupBusy === "approve", groupBusy !== null || busy !== null)} data-testid="approval-group-approve">
        <BusyLabel busy={groupBusy === "approve"} label={t("busy.approving")}>{t("wave1.approvals.approveAll", { n: openSiblings.length })}</BusyLabel>
      </Button>
    </div>
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SheetHeader className="px-5 pt-5 pb-3">
        <div className="flex items-center gap-2">
          <SheetTitle className="type-title-3 outline-hidden" tabIndex={-1} data-approval-title>{r.room_name}</SheetTitle>
          <StatusPill status={r.status} />
        </div>
        {/* T-R1-13 (R1-M-34): a submission's heading names its whole span ("P7–P8 (13:30–15:00)") */}
        <SheetDescription className="type-callout text-label-2">
          {siblings.length ? <GroupSlotLine reqs={siblings} fmt={fmt} /> : <SlotLine req={r} fmt={fmt} />}
        </SheetDescription>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {siblings.length ? (
          <section aria-label={t("wave1.approvals.groupTitle", { n: siblings.length })} className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3" data-testid="approval-group-bar">
            <p className="type-footnote text-label-2">{t("wave1.approvals.groupTitle", { n: siblings.length })}</p>
            <div className="flex flex-wrap gap-1.5">
              {siblings.map((s) => {
                const sb = s.bookings[0];
                const label = sb ? (sb.start_period === sb.end_period ? `P${sb.start_period}` : `P${sb.start_period}–P${sb.end_period}`) : `#${s.id}`;
                return (
                  <Button key={s.id} size="xs" className={SIBLING_CHIP_CLASS} variant={s.id === r.id ? "default" : "outline"} aria-current={s.id === r.id ? "true" : undefined} onClick={() => onSwitch(s.id)} data-testid={`approval-sibling-${s.id}`}>
                    {label}
                    {isOpen(s) ? null : <span className="sr-only">, {s.status}</span>}
                  </Button>
                );
              })}
            </div>
            {openSiblings.length > 1 && !phone ? groupActions : null}
          </section>
        ) : null}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 type-callout">
          <dt className="text-label-3">{t("wave1.approvals.requester")}</dt>
          <dd className="text-label-1">{r.requester_name ?? "—"}</dd>
          {first?.department_name ? (
            <>
              <dt className="text-label-3">{t("crbs.book.department")}</dt>
              <dd className="text-label-1">{first.department_name}</dd>
            </>
          ) : null}
          {head ? (
            <>
              <dt className="text-label-3">{t("wave1.approvals.headcount")}</dt>
              <dd className="text-label-1 tabular-nums">{head}</dd>
            </>
          ) : null}
          {first?.notes ? (
            <>
              <dt className="text-label-3">{t("crbs.book.notes")}</dt>
              <dd className="text-label-1">{first.notes}</dd>
            </>
          ) : null}
          {r.rule?.name ? (
            <>
              <dt className="text-label-3">{t("wave1.approvals.rule")}</dt>
              <dd className="text-label-1">{r.rule.name}</dd>
            </>
          ) : null}
          {r.steps > 1 ? (
            <>
              <dt className="text-label-3">{t("wave1.approvals.step")}</dt>
              <dd className="text-label-1">{t("wave1.approvals.stepN", { n: r.step, of: r.steps })}</dd>
            </>
          ) : null}
          {r.expires_at && open ? (
            <>
              <dt className="text-label-3">{t("wave1.approvals.expiresAt")}</dt>
              <dd className="text-label-1 tabular-nums">{fmt.dateTime(r.expires_at)}</dd>
            </>
          ) : null}
        </dl>

        {first ? <RoomDayStrip roomId={r.room_id} date={first.date} termId={r.term_id ?? undefined} start={first.start_period} end={first.end_period} /> : null}

        {r.competing.length ? (
          <Alert tone="warning" title={t("wave1.approvals.competingTitle", { n: r.competing.length })}>
            <span className="flex flex-wrap items-center gap-2">
              {t("wave1.approvals.competingBody")}
              {r.competing.map((c) => (
                <Button key={c} size="sm" variant="outline" onClick={() => onSwitch(c)} data-testid={`competing-${c}`}>
                  #{c}
                </Button>
              ))}
            </span>
          </Alert>
        ) : null}

        {open && pending.length > 1 ? (
          <fieldset className="flex flex-col gap-2" data-testid="approval-instances">
            <legend className="mb-1 type-headline text-label-1">{t("wave1.approvals.instances")}</legend>
            <p className="type-footnote text-label-2">{t("wave1.approvals.instancesHint", { n: chosen.size, of: pending.length })}</p>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
              {pending.map((d) => (
                <label key={d} className="flex items-center gap-2 type-callout text-label-1 tabular-nums">
                  <Checkbox
                    checked={chosen.has(d)}
                    onCheckedChange={(v) => {
                      const next = new Set(chosen);
                      if (v === true) next.add(d);
                      else next.delete(d);
                      setInstances(next);
                    }}
                  />
                  {fmt.short(d)}
                </label>
              ))}
            </div>
          </fieldset>
        ) : dates.length > 1 ? (
          <p className="type-footnote text-label-2">{dates.map((d) => fmt.short(d)).join(", ")}</p>
        ) : null}

        <RequestReason req={r} />

        <section aria-labelledby="req-tl" className="flex flex-col gap-2">
          <h3 id="req-tl" className="type-headline text-label-1">
            {t("wave1.approvals.timeline")}
          </h3>
          <RequestTimeline req={r} fmt={fmt} />
        </section>

        {open && picking && first ? <OtherRooms req={r} busy={busy} onApprove={(alt) => void decide("approve", alt)} onSuggest={(alt, name) => askReject("one", alt, name)} /> : null}

        {open ? (
          <label className="flex flex-col gap-1.5 type-footnote font-medium text-label-2">
            {t("wave1.approvals.note")}
            <Textarea rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("wave1.approvals.notePlaceholder")} data-testid="approval-note" />
          </label>
        ) : null}

        {error ? (
          <Alert tone="error" testId="approval-error">
            <span className="block">{error.text}</span>
            {error.alternatives.length ? (
              <span className="mt-2 flex flex-col gap-1.5">
                <span className="type-footnote text-label-2">{t("wave1.approvals.conflictAlts")}</span>
                {error.alternatives.slice(0, 5).map((a) => (
                  <span key={`${a.roomId}-${a.date}-${a.start}`} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 type-callout text-label-1">
                      {a.name}
                      {a.reason ? <span className="block type-footnote text-label-2">{pickLang(a.reason, locale)}</span> : null}
                    </span>
                    <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void decide("approve", { room_id: a.roomId, date: a.date ?? undefined, start_period: a.start || undefined, end_period: a.end || undefined })} data-testid={`approve-alt-${a.roomId}`}>
                      {t("wave1.approvals.approveIn")}
                    </Button>
                  </span>
                ))}
              </span>
            ) : null}
          </Alert>
        ) : null}
      </div>
      {open ? (
        <SheetFooter className="hairline-t flex-row flex-wrap items-center justify-end gap-2 px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]" data-testid="approval-footer">
          {openSiblings.length > 1 && phone ? groupActions : null}
          <Button variant="ghost" className="mr-auto" onClick={() => setPicking((p) => !p)} aria-pressed={picking} aria-keyshortcuts="R" data-testid="approval-other-room">
            <DoorOpen aria-hidden />
            {t("wave1.approvals.otherRoom")}
          </Button>
          <Button variant="outline" className="text-status-infeasible-fg" disabled={!!busy} onClick={() => askReject("one")} aria-keyshortcuts="D" data-testid="approval-reject" aria-busy={busy === "reject" || undefined}>
            <BusyLabel busy={busy === "reject"} label={t("busy.rejecting")} icon={<XCircle aria-hidden />}>
            {t("wave1.approvals.reject")}</BusyLabel>
          </Button>
          <Button disabled={!!busy} onClick={() => void decide("approve")} aria-keyshortcuts="A" data-testid="approval-approve" aria-busy={busy === "approve" || undefined}>
            <BusyLabel busy={busy === "approve"} label={t("busy.approving")} icon={<CheckCircle2 aria-hidden />}>
            {pending.length > 1 && chosen.size < pending.length ? t("wave1.approvals.approveN", { n: chosen.size }) : t("wave1.approvals.approve")}</BusyLabel>
          </Button>
        </SheetFooter>
      ) : null /* a decided request: the sheet's own close button is the one close control ("Kapat Kapat", R1-M-34) */}
      <RejectDialog
        open={rejecting !== null}
        onOpenChange={(o) => !o && setRejecting(null)}
        room={r.room_name ?? ""}
        count={rejecting?.scope === "group" ? openSiblings.length : 1}
        suggestion={rejecting?.suggestion ?? null}
        initialText={note}
        busy={rejecting?.scope === "group" ? groupBusy === "reject" : busy === "reject"}
        error={rejectError}
        onConfirm={(reason) => {
          setRejectError(null);
          if (rejecting?.scope === "group") void decideAll("reject", reason);
          else void decide("reject", rejecting?.alternative, reason);
        }}
      />
    </div>
  );
}

/** The room's day around the requested periods (what else is there), from the booking grid. */
function RoomDayStrip({ roomId, date, termId, start, end }: { roomId: number; date: string; termId?: number; start: number; end: number }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const info = useQuery({ queryKey: ["crbs", "booking-room", roomId], queryFn: () => crbs.bookings.room(roomId), retry: false, staleTime: 60_000 });
  const q: GridQuery = { display: "day", date, term_id: termId, room_group_id: info.data?.room_group_id ?? undefined };
  const grid = useQuery({ queryKey: crbsKeys.grid(q), queryFn: () => crbs.bookings.grid(q), enabled: info.isSuccess, retry: false, staleTime: 30_000 });
  const periods = useMemo(() => new Map((grid.data?.periods ?? []).map((p) => [p.id, p])), [grid.data]);
  const day = grid.data ? roomDay(grid.data, roomId, date) : [];
  if (!day.length) return null;
  return (
    <section aria-labelledby="req-day" className="flex flex-col gap-2">
      <h3 id="req-day" className="type-headline text-label-1">
        {t("wave1.approvals.roomDay", { date: fmt.weekday(date) })}
      </h3>
      <ul className="flex gap-1 overflow-x-auto pb-1" data-testid="approval-room-day">
        {day.map((s) => {
          const p = periods.get(s.period_id);
          const asked = !!p && p.start_period >= start && p.end_period <= end;
          const what = s.status === "booked" ? (s.booking?.status === "PENDING" ? t("wave1.grid.pending") : s.booking?.user_name || t("crbs.slot.booked")) : s.status === "timetable" ? s.label || t("reserve.cell.class") : s.status === "available" ? t("crbs.slot.free") : t(reasonKey(s.reason), { name: s.label ?? "" });
          return (
            <li
              key={s.period_id}
              className={cn(
                "flex min-w-16 shrink-0 flex-col rounded-lg px-2 py-1.5 type-caption",
                s.status === "available" ? "bg-fill-3 text-label-2" : s.status === "timetable" ? "bg-status-locked text-status-locked-fg" : "bg-fill-2 text-label-1",
                asked && "edge-tint",
              )}
              aria-current={asked ? "true" : undefined}
            >
              <span className="font-semibold">{p?.name}</span>
              <span className="truncate">{what}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Free rooms for the same date and periods (T1, the reservation panel's finder call). */
function OtherRooms({ req, busy, onApprove, onSuggest }: { req: ApprovalRequest; busy: string | null; onApprove: (alt: NonNullable<DecideIn["alternative"]>) => void; onSuggest: (alt: NonNullable<DecideIn["alternative"]>, name: string) => void }) {
  const { t, locale } = useI18n();
  const { first } = requestSlots(req);
  const find = useQuery({
    queryKey: ["crbs", "find", "approval", req.id],
    queryFn: () => crbs.rooms.find({ date: first!.date, start: first!.start_period, end: first!.end_period, headcount: first!.headcount ?? undefined, term_id: req.term_id ?? undefined, include_busy: false, include_requestable: true, flex: { periods: 0 }, limit: 20 }),
    enabled: !!first,
    retry: false,
  });
  const rooms = (find.data?.results ?? []).filter((x) => x.room_id !== req.room_id && (x.status === "free" || x.status === "requestable"));
  return (
    <section aria-labelledby="req-other" className="flex flex-col gap-2" data-testid="approval-other-rooms">
      <h3 id="req-other" className="type-headline text-label-1">
        {t("wave1.approvals.otherRoomTitle")}
      </h3>
      <p className="type-footnote text-label-2">{t("wave1.approvals.otherRoomLead")}</p>
      {find.isLoading ? (
        <Loading />
      ) : find.isError ? (
        <Alert tone="error">{errorText(wave1Error(find.error), locale)}</Alert>
      ) : rooms.length === 0 ? (
        <p className="type-callout text-label-2">{t("wave1.approvals.otherRoomNone")}</p>
      ) : (
        <ul className="flex flex-col overflow-hidden rounded-xl bg-fill-2">
          {rooms.slice(0, 8).map((x) => {
            const alt = { room_id: x.room_id, date: first?.date, start_period: x.start_period, end_period: x.end_period };
            return (
              <li key={x.room_id} className="flex flex-wrap items-center gap-2 px-3 py-2 hairline-b last:shadow-none" data-testid={`other-room-${x.code}`}>
                <span className="min-w-0 flex-1">
                  <span className="block type-callout font-medium text-label-1">{x.name}</span>
                  <span className="block truncate type-footnote text-label-2">{pickLang(x.reason, locale) || (x.capacity ? t("crbs.grid.seats", { n: x.capacity }) : "")}</span>
                </span>
                <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => onSuggest(alt, x.name)} data-testid={`suggest-${x.code}`}>
                  {t("wave1.approvals.rejectSuggest")}
                </Button>
                <Button size="sm" variant="outline" disabled={!!busy} onClick={() => onApprove(alt)} data-testid={`approve-in-${x.code}`}>
                  {t("wave1.approvals.approveIn")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
