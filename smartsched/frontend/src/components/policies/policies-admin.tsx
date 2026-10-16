"use client";
/**
 * Ayarlar › Rezervasyon kuralları (P8, `setup.settings`): the booking policies with each rule's TR/EN summary (the
 * same lines "Neden?" shows), a form per rule, and the exam-period mode. No rule ships with the product: until an
 * administrator adds one, only the role limits apply. Planning administrators are never bound by policies.
 */
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ConfirmDialog, Loading } from "@/components/admin/kit";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Alert } from "@/components/ui/alert";
import { Button, IconButton } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { emptyPolicy, policyToInput, useDeletePolicy, usePolicies, useSaveExamPeriod, useSavePolicy, type ExamMode, type Policy, type PolicyIn } from "@/lib/api/booking-policies";
import { crbs, useBookingContext, useRoles } from "@/lib/api/crbs";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { roleLabel } from "@/lib/i18n/roles";
import { PolicyForm, type PolicyFormContext } from "./policy-form";

function useFormContext(): PolicyFormContext {
  const { t } = useI18n();
  const ctx = useBookingContext();
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), retry: false, staleTime: 60_000 });
  const roles = useRoles();
  return useMemo(
    () => ({
      rooms: (rooms.data ?? []).map((r) => ({ id: r.id, name: r.name || r.code })),
      groups: (ctx.data?.room_groups ?? []).map((g) => ({ id: g.id, name: g.name })),
      terms: (ctx.data?.sessions ?? []).map((s) => ({ id: s.id, name: s.name })),
      roles: roles.isError ? null : (roles.data ?? []).map((r) => ({ code: (r.code ?? r.name).toUpperCase(), name: roleLabel(t, r) })),
    }),
    [rooms.data, ctx.data, roles.data, roles.isError, t],
  );
}

function scopeText(p: Policy, ctx: PolicyFormContext, t: (k: MessageKey, v?: Record<string, string | number>) => string): string {
  if (p.scope_type === "room") return t("policies.scopeLine.room", { name: ctx.rooms.find((r) => r.id === p.scope_id)?.name ?? `#${p.scope_id}` });
  if (p.scope_type === "room_group") return t("policies.scopeLine.room_group", { name: ctx.groups.find((g) => g.id === p.scope_id)?.name ?? `#${p.scope_id}` });
  if (p.scope_type === "tag") return t("policies.scopeLine.tag", { tag: p.tag ?? "" });
  return t("policies.scopeLine.all");
}

