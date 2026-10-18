"use client";
/**
 * Admin → Audit log (P7, `audit.view`; docs/product/wave1-api.md §3). Append-only events, newest first, with
 * filters (what, which record, action, who, dates), cursor paging ("Load older"), the before/after diff per
 * event, the CSV export of the filtered range, and Undo for booking create / move / cancel and series create.
 * Undo re-runs the inverse through the booking service; a 409 explains why not (later changes, the slot is
 * taken now, too old) in the backend's words, with the free alternatives when the slot was taken.
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Download, Filter, RotateCcw, SlidersHorizontal, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SelectField } from "@/components/admin/kit";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { BOOKING_KEYS, useUserSearch } from "@/lib/api/crbs";
import { errorText, useAuditLog, wave1, wave1Error, type AuditEvent } from "@/lib/api/wave1";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { ACTION_PREFIXES, ACTION_SENTENCES, ARCHIVED_KINDS, archivedCounts, auditQuery, auditReason, auditSubject, auditTail, canUndo, dedupeOptions, diffRows, diffValueText, emptyAuditFilters, ENTITY_ALIASES, ENTITY_TYPES, fieldLabel, isProgramUndo, undoBlockers, undoReasons, type AuditFilterForm } from "./audit-model";
import { BareButton } from "@/components/shell/bare-button";
import { DateField } from "@/components/ui/date-field";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { focusAfter } from "@/components/bookings/focus-after";
import { AuditDaily } from "./audit-daily";
import { filterToDay } from "./audit-daily-model";

export function AuditView() {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const [draft, setDraft] = useState<AuditFilterForm>(emptyAuditFilters);
  const [applied, setApplied] = useState<AuditFilterForm>(emptyAuditFilters);
  const query = auditQuery(applied);
  const log = useAuditLog(query);
  const users = useUserSearch({ limit: 500, sort: "displayname" }, can("setup.users"));
  const items = log.data?.pages.flatMap((p) => p.items) ?? [];
  const set = <K extends keyof AuditFilterForm>(k: K, v: AuditFilterForm[K]) => setDraft((p) => ({ ...p, [k]: v }));
  const exportHref = wave1.audit.exportUrl({ from: query.from, to: query.to, entity_type: query.entity_type });
  const [undoing, setUndoing] = useState<AuditEvent | null>(null);
  const phone = useIsPhone();
  const [filtersOpen, setFiltersOpen] = useState(false);

  // phones: the six filters live in a bottom sheet behind one "Filtreler · n" trigger (MOBILE.md M-04)
  const filterForm = (
    <form
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6"
      aria-label={t("wave1.audit.filters")}
      onSubmit={(e) => {
        e.preventDefault();
        setApplied(draft);
        setFiltersOpen(false);
      }}
    >
      <Field label={t("wave1.audit.entity")} htmlFor="au-entity">
        <SelectField id="au-entity" value={draft.entityType} onChange={(e) => set("entityType", e.target.value)} data-testid="audit-entity">
          <option value="">{t("wave1.audit.any")}</option>
          {dedupeOptions(ENTITY_TYPES.map((x) => ({ value: x, label: entityLabel(x, t), hint: x }))).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </SelectField>
      </Field>
      <Field label={t("wave1.audit.entityId")} htmlFor="au-id">
        <Input id="au-id" inputMode="numeric" value={draft.entityId} onChange={(e) => set("entityId", e.target.value)} data-testid="audit-entity-id" />
      </Field>
      <Field label={t("wave1.audit.action")} htmlFor="au-action">
        <SelectField id="au-action" value={draft.action} onChange={(e) => set("action", e.target.value)} data-testid="audit-action">
          <option value="">{t("wave1.audit.any")}</option>
          {ACTION_PREFIXES.map((x) => (
            <option key={x} value={x}>
              {x}*
            </option>
          ))}
        </SelectField>
      </Field>
      <Field label={t("wave1.audit.actor")} htmlFor="au-actor">
        {users.data ? (
          <SelectField id="au-actor" value={draft.actorId} onChange={(e) => set("actorId", e.target.value)} data-testid="audit-actor">
            <option value="">{t("wave1.audit.anyone")}</option>
            {/* T-R1-32: two people with one display name are told apart by username / e-mail, and no one is listed twice */}
            {dedupeOptions(users.data.items.map((u) => ({ value: String(u.id), label: u.displayname || u.full_name || u.username || u.email || `#${u.id}`, hint: u.username || u.email }))).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </SelectField>
        ) : (
          <Input id="au-actor" inputMode="numeric" placeholder="#" value={draft.actorId} onChange={(e) => set("actorId", e.target.value)} />
        )}
      </Field>
      <Field label={t("wave1.find.from")} htmlFor="au-from">
        <DateField id="au-from" value={draft.from} onChange={(v) => set("from", v)} />
      </Field>
      <Field label={t("wave1.find.to")} htmlFor="au-to">
        <DateField id="au-to" value={draft.to} min={draft.from || undefined} onChange={(v) => set("to", v)} />
      </Field>
      <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-6">
        <Button type="submit" data-testid="audit-apply">
          <Filter aria-hidden />
          {t("wave1.audit.apply")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setDraft(emptyAuditFilters);
            setApplied(emptyAuditFilters);
            setFiltersOpen(false);
          }}
        >
          <RotateCcw aria-hidden />
          {t("wave1.audit.reset")}
        </Button>
      </div>
    </form>
  );
  const activeFilters = Object.values(auditQuery(applied)).length;

  return (
    <div className="flex flex-col gap-5" data-testid="audit">
      {/* phones (T-R1-32, R1-M-30): the filter trigger ("Filtreler · n") and the export sit beside the title, the lead
          is left out, so the first event starts above 200 px */}
      {/* mobile-b phase 2 (CLS 1.32 at 390 with filters): the phone / desktop split is CSS (max-sm), not useIsPhone,
          which reads false until hydration and painted the six-field desktop form first on every phone */}
      <PageTitle
        className="max-sm:mb-1 max-sm:flex-row max-sm:items-center max-sm:justify-between max-sm:[&>div>p]:hidden"
        title={t("wave1.audit.title")}
        subtitle={t("wave1.audit.lead")}
        actions={
          <>
            <Button variant="outline" className="sm:hidden" onClick={() => setFiltersOpen(true)} aria-haspopup="dialog" aria-label={activeFilters ? t("reserve.filters.openCount", { n: activeFilters }) : t("reserve.filters.open")} data-testid="audit-filters-open">
              <SlidersHorizontal aria-hidden />
              {activeFilters ? String(activeFilters) : null}
            </Button>
            <Button variant="outline" className="max-sm:size-11 max-sm:px-0" render={<a href={exportHref} download data-testid="audit-export" />} nativeButton={false}>
              <Download aria-hidden />
              <span className="max-sm:sr-only">{t("wave1.audit.export")}</span>
            </Button>
          </>
        }
      />
      {activeFilters ? (
          <div className="flex items-center gap-2 sm:hidden">
            <Button className="pointer-coarse:h-11"
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(emptyAuditFilters);
                setApplied(emptyAuditFilters);
              }}
            >
              <RotateCcw aria-hidden />
              {t("wave1.audit.reset")}
            </Button>
          </div>
      ) : null}
      {phone ? null : <Card className="gap-3 px-4 py-4 max-sm:hidden">{filterForm}</Card>}
      <Sheet open={phone && filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="bottom" className="gap-0 data-[side=bottom]:max-h-[92dvh]" data-testid="audit-filters-sheet">
          <SheetHeader className="px-5 pt-5">
            <SheetTitle className="type-title-3">{t("wave1.audit.filters")}</SheetTitle>
            <SheetDescription className="sr-only">{t("wave1.audit.lead")}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]">{filterForm}</div>
        </SheetContent>
      </Sheet>

      {/* CH-10: events per day (30 g); a column click filters the list to that day (audit.view only: the counts are everyone's) */}
      {can("audit.view") ? (
        <AuditDaily
          onDay={(day) => {
            const next = filterToDay(applied, day);
            setDraft(next);
            setApplied(next);
          }}
        />
      ) : null}
      <Card className="gap-0 overflow-hidden py-0">
        {log.isLoading ? (
          // the first page of events fills the screen: hold that height, not a one-line spinner (CLS)
          <div className="min-h-[70dvh] px-4 py-3" aria-busy="true" data-testid="audit-loading">
            <Loading />
          </div>
        ) : log.isError ? (
          <Alert tone="error" className="m-4">
            {errorText(wave1Error(log.error), locale)}
          </Alert>
        ) : items.length === 0 ? (
          <p className="px-4 py-6 type-callout text-label-2" data-testid="audit-empty">
            {t("wave1.audit.empty")}
          </p>
        ) : (
          <ul data-testid="audit-list" aria-label={t("wave1.audit.title")}>
            {items.map((e) => (
              <EventRow key={e.id} event={e} onUndo={() => setUndoing(e)} />
            ))}
          </ul>
        )}
      </Card>
      {log.hasNextPage ? (
        <Button variant="outline" className="self-center" disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()} data-testid="audit-more" aria-busy={log.isFetchingNextPage || undefined}>
          <BusyLabel busy={log.isFetchingNextPage} label={t("busy.loading")} icon={<ChevronDown aria-hidden />}>
          {t("wave1.audit.more")}</BusyLabel>
        </Button>
      ) : items.length ? (
        <p className="text-center type-footnote text-label-3">{t("wave1.audit.end", { n: items.length })}</p>
      ) : null}
      <UndoDialog event={undoing} onClose={() => setUndoing(null)} />
    </div>
  );
}

