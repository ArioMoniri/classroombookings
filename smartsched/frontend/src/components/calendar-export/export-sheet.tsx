"use client";
/**
 * "Takvimime ekle" (CAL-08, research doc §3.7): three taps, what → how → approve, then the done state.
 *
 * - Phone (< 640 px): a full-screen sheet, one step per screen, the primary action in a sticky footer, 44 px targets.
 *   Desktop: a 560 px right sheet with the same steps.
 * - Step 1 lists the scopes (Derslerim, Bölümümün dersleri per department, Rezervasyonlarım); a scope that is not
 *   allowed shows the backend's reason. Step 2 lists only the channels the organisation configured. Step 3 shows
 *   exactly what is sent (the field bullets, a real sample event) and, while the `calendar_sync` consent is missing,
 *   an unticked consent box; "Onayla ve ekle" gives the consent first (POST /me/consents/calendar_sync), then:
 *   link → POST /calendar/subscriptions (the URLs are shown once), file → the one-off .ics download, push → PUT the
 *   account's scopes (connected) or the provider's OAuth round trip (not connected; resumed on /profile).
 * - Focus: the step heading on open and on every step change; the consent box when it is missing on submit.
 */
import { ArrowLeft } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button, IconButton } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Loading } from "@/components/admin/kit";
import { ConsentRefusal, consentRefusal } from "@/components/privacy/calendar-consent";
import { calendarExportApi, useExportOptions, useRefreshCalendar, useSubscriptions, type SubscriptionUrls } from "@/lib/api/calendar-export";
import { useConsent } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import {
  PENDING_KEY,
  RETURN_PATH,
  approvalFields,
  channelChoices,
  fileName,
  findPushRow,
  notLinked,
  pushAccounts,
  pushProgress,
  pushScope,
  relativeWhen,
  scopeChoices,
  type Channel,
  type PendingPush,
  type ScopeChoice,
  type Step,
} from "./model";
import { ApproveStep, HowStep, LinkResult, StepHeading, WhatStep, backendText, providerName, scopeName } from "./steps";

type Result = { kind: "link"; urls: SubscriptionUrls } | { kind: "file"; name: string } | { kind: "push"; provider: string } | { kind: "redirect"; provider: string };

/** The account-not-verified refusal (CAL-07): the backend's sentence, else ours with the domain it names. */
function refusalText(e: unknown, t: ReturnType<typeof useI18n>["t"], locale: string): string {
  const w = wave1Error(e);
  if (w.code === "account_not_verified") {
    if (w.messageTr || locale !== "tr") return errorText(w, locale);
    const domain = typeof w.data.domain === "string" ? w.data.domain : null;
    return domain ? t("calendarExport.manage.notVerified", { domain }) : t("calendarExport.manage.notVerifiedPlain");
  }
  if (w.code === "department_not_allowed" && !(locale === "tr" ? w.messageTr : null)) return t("calendarExport.reason.department_not_allowed");
  // a coded refusal carries its own sentence (API.md: message_tr first, never the code)
  if (w.code && (w.messageTr || typeof w.data.message_en === "string")) return locale === "tr" ? (w.messageTr ?? String(w.data.message_en)) : String(w.data.message_en ?? w.message);
  return t("calendarExport.failed", { message: backendText(e, locale) });
}

