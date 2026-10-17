"use client";
/**
 * Guided automation setup (W3-HUB): n8n / Activepieces / Pipedream / Zapier receive SmartSched events as signed
 * webhooks. Four steps: create the trigger on the platform (what to click, with the platform's docs), paste its
 * URL here (POST /webhooks; the backend refuses private / loopback targets), copy the signing secret (shown once)
 * plus the headers and a signature-check snippet into the platform, send a test event (POST /webhooks/{id}/test)
 * and see whether it arrived. Uses the existing webhooks API (lib/api/approval-first.ts); nothing new is stored.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink, RotateCcw, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { afKeys, approvalFirst, useIntegrationSettings, useSaveIntegrationSettings, useWebhookDeliveries, useWebhooks, type Webhook } from "@/lib/api/approval-first";
import { problemText } from "@/lib/api/error-text";
import { integrationsKeys } from "@/lib/api/integrations";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { PLATFORMS, PRESETS, SIGNATURE_HEADERS, checkUrl, galleryHref, testResult, verifySnippet, type Platform } from "./integrations-model";

const EVENT_SETS = {
  all: ["*"],
  bookings: ["booking.created", "booking.updated", "booking.cancelled"],
  approvals: ["approval.requested", "approval.step", "approval.approved", "approval.rejected", "approval.expired", "approval.withdrawn"],
} as const;
type EventSet = keyof typeof EVENT_SETS;

export function CopyField({ label, value, mono = true, multiline = false, testId }: { label: string; value: string; mono?: boolean; multiline?: boolean; testId?: string }) {
  const { t } = useI18n();
  const id = useId();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("integrations.guided.copied"));
    } catch {
      toast.error(t("integrations.guided.copyFailed"));
    }
  };
  return (
    <div className="grid gap-1.5" data-testid={testId}>
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <Button size="sm" variant="outline" onClick={copy} aria-label={t("integrations.guided.copyWhat", { what: label })} className="pointer-coarse:min-h-11">
          <Copy aria-hidden />
          {t("integrations.guided.copy")}
        </Button>
      </div>
      {multiline ? (
        <pre id={id} tabIndex={0} className={cn("max-h-56 overflow-auto rounded-xl bg-fill-2 p-3 type-caption text-label-1 whitespace-pre", mono && "font-mono")} aria-label={label}>
          {value}
        </pre>
      ) : (
        <Input id={id} readOnly value={value} className={cn("pointer-coarse:text-base", mono && "font-mono")} onFocus={(e) => e.currentTarget.select()} />
      )}
    </div>
  );
}

export function GuidedWebhook({ initialPlatform, webhookId }: { initialPlatform: Platform | null; webhookId: number | null }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [platform, setPlatform] = useState<Platform>(initialPlatform ?? "n8n");
  const hooks = useWebhooks();
  const settings = useIntegrationSettings();
  const saveSettings = useSaveIntegrationSettings();
  const [createdId, setCreatedId] = useState<number | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<EventSet>("all");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [deliveryId, setDeliveryId] = useState<number | null>(null);
  const urlId = useId();
  const urlHint = useId();
  const resultRef = useRef<HTMLParagraphElement>(null);
  const endpointId = createdId ?? webhookId;
  const endpoint: Webhook | undefined = hooks.data?.find((h) => h.id === endpointId);
  const deliveries = useWebhookDeliveries(deliveryId !== null ? endpointId : null);
  const result = testResult(deliveries.data ?? [], deliveryId);
  const preset = PRESETS[platform];
  const urlState = checkUrl(url, platform);

  // poll the delivery log until the test event is SENT or FAILED (the worker sends it within seconds)
  useEffect(() => {
    if (result?.state !== "pending" || endpointId === null) return;
    const timer = window.setInterval(() => void qc.invalidateQueries({ queryKey: afKeys.deliveries(endpointId) }), 1500);
    return () => window.clearInterval(timer);
  }, [result?.state, endpointId, qc]);
  useEffect(() => {
    if (result && result.state !== "pending") {
      void qc.invalidateQueries({ queryKey: integrationsKeys.status });
      resultRef.current?.focus();
    }
  }, [result, qc]);

  const refresh = async () => {
    await Promise.all([qc.invalidateQueries({ queryKey: afKeys.webhooks }), qc.invalidateQueries({ queryKey: integrationsKeys.status })]);
  };

  const save = async () => {
    if (urlState === "invalid" || urlState === "empty") {
      setSaveError(t("integrations.guided.urlInvalid"));
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const created = await approvalFirst.webhooks.create({ url: url.trim(), events: [...EVENT_SETS[events]], description: `${platform} akışı` });
      setCreatedId(created.id);
      setSecret(created.secret);
      toast.success(t("integrations.guided.saved", { name: preset.name }));
      await refresh();
    } catch (e) {
      setSaveError(problemText(e, locale) ?? t("integrations.toast.failed", { reason: String((e as Error).message ?? e) }));
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    if (endpointId === null) return;
    try {
      const r = await approvalFirst.webhooks.rotate(endpointId);
      setSecret(r.secret);
      toast.success(t("integrations.guided.rotated"));
      await refresh();
    } catch (e) {
      toast.error(problemText(e, locale) ?? String(e));
    }
  };

  const sendTest = async () => {
    if (endpointId === null) return;
    setTesting(true);
    try {
      const r = await approvalFirst.webhooks.test(endpointId);
      setDeliveryId(r.delivery_id);
      await qc.invalidateQueries({ queryKey: afKeys.deliveries(endpointId) });
    } catch (e) {
      toast.error(problemText(e, locale) ?? String(e));
    } finally {
      setTesting(false);
    }
  };

  const primary =
    endpointId === null ? (
      <Button size="lg" onClick={save} disabled={saving} aria-busy={saving || undefined} className="w-full sm:w-auto" data-testid="guided-save">
        <BusyLabel busy={saving} label={t("integrations.guided.saving")}>
          {t("integrations.guided.save")}
        </BusyLabel>
      </Button>
    ) : (
      <Button size="lg" onClick={sendTest} disabled={testing || result?.state === "pending"} aria-busy={testing || undefined} className="w-full sm:w-auto" data-testid="guided-test">
        <Send aria-hidden />
        <BusyLabel busy={testing} label={t("integrations.guided.testing")}>
          {t("integrations.guided.test")}
        </BusyLabel>
      </Button>
    );
  const globalOff = settings.data ? !settings.data.webhooks_enabled : false;

  return (
    <div className="grid gap-6" data-testid="guided-webhook">
      <p className="type-callout text-label-2">{t("integrations.guided.lead")}</p>
      {initialPlatform === null && endpointId === null ? (
        <div className="grid gap-1.5">
          <span id={`${urlId}-p`} className="type-footnote font-medium text-label-1">
            {t("integrations.guided.platform")}
          </span>
          <SegmentedControl<Platform> aria-labelledby={`${urlId}-p`} semantics="radiogroup" fill value={platform} onValueChange={setPlatform} options={PLATFORMS.map((p) => ({ value: p, label: PRESETS[p].name }))} data-testid="guided-platform" />
        </div>
      ) : null}

      <section className="grid gap-2" aria-labelledby={`${urlId}-s1`}>
        <h3 id={`${urlId}-s1`} className="type-headline text-label-1">
          {t("integrations.guided.step1")}
        </h3>
        <p className="type-callout text-label-1">{t(`integrations.guided.how.${platform}`)}</p>
        <a href={preset.docs} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 type-footnote text-tint-text underline-offset-2 hover:underline pointer-coarse:min-h-11">
          <ExternalLink aria-hidden className="size-3.5" />
          {t("integrations.guided.docs", { name: preset.name })}
        </a>
      </section>

      <section className="grid gap-2" aria-labelledby={`${urlId}-s2`}>
        <h3 id={`${urlId}-s2`} className="type-headline text-label-1">
          {t("integrations.guided.step2")}
        </h3>
        {endpoint || endpointId !== null ? (
          <CopyField label={t("integrations.guided.existing")} value={endpoint?.url ?? ""} testId="guided-existing-url" />
        ) : (
          <>
            <Label htmlFor={urlId}>{t("integrations.guided.url")}</Label>
            <Input
              id={urlId}
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              placeholder={preset.example}
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setSaveError(null);
              }}
              aria-describedby={urlHint}
              aria-invalid={saveError ? true : undefined}
              className="pointer-coarse:text-base"
              data-testid="guided-url"
            />
            <p id={urlHint} className="type-footnote text-label-2">
              {saveError ?? (urlState === "hint" ? t("integrations.guided.urlLooksOff", { name: preset.name }) : t("integrations.guided.urlHint"))}
            </p>
            <div className="grid gap-1.5">
              <span id={`${urlId}-ev`} className="type-footnote font-medium text-label-1">
                {t("integrations.guided.events")}
              </span>
              <SegmentedControl<EventSet>
                aria-labelledby={`${urlId}-ev`}
                semantics="radiogroup"
                value={events}
                onValueChange={setEvents}
                options={[
                  { value: "all", label: t("integrations.guided.eventsAll") },
                  { value: "bookings", label: t("integrations.guided.eventsBookings") },
                  { value: "approvals", label: t("integrations.guided.eventsApprovals") },
                ]}
              />
            </div>
          </>
        )}
      </section>

      <section className="grid gap-3" aria-labelledby={`${urlId}-s3`}>
        <h3 id={`${urlId}-s3`} className="type-headline text-label-1">
          {t("integrations.guided.step3")}
        </h3>
        {secret ? (
          <>
            <Alert tone="warning">{t("integrations.guided.secretOnce")}</Alert>
            <CopyField label={t("integrations.guided.secret")} value={secret} testId="guided-secret" />
          </>
        ) : endpoint?.secret_hint ? (
          <p className="type-footnote text-label-2">{t("integrations.guided.secretHint", { hint: endpoint.secret_hint })}</p>
        ) : (
          <p className="type-footnote text-label-3">{t("integrations.guided.saveFirst")}</p>
        )}
        {endpointId !== null ? (
          <Button size="md" variant="outline" onClick={rotate} className="justify-self-start pointer-coarse:min-h-11" data-testid="guided-rotate">
            <RotateCcw aria-hidden />
            {t("integrations.guided.rotate")}
          </Button>
        ) : null}
        <CopyField label={t("integrations.guided.headers")} value={SIGNATURE_HEADERS.join("\n")} multiline />
        <p className="type-footnote text-label-2">{t("integrations.guided.snippetLead")}</p>
        <CopyField label={t("integrations.guided.snippet")} value={verifySnippet(platform)} multiline testId="guided-snippet" />
      </section>

      <section className="grid gap-2" aria-labelledby={`${urlId}-s4`}>
        <h3 id={`${urlId}-s4`} className="type-headline text-label-1">
          {t("integrations.guided.step4")}
        </h3>
        {globalOff ? (
          <Alert tone="info">
            <span className="block">{t("integrations.guided.globalOff")}</span>
            <Button
              size="sm"
              variant="outline"
              className="mt-2 pointer-coarse:min-h-11"
              disabled={saveSettings.isPending}
              onClick={() => saveSettings.mutate({ webhooks_enabled: true }, { onSuccess: () => void qc.invalidateQueries({ queryKey: integrationsKeys.status }) })}
              data-testid="guided-enable-global"
            >
              {t("integrations.guided.enableGlobal")}
            </Button>
          </Alert>
        ) : null}
        <p ref={resultRef} tabIndex={-1} role="status" aria-live="polite" className={cn("type-callout", result?.state === "failed" ? "text-status-infeasible-fg" : "text-label-1")} data-testid="guided-result">
          {endpointId === null
            ? t("integrations.guided.saveFirst")
            : result === null
              ? ""
              : result.state === "pending"
                ? t("integrations.guided.testPending")
                : result.state === "sent"
                  ? t("integrations.guided.testSent", { http: result.http ?? 200 })
                  : t("integrations.guided.testFailed", { reason: result.error ?? (result.http ? `HTTP ${result.http}` : t("integrations.guided.testUnknownReason")) })}
        </p>
        <Link href={galleryHref("automation", "automation.webhooks")} className="type-footnote text-tint-text underline-offset-2 hover:underline pointer-coarse:min-h-11 pointer-coarse:py-2">
          {t("integrations.guided.manageAll")}
        </Link>
      </section>
      {/* MOBILE M-05: the step's primary action stays in thumb reach at every scroll of the setup sheet */}
      <div className="sticky bottom-0 z-10 -mx-5 flex justify-end bg-(--mat-thick) px-5 py-3 hairline-t" data-testid="guided-footer">
        {primary}
      </div>
    </div>
  );
}