const ENTITY_KEYS: Record<string, MessageKey> = {
  booking: "wave1.audit.e.booking",
  approval_request: "wave1.audit.e.approval_request",
  approval_rule: "wave1.audit.e.approval_rule",
  approver: "wave1.audit.e.approver",
  room: "wave1.audit.e.room",
  room_feature: "wave1.audit.e.room_feature",
  room_group: "wave1.audit.e.room_group",
  room_acl: "wave1.audit.e.room_acl",
  user: "wave1.audit.e.user",
  role: "wave1.audit.e.role",
  settings: "wave1.audit.e.settings",
  holiday: "wave1.audit.e.holiday",
  session: "wave1.audit.e.session",
  term: "wave1.audit.e.term",
  department: "wave1.audit.e.department",
  program: "wave1.audit.e.program",
  // admin persona M-36: these showed their raw API names in the Turkish filter
  room_field: "wave1.audit.e.room_field",
  schedule: "wave1.audit.e.schedule",
  period: "wave1.audit.e.period",
  timetable_week: "wave1.audit.e.timetable_week",
  translation: "wave1.audit.e.translation",
  building: "wave1.audit.e.building",
  user_constraints: "wave1.audit.e.user_constraints",
  // T-R1-32 (R1-M-18): the KVKK, channel, policy, sign-in and wizard records
  course: "wave1.audit.e.course",
  section: "wave1.audit.e.section",
  exam: "wave1.audit.e.exam",
  meeting: "wave1.audit.e.meeting",
  faculty: "wave1.audit.e.faculty",
  instructor: "wave1.audit.e.instructor",
  run: "wave1.audit.e.run",
  booking_policy: "wave1.audit.e.booking_policy",
  webhook: "wave1.audit.e.webhook",
  sso_provider: "wave1.audit.e.sso_provider",
  sso_role_mapping: "wave1.audit.e.sso_role_mapping",
  notify_channel: "wave1.audit.e.notify_channel",
  user_channel: "wave1.audit.e.user_channel",
  dsr_request: "wave1.audit.e.dsr_request",
  privacy_notice: "wave1.audit.e.privacy_notice",
  consent: "wave1.audit.e.consent",
  retention_policy: "wave1.audit.e.retention_policy",
  preset: "wave1.audit.e.preset",
  constraint: "wave1.audit.e.constraint",
  invigilation_plan: "wave1.audit.e.invigilation_plan",
  invigilation_duty: "wave1.audit.e.invigilation_duty",
  invigilator_pool: "wave1.audit.e.invigilator_pool",
  // R3-S-03 / R3-M-07: series, intake jobs, learning and the run/plan records read "Booking series", "Council job"…
  booking_series: "wave1.audit.e.booking_series",
  council_job: "wave1.audit.e.council_job",
  exam_request: "wave1.audit.e.exam_request",
  assignment: "wave1.audit.e.assignment",
  learning: "wave1.audit.e.learning",
  learning_reset: "wave1.audit.e.learning_reset",
  program_draft: "wave1.audit.e.program_draft",
  suggestion: "wave1.audit.e.suggestion",
};

