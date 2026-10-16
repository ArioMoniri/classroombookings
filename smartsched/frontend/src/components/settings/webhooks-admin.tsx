"use client";
/**
 * Settings › Entegrasyonlar › Giden webhook'lar: `/webhooks` (backend `app/api/v1/webhooks.py`, `setup.settings`).
 * Booking and approval events as signed POSTs (HMAC-SHA256, `whsec_…`) to the institution's own systems.
 *
 * - The list is a card list on every width (URL, events, active / paused with the reason, failures, the secret's
 *   last four characters), each with Test, Rotate secret, Pause / Resume and Delete (≥ 44 px on touch).
 * - New: URL (https; private and loopback addresses are refused by the backend, M-41: its sentence is shown next
 *   to the field), events (or every event), a description. The secret is shown once, with Copy.
 * - Recent deliveries per webhook (status, HTTP code, error) open on demand.
 * Nothing is sent while the "Webhook gönderimi" switch (CalendarSyncAdmin) is off.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Copy, Plus, RotateCcw, Send, Trash2, Webhook as WebhookIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ResponsiveDialog } from "@/components/approvals/responsive-dialog";
import { afKeys, approvalFirst, useWebhookDeliveries, useWebhookEventTypes, useWebhooks, type Webhook } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export function WebhooksAdmin() {
  const { t, locale } = useI18n();
  const list = useWebhooks();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<{ url: string; secret: string } | null>(null);
  const [deleting, setDeleting] = useState<Webhook | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: afKeys.webhooks });
  const run = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    try {
      await fn();
      await refresh();
      toast.success(ok);
    } catch (e) {
      toast.error(errorText(wave1Error(e), locale) || t("notifications.admin.failed"));
    } finally {
      setBusy(null);
    }
  };
  const rows = list.data ?? [];
  return (
    <Card data-testid="webhooks-admin">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <WebhookIcon className="size-4 text-label-3" aria-hidden />
            {t("notifications.admin.webhooks.title")}
          </CardTitle>
          <Button size="sm" onClick={() => setCreating(true)} data-testid="webhook-new">
            <Plus aria-hidden />
            {t("notifications.admin.webhooks.new")}
          </Button>
        </div>
        <CardDescription>{t("notifications.admin.webhooks.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {list.isError ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {errorText(wave1Error(list.error), locale)}
          </p>
        ) : null}
        {list.isSuccess && rows.length === 0 ? (
          <p className="type-callout text-label-2" data-testid="webhooks-empty">
            {t("notifications.admin.webhooks.empty")}
          </p>
        ) : null}
        {secret ? (
          <SecretOnce url={secret.url} secret={secret.secret} onDone={() => setSecret(null)} />
        ) : null}
        <ul className="flex flex-col gap-2" data-testid="webhooks-list">
          {rows.map((w) => (
            <WebhookRow
              key={w.id}
              w={w}
              busy={busy}
              onTest={() => void run(`test-${w.id}`, () => approvalFirst.webhooks.test(w.id), t("notifications.admin.webhooks.testSent"))}
              onToggle={() => void run(`toggle-${w.id}`, () => approvalFirst.webhooks.update(w.id, { active: !w.active }), t("notifications.admin.saved"))}
              onRotate={() =>
                void run(
                  `rotate-${w.id}`,
                  async () => {
                    const out = await approvalFirst.webhooks.rotate(w.id);
                    setSecret({ url: w.url, secret: out.secret });
                  },
                  t("notifications.admin.webhooks.rotated"),
                )
              }
              onDelete={() => setDeleting(w)}
            />
          ))}
        </ul>
      </CardContent>
      <CreateWebhook
        open={creating}
        onOpenChange={setCreating}
        onCreated={(url, s) => {
          setCreating(false);
          setSecret({ url, secret: s });
          void refresh();
          toast.success(t("notifications.admin.webhooks.created"));
        }}
      />
      <ResponsiveDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && !busy && setDeleting(null)}
        role="alertdialog"
        title={t("notifications.admin.webhooks.deleteTitle", { url: deleting?.url ?? "" })}
        description={t("notifications.admin.webhooks.deleteBody")}
        testId="webhook-delete-confirm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={!!busy}>
              {t("crbs.common.cancel")}
            </Button>
            <Button
              variant="destructive"
              {...busyProps(busy === "delete")}
              onClick={() => {
                const w = deleting;
                if (!w) return;
                void run("delete", () => approvalFirst.webhooks.remove(w.id), t("notifications.admin.webhooks.deleted")).then(() => setDeleting(null));
              }}
              data-testid="webhook-delete-confirm-button"
            >
              <BusyLabel busy={busy === "delete"} label={t("busy.deleting")}>
                {t("crbs.common.delete")}
              </BusyLabel>
            </Button>
          </>
        }
      />
    </Card>
  );
}

function WebhookRow({ w, busy, onTest, onToggle, onRotate, onDelete }: { w: Webhook; busy: string | null; onTest: () => void; onToggle: () => void; onRotate: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const [showDeliveries, setShowDeliveries] = useState(false);
  return (
    <li className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3" data-testid={`webhook-${w.id}`}>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="break-all font-mono type-footnote text-label-1">{w.url}</span>
        {w.description ? <span className="type-footnote text-label-2">{w.description}</span> : null}
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 type-caption text-label-2">
          <span className={cn("font-medium", w.active ? "text-status-feasible-fg" : "text-status-warning-fg")}>
            {w.active ? t("notifications.admin.webhooks.active") : w.disabled_reason ? t("notifications.admin.webhooks.pausedWhy", { reason: w.disabled_reason }) : t("notifications.admin.webhooks.paused")}
          </span>
          {w.consecutive_failures ? <span>{t("notifications.admin.webhooks.failures", { n: w.consecutive_failures })}</span> : null}
          {w.secret_hint ? <span>{t("notifications.admin.webhooks.secretHint", { hint: w.secret_hint })}</span> : null}
        </span>
        <span className="flex flex-wrap gap-1 pt-1">
          {w.events.map((e) => (
            <span key={e} className="rounded-full bg-fill-2 px-2 py-0.5 font-mono type-caption text-label-2">
              {e === "*" ? t("notifications.admin.webhooks.allEvents") : e}
            </span>
          ))}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onTest} {...busyProps(busy === `test-${w.id}`, !!busy)} data-testid={`webhook-test-${w.id}`}>
          <Send aria-hidden />
          <BusyLabel busy={busy === `test-${w.id}`} label={t("busy.sending")}>
            {t("notifications.admin.webhooks.test")}
          </BusyLabel>
        </Button>
        <Button size="sm" variant="outline" onClick={onToggle} {...busyProps(busy === `toggle-${w.id}`, !!busy)} data-testid={`webhook-toggle-${w.id}`}>
          {w.active ? t("notifications.admin.webhooks.pause") : t("notifications.admin.webhooks.resume")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onRotate} {...busyProps(busy === `rotate-${w.id}`, !!busy)} data-testid={`webhook-rotate-${w.id}`}>
          <RotateCcw aria-hidden />
          {t("notifications.admin.webhooks.rotate")}
        </Button>
        <Button size="sm" variant="ghost" aria-expanded={showDeliveries} onClick={() => setShowDeliveries((x) => !x)} data-testid={`webhook-deliveries-${w.id}`}>
          {t("notifications.admin.webhooks.deliveries")}
        </Button>
        <Button size="sm" variant="ghost" className="text-status-infeasible-fg sm:ml-auto" onClick={onDelete} disabled={!!busy} data-testid={`webhook-delete-${w.id}`}>
          <Trash2 aria-hidden />
          {t("crbs.common.delete")}
        </Button>
      </div>
      {showDeliveries ? <Deliveries id={w.id} /> : null}
    </li>
  );
}

function Deliveries({ id }: { id: number }) {
  const { t, locale } = useI18n();
  const q = useWebhookDeliveries(id);
  if (q.isLoading) return <p className="type-footnote text-label-2">{t("crbs.common.loading")}</p>;
  if (q.isError) return <p role="alert" className="type-footnote text-status-infeasible-fg">{errorText(wave1Error(q.error), locale)}</p>;
  const rows = q.data ?? [];
  if (!rows.length) return <p className="type-footnote text-label-2">{t("notifications.admin.webhooks.noDeliveries")}</p>;
  return (
    <ul className="flex flex-col overflow-hidden rounded-lg bg-fill-2" data-testid={`webhook-delivery-list-${id}`}>
      {rows.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 type-caption text-label-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
          <span className="font-mono text-label-1">{d.event_type}</span>
          <span className={cn("font-medium", d.status === "SENT" ? "text-status-feasible-fg" : d.status === "FAILED" ? "text-status-infeasible-fg" : "text-label-2")}>{d.status}</span>
          {d.response_status ? <span className="tabular-nums">HTTP {d.response_status}</span> : null}
          {d.created_at ? <span className="tabular-nums">{new Date(d.created_at).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB")}</span> : null}
          {d.last_error ? <span className="w-full break-all text-status-infeasible-fg">{d.last_error}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function SecretOnce({ url, secret, onDone }: { url: string; secret: string; onDone: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-status-warning p-3" role="status" data-testid="webhook-secret">
      <p className="type-callout text-label-1">{t("notifications.admin.webhooks.secretOnce", { url })}</p>
      <code className="break-all rounded-lg bg-(--mat-thick-solid) px-2 py-1.5 font-mono type-footnote text-label-1">{secret}</code>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            void navigator.clipboard?.writeText(secret).then(() => toast.success(t("notifications.admin.webhooks.copied")));
          }}
        >
          <Copy aria-hidden />
          {t("notifications.admin.webhooks.copy")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          {t("notifications.admin.webhooks.secretDone")}
        </Button>
      </div>
    </div>
  );
}

function CreateWebhook({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (url: string, secret: string) => void }) {
  const { t, locale } = useI18n();
  const types = useWebhookEventTypes(open);
  const [url, setUrl] = useState("");
  const [all, setAll] = useState(true);
  const [events, setEvents] = useState<Set<string>>(new Set());
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = useId();
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setUrl("");
      setAll(true);
      setEvents(new Set());
      setDescription("");
      setError(null);
    }
  }
  const chosen = all ? ["*"] : [...events];
  const valid = url.trim().length > 0 && chosen.length > 0;
  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const out = await approvalFirst.webhooks.create({ url: url.trim(), events: chosen, description: description.trim() || null, active: true });
      onCreated(out.url, out.secret);
    } catch (e) {
      setError(errorText(wave1Error(e), locale) || t("notifications.admin.failed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={(o) => !busy && onOpenChange(o)}
      title={t("notifications.admin.webhooks.new")}
      description={t("notifications.admin.webhooks.newLead")}
      testId="webhook-dialog"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("crbs.common.cancel")}
          </Button>
          <Button type="submit" form={`${base}-form`} {...busyProps(busy, !valid)} data-testid="webhook-save">
            <BusyLabel busy={busy} label={t("busy.saving")}>
              {t("notifications.admin.webhooks.create")}
            </BusyLabel>
          </Button>
        </>
      }
    >
      <form
        id={`${base}-form`}
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${base}-url`}>{t("notifications.admin.webhooks.url")}</Label>
          <Input id={`${base}-url`} type="url" inputMode="url" autoComplete="off" spellCheck={false} placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} aria-invalid={error ? true : undefined} aria-describedby={error ? `${base}-err` : undefined} className="font-mono text-base sm:text-[13px]" data-testid="webhook-url" />
          {error ? (
            <p id={`${base}-err`} role="alert" className="type-footnote text-status-infeasible-fg" data-testid="webhook-error">
              {error}
            </p>
          ) : null}
        </div>
        <fieldset className="flex min-w-0 flex-col gap-1">
          <legend className="mb-1.5 type-headline text-label-1">{t("notifications.admin.webhooks.events")}</legend>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 type-callout text-label-1">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="size-5 accent-(--accent)" data-testid="webhook-all-events" />
            {t("notifications.admin.webhooks.allEvents")}
          </label>
          {!all ? (
            <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
              {(types.data ?? []).map((e) => (
                <label key={e} className="flex min-h-11 cursor-pointer items-center gap-3 font-mono type-footnote text-label-1">
                  <input
                    type="checkbox"
                    checked={events.has(e)}
                    onChange={(ev) => {
                      const next = new Set(events);
                      if (ev.target.checked) next.add(e);
                      else next.delete(e);
                      setEvents(next);
                    }}
                    className="size-5 accent-(--accent)"
                  />
                  {e}
                </label>
              ))}
            </div>
          ) : null}
        </fieldset>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${base}-desc`}>{t("notifications.admin.webhooks.description")}</Label>
          <Input id={`${base}-desc`} maxLength={255} value={description} onChange={(e) => setDescription(e.target.value)} className="text-base sm:text-[13px]" />
        </div>
      </form>
    </ResponsiveDialog>
  );
}
