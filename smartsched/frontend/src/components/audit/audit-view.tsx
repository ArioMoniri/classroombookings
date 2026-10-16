"use client";
/**
 * Admin → Audit log (P7, `audit.view`; docs/product/wave1-api.md §3). Append-only events, newest first, with
 * filters (what, which record, action, who, dates), cursor paging ("Load older"), the before/after diff per
 * event, the CSV export of the filtered range, and Undo for booking create / move / cancel and series create.
 * Undo re-runs the inverse through the booking service; a 409 explains why not (later changes, the slot is
 * taken now, too old) in the backend's words, with the free alternatives when the slot was taken.
 */
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Download, Filter, RotateCcw, Undo2 } from "lucide-react";
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
import { ACTION_PREFIXES, auditQuery, canUndo, diffRows, emptyAuditFilters, ENTITY_TYPES, undoReasons, valueText, type AuditFilterForm } from "./audit-model";
import { BareButton } from "@/components/shell/bare-button";

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

  return (
    <div className="flex flex-col gap-5" data-testid="audit">
      <PageTitle
        title={t("wave1.audit.title")}
        subtitle={t("wave1.audit.lead")}
        actions={
          <Button variant="outline" render={<a href={exportHref} download data-testid="audit-export" />} nativeButton={false}>
            <Download aria-hidden />
            {t("wave1.audit.export")}
          </Button>
        }
      />
      <Card className="gap-3 px-4 py-4">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6"
          aria-label={t("wave1.audit.filters")}
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(draft);
          }}
        >
          <Field label={t("wave1.audit.entity")} htmlFor="au-entity">
            <SelectField id="au-entity" value={draft.entityType} onChange={(e) => set("entityType", e.target.value)} data-testid="audit-entity">
              <option value="">{t("wave1.audit.any")}</option>
              {ENTITY_TYPES.map((x) => (
                <option key={x} value={x}>
                  {entityLabel(x, t)}
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
              <SelectField id="au-actor" value={draft.actorId} onChange={(e) => set("actorId", e.target.value)}>
                <option value="">{t("wave1.audit.anyone")}</option>
                {users.data.items.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.displayname || u.username || u.email}
                  </option>
                ))}
              </SelectField>
            ) : (
              <Input id="au-actor" inputMode="numeric" placeholder="#" value={draft.actorId} onChange={(e) => set("actorId", e.target.value)} />
            )}
          </Field>
          <Field label={t("wave1.find.from")} htmlFor="au-from">
            <Input id="au-from" type="date" value={draft.from} onChange={(e) => set("from", e.target.value)} />
          </Field>
          <Field label={t("wave1.find.to")} htmlFor="au-to">
            <Input id="au-to" type="date" value={draft.to} min={draft.from || undefined} onChange={(e) => set("to", e.target.value)} />
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
              }}
            >
              <RotateCcw aria-hidden />
              {t("wave1.audit.reset")}
            </Button>
          </div>
        </form>
      </Card>

      <Card className="gap-0 overflow-hidden py-0">
        {log.isLoading ? (
          <Loading className="px-4" />
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
  // admin persona M-36: these showed their raw API names in the Turkish filter
  room_field: "wave1.audit.e.room_field",
  schedule: "wave1.audit.e.schedule",
  period: "wave1.audit.e.period",
  timetable_week: "wave1.audit.e.timetable_week",
  translation: "wave1.audit.e.translation",
  building: "wave1.audit.e.building",
  user_constraints: "wave1.audit.e.user_constraints",
};

const VERBS = ["create", "update", "delete", "cancel", "move", "approve", "reject", "decide", "undo", "activate", "withdraw", "import", "policy", "login", "logout", "lock", "unlock"] as const;

/** "room_feature.create" → "Derslik özelliği eklendi"; an unknown verb keeps the entity name and the raw verb. */
export function auditSentence(action: string, entityType: string, t: ReturnType<typeof useI18n>["t"]): string {
  const verb = action.split(".").pop() ?? action;
  const entity = entityLabel(entityType, t);
  return (VERBS as readonly string[]).includes(verb) ? t(`wave1.audit.verb.${verb}` as MessageKey, { entity }) : `${entity} · ${action}`;
}

function entityLabel(type: string, t: ReturnType<typeof useI18n>["t"]): string {
  const key = ENTITY_KEYS[type];
  return key ? t(key) : type;
}

function EventRow({ event: e, onUndo }: { event: AuditEvent; onUndo: () => void }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const [open, setOpen] = useState(false);
  const rows = open ? diffRows(e) : [];
  const words = { yes: t("wave1.audit.yes"), no: t("wave1.audit.no") };
  const panel = `audit-${e.id}`;
  return (
    <li className="not-last:edge-hairline-b" data-testid={`audit-event-${e.id}`} data-action={e.action}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
        <BareButton
          onClick={() => setOpen((x) => !x)}
          aria-expanded={open}
          aria-controls={panel}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left"
        >
          <ChevronDown className={cn("size-4 shrink-0 text-label-3 transition-transform duration-(--dur-fast)", open && "rotate-180")} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              {/* UI/UX review §3: a domain sentence ("Derslik özelliği eklendi · #2"), the raw key in the details */}
              <span className="type-callout font-semibold text-label-1">{auditSentence(e.action, e.entity_type, t)}</span>
              <span className="type-footnote text-label-2 tabular-nums">{e.entity_id ? `#${e.entity_id}` : ""}</span>
              {e.undone ? <span className="type-caption font-medium text-label-3">{t("wave1.audit.undone")}</span> : null}
              {e.undo_of ? <span className="type-caption font-medium text-label-3">{t("wave1.audit.undoOf", { id: e.undo_of })}</span> : null}
            </span>
            <span className="block truncate type-footnote text-label-3 tabular-nums">
              {e.ts ? fmt.dateTime(e.ts) : ""} · {e.actor_label ?? t(`wave1.audit.actorType.${e.actor_type === "user" ? "user" : "system"}`)}
              {e.reason ? ` · ${e.reason}` : ""}
            </span>
          </span>
        </BareButton>
        {canUndo(e) ? (
          <Button size="sm" variant="outline" onClick={onUndo} data-testid={`audit-undo-${e.id}`}>
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
                      <TableCell className="pl-3 font-mono type-footnote text-label-2">{r.field}</TableCell>
                      <TableCell className={cn("max-w-64 truncate type-footnote", r.changed ? "text-status-infeasible-fg line-through decoration-1" : "text-label-2")} title={valueText(r.before, words)}>
                        {valueText(r.before, words)}
                      </TableCell>
                      <TableCell className={cn("max-w-64 truncate pr-3 type-footnote", r.changed ? "font-medium text-status-feasible-fg" : "text-label-2")} title={valueText(r.after, words)}>
                        {valueText(r.after, words)}
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
  const [refusal, setRefusal] = useState<{ text: string; later: number | null; alternatives: string[] } | null>(null);
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
      await Promise.all([...BOOKING_KEYS, ["w1", "audit"]].map((k) => qc.invalidateQueries({ queryKey: k })));
      toast.success(t("wave1.audit.undoneN", { n: out.booking_ids.length || out.undone }));
      onClose();
    } catch (e) {
      const err = wave1Error(e);
      setRefusal({ text: errorText(err, locale), ...undoReasons(err.data) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <ConfirmDialog
      open={!!event}
      onOpenChange={(o) => !o && onClose()}
      title={t("wave1.audit.undoTitle", { action: event?.action ?? "" })}
      description={t("wave1.audit.undoBody")}
      confirmLabel={t("wave1.audit.undo")}
      busy={busy}
      onConfirm={() => void run()}
    >
      {refusal ? (
        <Alert tone="error" testId="audit-undo-error">
          <span className="block">{refusal.text}</span>
          {refusal.alternatives.length ? <span className="mt-1 block type-footnote">{t("wave1.audit.freeNow", { rooms: refusal.alternatives.slice(0, 5).join(", ") })}</span> : null}
        </Alert>
      ) : null}
    </ConfirmDialog>
  );
}