const VERBS = ["create", "update", "delete", "cancel", "move", "approve", "reject", "decide", "undo", "activate", "withdraw", "import", "policy", "login", "logout", "lock", "unlock", "restore", "archive", "features", "expire", "request", "requested", "approved", "rejected", "withdrawn", "expired", "step", "detect", "resolve", "commit", "deleted", "disabled", "secret"] as const;

/**
 * "room_feature.create" → "Derslik özelliği eklendi", "kvkk.dsr_refuse" → "Kişisel veri talebi reddedildi" (T-R1-32).
 * An action this screen does not know still reads as the entity's name plus a generic verb, never the raw key: the
 * key is in the details (`audit-action-<id>`).
 */
export function auditSentence(action: string, entityType: string, t: ReturnType<typeof useI18n>["t"]): string {
  const special = ACTION_SENTENCES[action];
  const entity = entityLabel(entityType, t);
  if (special) return t(`wave1.audit.act.${special}` as MessageKey, { entity });
  const verb = action.split(".").pop() ?? action;
  return t(((VERBS as readonly string[]).includes(verb) ? `wave1.audit.verb.${verb}` : "wave1.audit.verb.changed") as MessageKey, { entity });
}

/** The record kind for people ("Derslik", "Kişisel veri talebi"); an unknown kind reads as a plain word, not a key. */
export function entityLabel(type: string, t: ReturnType<typeof useI18n>["t"]): string {
  const key = ENTITY_KEYS[ENTITY_ALIASES[type] ?? type];
  if (key) return t(key);
  return type.replace(/[._]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function EventRow({ event: e, onUndo }: { event: AuditEvent; onUndo: () => void }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const [open, setOpen] = useState(false);
  const rows = open ? diffRows(e) : [];
  const words = { yes: t("wave1.audit.yes"), no: t("wave1.audit.no") };
  const panel = `audit-${e.id}`;
  return (
    <li
      className="not-last:edge-hairline-b focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)"
      data-testid={`audit-event-${e.id}`}
      data-action={e.action}
      data-audit-id={e.id}
      tabIndex={-1}
      aria-label={`${auditSentence(e.action, e.entity_type, t)} ${auditTail(e)}`.trim()}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
        <BareButton
          onClick={() => setOpen((x) => !x)}
          aria-expanded={open}
          aria-controls={panel}
          className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-lg text-left pointer-fine:min-h-0"
        >
          <ChevronDown className={cn("size-4 shrink-0 text-label-3 transition-transform duration-(--dur-fast)", open && "rotate-180")} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              {/* UI/UX review §3: a domain sentence ("Derslik özelliği eklendi · #2"), the raw key in the details */}
              <span className="type-callout font-semibold text-label-1" data-testid={`audit-summary-${e.id}`}>{auditSentence(e.action, e.entity_type, t)}</span>
              <span className="type-footnote text-label-2 tabular-nums">{auditTail(e)}</span>
              {e.undone ? <span className="type-caption font-medium text-label-3">{t("wave1.audit.undone")}</span> : null}
              {e.undo_of ? <span className="type-caption font-medium text-label-3">{t("wave1.audit.undoOf", { id: e.undo_of })}</span> : null}
            </span>
            <span className="block truncate type-footnote text-label-3 tabular-nums">
              {e.ts ? fmt.dateTime(e.ts) : ""} · {e.actor_label ?? t(`wave1.audit.actorType.${e.actor_type === "user" ? "user" : "system"}`)}
              {auditReason(e.reason, t) ? ` · ${auditReason(e.reason, t)}` : ""}
            </span>
          </span>
        </BareButton>
        {canUndo(e) ? (
          <Button size="sm" variant="outline" className="pointer-coarse:h-11 pointer-coarse:px-4" onClick={onUndo} data-testid={`audit-undo-${e.id}`}>
            <Undo2 aria-hidden />
            {t("wave1.audit.undo")}
          </Button>
        ) : null}
      </div>
      {open ? (
        <div id={panel} className="px-4 pb-3">
          <p className="mb-2 font-mono type-caption text-label-3" data-testid={`audit-action-${e.id}`}>
            {e.action}
          </p>
          {rows.length === 0 ? (
            <p className="type-footnote text-label-2">{t("wave1.audit.noDiff")}</p>
          ) : (
            <div className="overflow-x-auto rounded-xl bg-fill-3">
              <Table data-testid="audit-diff">
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-3">{t("wave1.audit.field")}</TableHead>
                    <TableHead>{t("wave1.audit.before")}</TableHead>
                    <TableHead className="pr-3">{t("wave1.audit.after")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow key={r.field} data-changed={r.changed || undefined}>
                      {/* BUG-02: the field's label ("Derslik"), and names for the ids this viewer may see (e.refs) */}
                      <TableCell className="pl-3 type-footnote text-label-2">{fieldLabel(r.field, t)}</TableCell>
                      <TableCell className={cn("max-w-64 truncate type-footnote", r.changed ? "text-status-infeasible-fg line-through decoration-1" : "text-label-2")} title={diffValueText(r.field, r.before, e.refs, words)}>
                        {diffValueText(r.field, r.before, e.refs, words)}
                      </TableCell>
                      <TableCell className={cn("max-w-64 truncate pr-3 type-footnote", r.changed ? "font-medium text-status-feasible-fg" : "text-label-2")} title={diffValueText(r.field, r.after, e.refs, words)}>
                        {diffValueText(r.field, r.after, e.refs, words)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {e.request_id || e.ip_hash ? (
            <p className="mt-2 type-caption text-label-3">
              {e.request_id ? `${t("wave1.audit.requestId")}: ${e.request_id}` : ""}
              {e.request_id && e.ip_hash ? " · " : ""}
              {e.ip_hash ? `${t("wave1.audit.network")}: ${e.ip_hash.slice(0, 12)}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function UndoDialog({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<{ text: string; later: number | null; alternatives: string[]; blockers: string[] } | null>(null);
  const program = !!event && isProgramUndo(event);
  const [last, setLast] = useState<number | null>(null);
  if ((event?.id ?? null) !== last) {
    setLast(event?.id ?? null);
    setRefusal(null);
  }
  const run = async () => {
    if (!event) return;
    setBusy(true);
    setRefusal(null);
    try {
      const out = await wave1.audit.undo(event.id);
      if (program) {
        // a programme touches sections, requests, people and rules across screens: refresh everything cached
        await qc.invalidateQueries();
        const parts = archivedCounts(out.archived).map(([k, n]) => ((ARCHIVED_KINDS as readonly string[]).includes(k) ? t(`wave1.audit.archived.${k}` as MessageKey, { n }) : `${k}: ${n}`));
        toast.success(t("wave1.audit.programUndone"), parts.length ? { description: t("wave1.audit.archivedLine", { parts: parts.join(", ") }) } : undefined);
      } else {
        await Promise.all([...BOOKING_KEYS, ["w1", "audit"]].map((k) => qc.invalidateQueries({ queryKey: k })));
        toast.success(t("wave1.audit.undoneN", { n: out.booking_ids.length || out.undone }));
      }
      onClose();
      focusAfter([`[data-audit-id="${event.id}"]`]);
    } catch (e) {
      const err = wave1Error(e);
      setRefusal({ text: errorText(err, locale), ...undoReasons(err.data), blockers: undoBlockers(err.data, locale) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <ConfirmDialog
      open={!!event}
      onOpenChange={(o) => !o && onClose()}
      title={t("wave1.audit.undoTitle", { action: event ? [entityLabel(event.entity_type, t), auditSubject(event) ?? (event.entity_id ? `#${event.entity_id}` : "")].filter(Boolean).join(" ") : "" })}
      description={program ? t("wave1.audit.programUndoBody") : t("wave1.audit.undoBody")}
      confirmLabel={t("wave1.audit.undo")}
      busy={busy}
      onConfirm={() => void run()}
    >
      {refusal ? (
        <Alert tone="error" testId="audit-undo-error">
          <span className="block">{refusal.text}</span>
          {refusal.alternatives.length ? <span className="mt-1 block type-footnote">{t("wave1.audit.freeNow", { rooms: refusal.alternatives.slice(0, 5).join(", ") })}</span> : null}
          {refusal.blockers.length ? (
            <span className="mt-2 block" data-testid="audit-undo-blockers">
              <span className="block type-footnote font-semibold">{t("wave1.audit.blockersTitle")}</span>
              <ul className="mt-1 list-disc ps-5 type-footnote">
                {refusal.blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </span>
          ) : null}
        </Alert>
      ) : null}
    </ConfirmDialog>
  );
}
