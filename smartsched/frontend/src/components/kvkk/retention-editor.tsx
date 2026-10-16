"use client";
/**
 * Yönetim › KVKK › Saklama süreleri (`setup.settings`): one row per data class with a retention rule (bookings,
 * audit log, notifications). Every rule ships switched off — nothing is deleted until the institution's KVKK officer
 * agreed the period and an administrator turns it on. The minimum the law needs is enforced (the field's `min` and the
 * backend's 422 `below_floor`); bookings are anonymised, never deleted; a legal hold stops the daily job for that class
 * and needs a written reason. "Şimdi uygula" runs the job once; each row shows its last run and counts. A 422 from
 * `PUT /admin/retention/{class}` lists `errors[]`; each is shown under its field (`retain_days`, `action`, `enabled`,
 * `legal_hold`, `legal_hold_reason`) with the floor / range / allowed actions in the reader's words, and stays until
 * that field is edited; `data_class` (unknown class) and errors without a field are the row's own message.
 */
import { Play } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Field, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { retentionErrors, useRetention, useRunRetention, useSaveRetention, type RetentionField, type RetentionFieldError, type RetentionIn, type RetentionPolicy } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { useDateTime } from "@/components/privacy/privacy-section";

export function RetentionEditor() {
  const { t, locale } = useI18n();
  const q = useRetention();
  const run = useRunRetention();
  const [confirm, setConfirm] = useState(false);
  const rows = q.data ?? [];
  const anyOn = rows.some((r) => r.enabled && !r.legal_hold);
  return (
    <div className="flex flex-col gap-4" data-testid="retention-editor">
      <p className="type-callout text-label-2">{t("kvkk.retention.lead")}</p>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {rows.map((r) => (
        <RetentionRow key={`${r.data_class}-${r.updated_at ?? ""}`} row={r} />
      ))}
      {rows.length ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => setConfirm(true)} {...busyProps(run.isPending, !anyOn)} data-testid="retention-run">
            <BusyLabel busy={run.isPending} label={t("busy.working")} icon={<Play aria-hidden />}>
              {t("kvkk.retention.run")}
            </BusyLabel>
          </Button>
          <p className="type-footnote text-label-3">{anyOn ? t("kvkk.retention.runHint") : t("kvkk.retention.allOff")}</p>
        </div>
      ) : null}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t("kvkk.retention.runTitle")}
        description={t("kvkk.retention.runBody")}
        confirmLabel={t("kvkk.retention.runConfirm")}
        destructive
        busy={run.isPending}
        onConfirm={() =>
          run.mutate(undefined, {
            onSuccess: () => {
              setConfirm(false);
              toast.success(t("kvkk.retention.ran"));
            },
            onError: (e) => toast.error(errorText(wave1Error(e), locale)),
          })
        }
      />
    </div>
  );
}

/** A field's error line under its control (`role="alert"`, linked with `aria-describedby`). */
function FieldError({ id, text, testId }: { id: string; text: string | null; testId: string }) {
  if (!text) return null;
  return (
    <p id={id} className="type-footnote text-status-infeasible-fg" role="alert" data-testid={testId}>
      {text}
    </p>
  );
}