export function PoliciesAdmin() {
  const { t, locale } = useI18n();
  const q = usePolicies();
  const ctx = useFormContext();
  const save = useSavePolicy();
  const del = useDeletePolicy();
  const phone = useIsPhone();
  const [editing, setEditing] = useState<{ id: number | null; initial: PolicyIn } | null>(null);
  const [serverError, setServerError] = useState<{ code: string | null; text: string } | null>(null);
  const [deleting, setDeleting] = useState<Policy | null>(null);
  const policies = q.data?.policies ?? [];

  const open = (p: Policy | null) => {
    setServerError(null);
    setEditing({ id: p?.id ?? null, initial: p ? policyToInput(p) : emptyPolicy() });
  };
  const onSave = (body: PolicyIn) => {
    if (!editing) return;
    save.mutate(
      { id: editing.id, body },
      {
        onSuccess: (p) => {
          toast.success(t("policies.saved", { name: p.name }));
          setEditing(null);
        },
        onError: (e) => {
          const err = wave1Error(e);
          setServerError({ code: err.code, text: errorText(err, locale) });
        },
      },
    );
  };
  const toggle = (p: Policy, on: boolean) => save.mutate({ id: p.id, body: { ...policyToInput(p), enabled: on } }, { onError: (e) => toast.error(errorText(wave1Error(e), locale)) });

  return (
    <div className="space-y-5" data-testid="policies-admin">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>{t("policies.title")}</CardTitle>
            <Button size="sm" onClick={() => open(null)} data-testid="policy-new">
              <Plus aria-hidden />
              {t("policies.new")}
            </Button>
          </div>
          <CardDescription>{t("policies.lead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {q.isLoading ? <Loading /> : null}
          {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
          {q.isSuccess && !policies.length ? (
            <p className="rounded-xl bg-fill-3 p-3 type-callout text-label-2" data-testid="policies-empty">
              {t("policies.empty")}
            </p>
          ) : null}
          <ul className="flex flex-col gap-2">
            {policies.map((p) => (
              <li key={p.id} className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3 sm:flex-row sm:items-start" data-testid={`policy-${p.id}`}>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 type-headline text-label-1">
                    {p.name}
                    <span className={p.effect === "refuse" ? "rounded-full bg-status-infeasible px-2 type-caption text-status-infeasible-fg" : "rounded-full bg-tint-soft px-2 type-caption text-tint-text"}>{t(`policies.effect.${p.effect}`)}</span>
                    {!p.enabled ? <span className="rounded-full bg-fill-2 px-2 type-caption text-label-2">{t("policies.off")}</span> : null}
                  </p>
                  <p className="type-footnote text-label-2">
                    {[scopeText(p, ctx, t), p.role_codes.length ? t("policies.rolesLine", { roles: p.role_codes.map((c) => ctx.roles?.find((r) => r.code === c)?.name ?? c).join(", ") }) : t("policies.everyone"), p.term_id ? (ctx.terms.find((x) => x.id === p.term_id)?.name ?? null) : null].filter(Boolean).join(" · ")}
                  </p>
                  <ul className="mt-1 list-disc pl-4 type-callout text-label-1" data-testid={`policy-summary-${p.id}`}>
                    {(locale === "tr" ? p.summary.tr : p.summary.en).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  {p.note ? <p className="mt-1 type-footnote text-label-3">{p.note}</p> : null}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Switch checked={p.enabled} onCheckedChange={(v) => toggle(p, v)} aria-label={t("policies.toggle", { name: p.name })} />
                  <IconButton label={t("policies.edit", { name: p.name })} onClick={() => open(p)} data-testid={`policy-edit-${p.id}`}>
                    <Pencil aria-hidden />
                  </IconButton>
                  <IconButton label={t("policies.delete", { name: p.name })} onClick={() => setDeleting(p)} data-testid={`policy-delete-${p.id}`}>
                    <Trash2 aria-hidden />
                  </IconButton>
                </div>
              </li>
            ))}
          </ul>
          <p className="type-footnote text-label-3">{t("policies.exemptNote")}</p>
        </CardContent>
      </Card>

      {q.data ? <ExamPeriodCard exam={q.data.exam_period} rooms={ctx.rooms} /> : null}

      <Sheet open={!!editing} onOpenChange={(o) => !o && !save.isPending && setEditing(null)}>
        <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[94dvh] data-[side=right]:sm:max-w-xl" data-testid="policy-sheet">
          <SheetHeader className="px-5 pt-5 pb-2">
            <SheetTitle className="type-title-3">{editing?.id ? t("policies.editTitle") : t("policies.newTitle")}</SheetTitle>
            <SheetDescription>{t("policies.formLead")}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-5">{editing ? <PolicyForm key={editing.id ?? "new"} initial={editing.initial} ctx={ctx} busy={save.isPending} serverError={serverError} onSave={onSave} onCancel={() => setEditing(null)} /> : null}</div>
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("policies.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("policies.deleteBody")}
        confirmLabel={t("policies.deleteConfirm")}
        destructive
        busy={del.isPending}
        onConfirm={() =>
          deleting &&
          del.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(t("policies.deleted", { name: deleting.name }));
              setDeleting(null);
            },
            onError: (e) => toast.error(errorText(wave1Error(e), locale)),
          })
        }
      />
    </div>
  );
}

const MODES: ExamMode[] = ["off", "request", "closed"];

function ExamPeriodCard({ exam, rooms }: { exam: { mode: ExamMode; from_exam_timetable: boolean; room_ids: number[] }; rooms: { id: number; name: string }[] }) {
  const { t, locale } = useI18n();
  const save = useSaveExamPeriod();
  const fromId = useId();
  const addId = useId();
  const fail = (e: unknown) => toast.error(errorText(wave1Error(e), locale));
  const ok = () => toast.success(t("policies.exam.saved"));
  const chosen = exam.room_ids.map((id) => ({ id, name: rooms.find((r) => r.id === id)?.name ?? `#${id}` }));
  return (
    <Card data-testid="exam-period">
      <CardHeader>
        <CardTitle>{t("policies.exam.title")}</CardTitle>
        <CardDescription>{t("policies.exam.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="type-footnote font-medium text-label-2" id={`${fromId}-mode`}>
            {t("policies.exam.mode")}
          </span>
          <SegmentedControl aria-labelledby={`${fromId}-mode`} value={exam.mode} onValueChange={(v) => save.mutate({ mode: v as ExamMode }, { onSuccess: ok, onError: fail })} options={MODES.map((m) => ({ value: m, label: t(`policies.exam.modes.${m}` as MessageKey), testId: `exam-mode-${m}` }))} />
          <p className="type-footnote text-label-3">{t(`policies.exam.hint.${exam.mode}` as MessageKey)}</p>
        </div>
        <div className="flex min-h-11 items-center justify-between gap-4">
          <div className="min-w-0">
            <Label htmlFor={fromId} className="type-callout font-medium text-label-1">
              {t("policies.exam.fromTimetable")}
            </Label>
            <p className="type-footnote text-label-2">{t("policies.exam.fromTimetableHint")}</p>
          </div>
          <Switch id={fromId} checked={exam.from_exam_timetable} onCheckedChange={(v) => save.mutate({ from_exam_timetable: v }, { onSuccess: ok, onError: fail })} />
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor={addId} className="type-footnote font-medium text-label-2">
            {t("policies.exam.rooms")}
          </label>
          {chosen.length ? (
            <div className="flex flex-wrap gap-2" data-testid="exam-rooms">
              {chosen.map((r) => (
                <Chip key={r.id} removeLabel={t("policies.exam.removeRoom", { name: r.name })} onRemove={() => save.mutate({ room_ids: exam.room_ids.filter((x) => x !== r.id) }, { onSuccess: ok, onError: fail })}>
                  {r.name}
                </Chip>
              ))}
            </div>
          ) : (
            <p className="type-footnote text-label-3">{t("policies.exam.noRooms")}</p>
          )}
          <NativeSelect id={addId} value="" onChange={(e) => e.target.value && save.mutate({ room_ids: [...exam.room_ids, Number(e.target.value)] }, { onSuccess: ok, onError: fail })} className="sm:max-w-xs" data-testid="exam-add-room">
            <option value="">{t("policies.exam.addRoom")}</option>
            {rooms
              .filter((r) => !exam.room_ids.includes(r.id))
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
          </NativeSelect>
        </div>
      </CardContent>
    </Card>
  );
}