export function CalendarExportSheet({ open, onOpenChange, resume }: { open: boolean; onOpenChange: (open: boolean) => void; resume?: PendingPush | null }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton
        className="gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-[560px] max-sm:inset-0! max-sm:h-dvh! max-sm:w-full! max-sm:max-w-none! max-sm:rounded-none! max-sm:pt-[env(safe-area-inset-top)]"
        data-testid="cal-sheet"
      >
        {open ? <Flow onClose={() => onOpenChange(false)} resume={resume ?? null} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function Flow({ onClose, resume }: { onClose: () => void; resume: PendingPush | null }) {
  const { t, locale } = useI18n();
  const options = useExportOptions();
  const refresh = useRefreshCalendar();
  const consent = useConsent();
  const o = options.data;
  const choices = useMemo(() => scopeChoices(o, locale), [o, locale]);
  const subsQ = useSubscriptions();
  const connections = subsQ.data?.connections;
  const channels = useMemo(() => channelChoices(o, connections), [o, connections]);
  const [since, setSince] = useState(() => Date.now());
  const [step, setStep] = useState<Step>(resume ? "done" : "what");
  const [choice, setChoice] = useState<ScopeChoice | null>(null);
  const [channel, setChannel] = useState<Channel | null>(null);
  const [tick, setTick] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ text: string; href: string } | null>(null);
  const [result, setResult] = useState<Result | null>(resume ? { kind: "push", provider: resume.provider } : null);
  const [resumed] = useState(resume);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const consentRef = useRef<HTMLButtonElement>(null);
  const headingId = useId();

  // focus the step's heading on open and on every step change (T1: "Sheet opens with focus on the heading")
  useEffect(() => {
    const id = window.requestAnimationFrame(() => headingRef.current?.focus({ preventScroll: true }));
    return () => window.cancelAnimationFrame(id);
  }, [step, options.isSuccess]);

  const needsConsent = !!o?.consent?.required && !o.consent.granted;
  const goto = (s: Step) => {
    setError(null);
    setRefusal(null);
    setStep(s);
  };
  const back = () => goto(step === "approve" ? "how" : "what");

  const fail = (e: unknown) => {
    const r = consentRefusal(e, locale);
    if (r) setRefusal(r);
    else setError(refusalText(e, t, locale));
  };

  /** the provider's OAuth round trip with the scopes; resumed on /profile (calendar-export-section.tsx) */
  const redirectToProvider = async (provider: string, scopes: string[]) => {
    if (!choice) return;
    const pending: PendingPush = { provider: provider as PendingPush["provider"], kind: choice.kind, departmentId: choice.departmentId, at: Date.now() };
    try {
      window.sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
    } catch {
      /* private mode: the backend applies the scopes it got with the connect call anyway */
    }
    const { authorize_url } = await calendarExportApi.connect(provider, RETURN_PATH, scopes);
    setResult({ kind: "redirect", provider });
    setStep("done");
    window.location.assign(authorize_url);
  };

  const approve = async () => {
    if (!choice || !channel) return;
    if (needsConsent && !tick) {
      setError(t("calendarExport.approve.needConsent"));
      consentRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      if (needsConsent) await consent.mutateAsync({ purpose: "calendar_sync", grant: true });
      if (channel.kind === "link") {
        const made = await calendarExportApi.create({ scope_kind: choice.kind, scope_id: choice.departmentId, channel: "link" });
        setResult({ kind: "link", urls: made.urls });
      } else if (channel.kind === "file") {
        const r = await calendarExportApi.download(choice.kind, choice.departmentId, fileName(choice.kind, o?.term?.slug, choice.departmentName));
        setResult({ kind: "file", name: r.name });
      } else {
        const scope = pushScope(choice.kind, choice.departmentId);
        if (channel.connected) {
          const current = pushAccounts(o, connections).find((p) => p.provider === channel.provider)?.scopes ?? [];
          setSince(Date.now());
          try {
            await calendarExportApi.pushScopes(channel.provider, [...new Set([...current, scope])]);
            setResult({ kind: "push", provider: channel.provider });
          } catch (e) {
            // an old broad connection cannot take classes (409 reconnect_required): reconnect with fewer permissions,
            // the approval already given covers it
            if (wave1Error(e).code !== "reconnect_required") throw e;
            await redirectToProvider(channel.provider, [...new Set([...current, scope])]);
            return;
          }
        } else {
          await redirectToProvider(channel.provider, [scope]);
          return;
        }
      }
      setStep("done");
      void refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const restart = () => {
    setChoice(null);
    setChannel(null);
    setTick(false);
    setResult(null);
    goto("what");
  };

  const stepNo = step === "what" ? 1 : step === "how" ? 2 : 3;
  const title = step === "what" ? t("calendarExport.what.title") : step === "how" ? t("calendarExport.how.title") : step === "approve" ? t("calendarExport.approve.title") : doneTitle(result, t);

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-step={step}>
      <SheetHeader className="gap-1 pr-14 hairline-b">
        <SheetTitle className="type-headline">{t("calendarExport.sheetTitle")}</SheetTitle>
        <SheetDescription className="sr-only">{t("calendarExport.lead")}</SheetDescription>
        {step !== "done" ? (
          <div className="flex items-center gap-2">
            {step !== "what" ? (
              <IconButton label={t("calendarExport.back")} size="sm" onClick={back} disabled={busy} data-testid="cal-back">
                <ArrowLeft aria-hidden />
              </IconButton>
            ) : null}
            <p className="type-footnote text-label-3" data-testid="cal-step">
              {t("calendarExport.step", { n: stepNo })}
            </p>
          </div>
        ) : null}
      </SheetHeader>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 py-4" role="region" aria-labelledby={headingId}>
        <StepHeading id={headingId} headingRef={headingRef}>
          {title}
        </StepHeading>
        {options.isLoading ? <Loading label={t("calendarExport.loading")} /> : null}
        {options.isError ? <Alert tone="error">{errorText(wave1Error(options.error), locale)}</Alert> : null}
        {o && !o.enabled ? (
          <p className="type-callout text-label-2" data-testid="cal-off">
            {t("calendarExport.off")}
          </p>
        ) : null}
        {o?.enabled && step === "what" ? (
          <WhatStep
            choices={choices}
            notLinked={notLinked(o)}
            contactEmail={o.contact_email ?? null}
            onPick={(c) => {
              setChoice(c);
              goto("how");
            }}
          />
        ) : null}
        {o?.enabled && step === "how" ? (
          <HowStep
            channels={channels}
            domain={o.push_verification?.required ? (o.push_verification.domain ?? null) : null}
            onPick={(c) => {
              setChannel(c);
              goto("approve");
            }}
          />
        ) : null}
        {o?.enabled && step === "approve" && choice && channel ? (
          <ApproveStep choice={choice} channel={channel} fields={approvalFields(choice, o.fields)} needsConsent={needsConsent} consent={tick} onConsent={setTick} consentRef={consentRef} locale={locale} />
        ) : null}
        {step === "done" && result ? <Done result={result} choice={choice} resumed={resumed} since={since} /> : null}
        {error ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="cal-error">
            {error}
          </p>
        ) : null}
        {refusal ? <ConsentRefusal refusal={refusal} /> : null}
      </div>

      {step === "approve" || step === "done" ? (
        <SheetFooter className="sticky bottom-0 pb-[max(1rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end">
          {step === "approve" ? (
            <Button size="lg" className="w-full sm:w-auto" onClick={() => void approve()} {...busyProps(busy)} data-testid="cal-submit">
              <BusyLabel busy={busy} label={t("busy.working")}>
                {channel?.kind === "file" ? t("calendarExport.approve.submitFile") : t("calendarExport.approve.submit")}
              </BusyLabel>
            </Button>
          ) : (
            <>
              {result?.kind !== "redirect" ? (
                <Button variant="ghost" size="lg" className="w-full sm:w-auto" onClick={restart} data-testid="cal-another">
                  {t("calendarExport.done.another")}
                </Button>
              ) : null}
              <Button size="lg" className="w-full sm:w-auto" onClick={onClose} data-testid="cal-finish">
                {t("calendarExport.done.finish")}
              </Button>
            </>
          )}
        </SheetFooter>
      ) : null}
    </div>
  );
}

function doneTitle(result: Result | null, t: ReturnType<typeof useI18n>["t"]): string {
  if (result?.kind === "link") return t("calendarExport.done.linkTitle");
  if (result?.kind === "file") return t("calendarExport.done.fileTitle");
  return t("calendarExport.sheetTitle");
}

function Done({ result, choice, resumed, since }: { result: Result; choice: ScopeChoice | null; resumed: PendingPush | null; since: number }) {
  const { t } = useI18n();
  const kind = choice?.kind ?? resumed?.kind ?? "my_classes";
  const departmentId = choice?.departmentId ?? resumed?.departmentId ?? null;
  const name = scopeName(kind, t, choice?.departmentName);
  if (result.kind === "link") return <LinkResult urls={result.urls} name={name} />;
  if (result.kind === "file") {
    return (
      <div className="grid gap-2" data-testid="cal-file-done">
        <p className="type-callout text-label-1">{t("calendarExport.done.fileName", { name: result.name })}</p>
        <p className="rounded-xl bg-status-warning px-3 py-2 type-footnote text-status-warning-fg">{t("calendarExport.done.fileNote")}</p>
      </div>
    );
  }
  if (result.kind === "redirect") {
    return (
      <p role="status" className="type-callout text-label-2" data-testid="cal-push-redirect">
        {t("calendarExport.done.pushRedirect", { provider: providerName(result.provider, t) })}
      </p>
    );
  }
  return <PushProgress provider={result.provider} kind={kind} departmentId={departmentId} scope={name} since={resumed?.at ?? since} />;
}

function PushProgress({ provider, kind, departmentId, scope, since }: { provider: string; kind: ScopeChoice["kind"]; departmentId: number | null; scope: string; since: number }) {
  const { t, locale } = useI18n();
  const [timedOut, setTimedOut] = useState(false);
  const [lastDone, setLastDone] = useState(false);
  // poll every 3 s until the row says done; give up after two minutes (the manage list keeps the state)
  const subs = useSubscriptions(true, !timedOut && !lastDone);
  const row = findPushRow(subs.data?.rows, provider, kind, departmentId);
  const p = pushProgress(row, since);
  const done = !!p?.done;
  if (done !== lastDone) setLastDone(done);
  useEffect(() => {
    const id = window.setTimeout(() => setTimedOut(true), 120_000);
    return () => window.clearTimeout(id);
  }, []);
  const who = providerName(provider, t);
  const when = relativeWhen(row?.last_synced_at, locale, { today: t("calendarExport.manage.today"), yesterday: t("calendarExport.manage.yesterday") });
  return (
    <div className="grid gap-2" data-testid="cal-push-done" data-done={done ? "" : undefined}>
      <p role="status" className="type-callout text-label-1">
        {done && when
          ? t("calendarExport.done.pushDone", { when: when.label })
          : p && p.m > 0
            ? t("calendarExport.done.pushProgress", { scope, provider: who, n: p.n, m: p.m })
            : t("calendarExport.done.pushWorking", { scope, provider: who })}
      </p>
      {p && p.m > 0 && !done ? (
        <div className="h-1.5 overflow-hidden rounded-full bg-fill-2" aria-hidden>
          <div className="h-full rounded-full bg-tint transition-[width] duration-(--dur-base)" style={{ width: `${Math.round((p.n / p.m) * 100)}%` }} />
        </div>
      ) : null}
    </div>
  );
}