function RetentionRow({ row }: { row: RetentionPolicy }) {
  const { t, locale } = useI18n();
  const save = useSaveRetention();
  const when = useDateTime();
  const ids = { days: useId(), action: useId(), on: useId(), hold: useId(), reason: useId(), err: useId() };
  const [days, setDays] = useState(String(row.retain_days));
  const [action, setAction] = useState(row.action);
  const [hold, setHold] = useState(row.legal_hold);
  const [reason, setReason] = useState(row.legal_hold_reason ?? "");
  const [error, setError] = useState<string | null>(null);
  // the backend's 422 `errors[]`, each shown at its field until that field is edited
  const [errs, setErrs] = useState<Partial<Record<RetentionField, RetentionFieldError>>>({});
  const clear = (field: RetentionField) => setErrs((p) => (p[field] ? { ...p, [field]: undefined } : p));
  const floor = row.floor_days ?? 0;
  const n = Number(days);
  const below = !Number.isFinite(n) || n < floor;
  const dirty = n !== row.retain_days || action !== row.action || hold !== row.legal_hold || (reason.trim() || null) !== (row.legal_hold_reason ?? null);
  const holdNeedsReason = hold && !reason.trim();
  const put = (body: RetentionIn, ok: string) => {
    setError(null);
    setErrs({});
    save.mutate(
      { dataClass: row.data_class, body },
      {
        onSuccess: () => toast.success(ok),
        onError: (e) => {
          const err = wave1Error(e);
          const by = err.status === 422 ? retentionErrors(err.data) : {};
          const { data_class: cls, ...fields } = by;
          if (Object.values(fields).some(Boolean)) setErrs(fields);
          // an unknown class (or any error without a field) is the row's own message
          if (cls) setError(serverText(cls));
          else if (!Object.values(fields).some(Boolean)) setError(errorText(err, locale));
        },
      },
    );
  };
  const actionLabel = (a: string) => (a === "delete" ? t("kvkk.retention.delete") : a === "anonymise" ? t("kvkk.retention.anonymise") : a);
  const serverText = (e: RetentionFieldError) => (locale === "tr" ? e.message_tr : e.message_en);
  /** the field's sentence: the floor / range in the reader's words when the backend sent the numbers, else its text */
  const fieldText = (e: RetentionFieldError | undefined): string | null => {
    if (!e) return null;
    if (e.code === "below_floor" && e.floor_days != null) return t("kvkk.retention.belowFloor", { n: e.floor_days });
    if (e.field === "retain_days" && e.floor_days != null && e.max_days != null) return t("kvkk.retention.range", { floor: e.floor_days, max: e.max_days });
    if (e.field === "action" && e.allowed?.length) return `${serverText(e)} ${t("kvkk.retention.allowed", { list: e.allowed.map(actionLabel).join(", ") })}`;
    return serverText(e);
  };
  const daysError = below ? t("kvkk.retention.belowFloor", { n: floor }) : fieldText(errs.retain_days);
  const reasonError = hold && holdNeedsReason ? t("kvkk.retention.holdReasonRequired") : fieldText(errs.legal_hold_reason);
  const err = (f: string) => `${ids.err}-${f}`;
  const counts = row.last_result ? Object.entries(row.last_result).filter((e): e is [string, number] => typeof e[1] === "number") : [];
  return (
    <Card className="gap-3 px-4 py-4" data-testid={`retention-${row.data_class}`}>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="type-headline text-label-1">{(locale === "tr" ? row.label_tr : row.label_en) ?? row.data_class}</p>
            <p className="type-footnote text-label-2">{row.enabled ? (row.legal_hold ? t("kvkk.retention.held") : t("kvkk.retention.on", { days: row.retain_days })) : t("kvkk.retention.off")}</p>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor={ids.on} className="type-callout text-label-1">
              {t("kvkk.retention.enabled")}
            </Label>
            <Switch id={ids.on} checked={row.enabled} disabled={save.isPending} onCheckedChange={(v) => put({ enabled: v }, v ? t("kvkk.retention.savedOn") : t("kvkk.retention.savedOff"))} aria-invalid={errs.enabled ? true : undefined} aria-describedby={errs.enabled ? err("enabled") : undefined} data-testid={`retention-on-${row.data_class}`} />
          </div>
        </div>
        <FieldError id={err("enabled")} text={fieldText(errs.enabled)} testId={`retention-field-error-${row.data_class}-enabled`} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("kvkk.retention.days")} htmlFor={ids.days} hint={daysError ? undefined : t("kvkk.retention.floor", { n: floor })}>
          <Input
            id={ids.days}
            type="number"
            inputMode="numeric"
            min={floor}
            max={errs.retain_days?.max_days}
            value={days}
            onChange={(e) => {
              setDays(e.target.value);
              clear("retain_days");
            }}
            aria-invalid={daysError ? true : undefined}
            aria-describedby={daysError ? err("retain_days") : undefined}
            data-testid={`retention-days-${row.data_class}`}
          />
          <FieldError id={err("retain_days")} text={daysError} testId={`retention-field-error-${row.data_class}-retain_days`} />
        </Field>
        <Field label={t("kvkk.retention.action")} htmlFor={ids.action} hint={errs.action ? undefined : row.data_class === "booking" ? t("kvkk.retention.bookingAnonymise") : undefined}>
          <NativeSelect
            id={ids.action}
            value={action}
            onChange={(e) => {
              setAction(e.target.value as RetentionPolicy["action"]);
              clear("action");
            }}
            disabled={row.data_class === "booking"}
            aria-invalid={errs.action ? true : undefined}
            aria-describedby={errs.action ? err("action") : undefined}
          >
            <option value="delete">{t("kvkk.retention.delete")}</option>
            <option value="anonymise">{t("kvkk.retention.anonymise")}</option>
          </NativeSelect>
          <FieldError id={err("action")} text={fieldText(errs.action)} testId={`retention-field-error-${row.data_class}-action`} />
        </Field>
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex min-h-11 items-center justify-between gap-4">
          <div className="min-w-0">
            <Label htmlFor={ids.hold} className="type-callout font-medium text-label-1">
              {t("kvkk.retention.hold")}
            </Label>
            <p className="type-footnote text-label-2">{t("kvkk.retention.holdHint")}</p>
          </div>
          <Switch
            id={ids.hold}
            checked={hold}
            onCheckedChange={(v) => {
              setHold(v);
              clear("legal_hold");
            }}
            aria-invalid={errs.legal_hold || (!hold && errs.legal_hold_reason) ? true : undefined}
            aria-describedby={errs.legal_hold ? err("legal_hold") : undefined}
            data-testid={`retention-hold-${row.data_class}`}
          />
        </div>
        <FieldError id={err("legal_hold")} text={fieldText(errs.legal_hold) ?? (!hold ? fieldText(errs.legal_hold_reason) : null)} testId={`retention-field-error-${row.data_class}-legal_hold`} />
      </div>
      {hold ? (
        <Field label={t("kvkk.retention.holdReason")} htmlFor={ids.reason}>
          <Textarea
            id={ids.reason}
            rows={2}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              clear("legal_hold_reason");
            }}
            aria-invalid={reasonError ? true : undefined}
            aria-describedby={reasonError ? err("legal_hold_reason") : undefined}
            data-testid={`retention-reason-${row.data_class}`}
          />
          <FieldError id={err("legal_hold_reason")} text={reasonError} testId={`retention-field-error-${row.data_class}-legal_hold_reason`} />
        </Field>
      ) : null}
      {error ? <Alert tone="error" testId={`retention-error-${row.data_class}`}>{error}</Alert> : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="type-footnote text-label-3" data-testid={`retention-last-${row.data_class}`}>
          {row.last_run_at ? t("kvkk.retention.lastRun", { date: when(row.last_run_at, true), counts: counts.map(([k, v]) => `${k}: ${v}`).join(", ") || "0" }) : t("kvkk.retention.neverRun")}
        </p>
        <Button size="sm" onClick={() => put({ retain_days: n, action, legal_hold: hold, legal_hold_reason: hold ? reason.trim() : null }, t("kvkk.retention.saved"))} {...busyProps(save.isPending, !dirty || below || holdNeedsReason)} data-testid={`retention-save-${row.data_class}`}>
          <BusyLabel busy={save.isPending} label={t("busy.saving")}>
            {t("crbs.common.save")}
          </BusyLabel>
        </Button>
      </div>
    </Card>
  );
}
