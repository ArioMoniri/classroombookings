"use client";
/**
 * The steps of the "Takvimime ekle" sheet (CAL-08, research doc §3.7): what → how → approve → done. Each step is a
 * plain view over the sheet's state (export-sheet.tsx owns the calls). Cards on steps 1 and 2 are the action (one tap
 * each); a scope or a channel that is not available is shown with its reason, never as a fake button.
 */
import { BookOpen, CalendarDays, CalendarPlus, Check, ChevronRight, ClipboardCheck, Copy, Download, Link2, Mail, RefreshCw, Users } from "lucide-react";
import Link from "next/link";
import { useId, useState, type ReactNode, type RefObject } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { BareButton, Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { GRANT_PATH } from "@/components/privacy/calendar-consent";
import type { FieldKey } from "@/lib/api/calendar-export";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { channelKey, sampleParts, subscribeLinks, type Channel, type ScopeChoice } from "./model";

type T = ReturnType<typeof useI18n>["t"];

/** The backend's own sentence (API.md: `message_tr` first in Turkish, `message_en` otherwise, never the code). */
export function backendText(e: unknown, locale: string): string {
  const w = wave1Error(e);
  if (locale === "tr" && w.messageTr) return w.messageTr;
  if (typeof w.data.message_en === "string") return w.data.message_en;
  const text = errorText(w, locale);
  // a response that failed its schema carries zod issues, not FastAPI `{msg}` items: never show "[object Object]"
  return text.includes("[object Object]") && e instanceof Error ? e.message : text;
}

export function providerName(p: string, t: T): string {
  return p === "google" || p === "microsoft" ? t(`calendarPush.provider.${p}`) : p;
}

export function scopeName(kind: string, t: T, department?: string | null): string {
  if (kind === "department_classes" && department) return t("calendarExport.scope.department_named", { department });
  if (kind === "my_classes" || kind === "department_classes" || kind === "my_bookings" || kind === "my_duties") return t(`calendarExport.scope.${kind}`);
  return kind;
}

export function channelName(c: Channel, t: T): string {
  if (c.kind === "push") return t("calendarExport.how.push", { provider: providerName(c.provider, t) });
  return t(c.kind === "link" ? "calendarExport.how.link" : "calendarExport.how.file");
}

export function reasonText(choice: Pick<ScopeChoice, "reason" | "reasonText">, t: T): string | null {
  if (!choice.reason) return null;
  if (choice.reason === "other") return choice.reasonText ?? t("calendarExport.reason.other");
  return t(`calendarExport.reason.${choice.reason}`);
}

/** A step's heading: focus lands here on every step change (never on <body>). */
export function StepHeading({ id, headingRef, children }: { id: string; headingRef: RefObject<HTMLHeadingElement | null>; children: ReactNode }) {
  return (
    <h3 id={id} ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus) rounded-sm" data-testid="cal-step-heading">
      {children}
    </h3>
  );
}

/** "Gelişmiş": the details a first-time user does not need (owner's simplicity principle, 2026-10-17). */
export function Advanced({ children, testId, className }: { children: ReactNode; testId: string; className?: string }) {
  const { t } = useI18n();
  return (
    <details className={cn("group rounded-xl px-3 edge-control", className)} data-testid={testId}>
      <summary className="flex min-h-11 cursor-pointer items-center gap-1 type-callout font-medium text-label-2 marker:content-none focus-visible:outline-2 focus-visible:outline-(--focus) rounded-lg" data-testid={`${testId}-toggle`}>
        <ChevronRight className="size-4 shrink-0 transition-transform group-open:rotate-90" aria-hidden />
        {t("calendarExport.advanced")}
      </summary>
      <div className="grid gap-3 pb-3">{children}</div>
    </details>
  );
}

const cardClass = "flex w-full min-h-14 items-start gap-3 rounded-2xl bg-fill-3 px-4 py-3 text-left edge-control transition-colors hover:bg-fill-2";

function ScopeIcon({ kind }: { kind: string }) {
  const Icon = kind === "my_classes" ? BookOpen : kind === "department_classes" ? Users : kind === "my_duties" ? ClipboardCheck : CalendarDays;
  return <Icon className="mt-0.5 size-5 shrink-0 text-tint-text" aria-hidden />;
}

/** CAL10-F01: many departments behind one card and a search (Turkish-insensitive), at most 8 shown at a time. */
function DepartmentGroup({ choices, card }: { choices: ScopeChoice[]; card: (c: ScopeChoice) => ReactNode }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const id = useId();
  const fold = (x: string) => x.toLocaleLowerCase("tr");
  const hits = choices.filter((c) => !q.trim() || fold(c.departmentName ?? "").includes(fold(q.trim())));
  const shown = hits.slice(0, 8);
  return (
    <li data-testid="cal-scope-departments">
      <BareButton className={cardClass} aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)} data-testid="cal-scope-departments-toggle">
        <ScopeIcon kind="department_classes" />
        <span className="grid min-w-0 flex-1 gap-0.5">
          <span className="type-headline text-label-1">{t("calendarExport.what.departments")}</span>
          <span className="type-footnote text-label-2">{t("calendarExport.what.departmentsN", { n: choices.length })}</span>
        </span>
        <ChevronRight className={cn("mt-0.5 size-4 shrink-0 self-center text-label-3 transition-transform", open && "rotate-90")} aria-hidden />
      </BareButton>
      {open ? (
        <div id={id} className="mt-2 grid gap-2 pl-2">
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("calendarExport.what.departmentsSearch")} aria-label={t("calendarExport.what.departmentsSearch")} className="pointer-coarse:text-base" autoFocus data-testid="cal-departments-search" />
          <ul className="grid gap-2">{shown.map((c) => card(c))}</ul>
          {hits.length === 0 ? <p className="type-footnote text-label-2">{t("calendarExport.what.departmentsNone")}</p> : null}
          {hits.length > shown.length ? <p className="type-footnote text-label-3">{t("calendarExport.what.departmentsMore", { n: hits.length - shown.length })}</p> : null}
        </div>
      ) : null}
    </li>
  );
}

/* ------------------------------------------------------------------------------------- 1 · what */

export function WhatStep({ choices, onPick, notLinked, contactEmail }: { choices: ScopeChoice[]; onPick: (c: ScopeChoice) => void; notLinked: boolean; contactEmail: string | null }) {
  const { t } = useI18n();
  const card = (c: ScopeChoice) => {
        const lead =
          c.kind === "my_classes"
            ? c.hours !== null
              ? t("calendarExport.what.my_classes", { n: c.hours })
              : t("calendarExport.what.my_classesPlain")
            : c.kind === "department_classes"
              ? t("calendarExport.what.department_classes", { department: c.departmentName ?? "" })
              : c.kind === "my_duties"
                ? t("calendarExport.what.my_duties")
                : t("calendarExport.what.my_bookings");
        const name = c.kind === "department_classes" && c.departmentName ? t("calendarExport.scope.department_named", { department: c.departmentName }) : scopeName(c.kind, t);
        const why = reasonText(c, t);
        const body = (
          <>
            <ScopeIcon kind={c.kind} />
            <span className="grid min-w-0 flex-1 gap-0.5">
              <span className="type-headline text-label-1">{name}</span>
              <span className="type-footnote text-label-2">{lead}</span>
              {c.available && c.upcoming !== null && c.kind !== "my_classes" ? <span className="type-footnote text-label-3">{t("calendarExport.what.upcoming", { n: c.upcoming })}</span> : null}
              {why ? (
                <span className="type-footnote text-status-warning-fg" data-testid={`cal-scope-reason-${c.key}`}>
                  {why}
                </span>
              ) : null}
            </span>
          </>
        );
        return (
          <li key={c.key}>
            {c.available ? (
              <BareButton className={cardClass} onClick={() => onPick(c)} data-testid={`cal-scope-${c.key}`}>
                {body}
                <ChevronRight className="mt-0.5 size-4 shrink-0 self-center text-label-3" aria-hidden />
              </BareButton>
            ) : (
              <div className={cn(cardClass, "hover:bg-fill-3")} aria-disabled="true" data-testid={`cal-scope-${c.key}`} data-disabled="">
                {body}
              </div>
            )}
          </li>
        );
  };
  // CAL10-F01: a department-feed holder got one card per department (146): above 3, one "Bölüm dersleri" card that
  // opens a search, the person's own department first (the backend's default), and the other scopes stay in place
  const depts = choices.filter((c) => c.kind === "department_classes");
  const grouped = depts.length > 3;
  return (
    <ul className="grid gap-2" data-testid="cal-scopes">
      {choices.map((c) => (!grouped || c.kind !== "department_classes" ? card(c) : c === depts[0] ? <DepartmentGroup key="departments" choices={depts} card={card} /> : null))}
      {notLinked ? (
        <li className="flex flex-wrap items-center gap-2 px-1 pt-1" data-testid="cal-not-linked">
          <Button
            variant="outline"
            size="sm"
            className="pointer-coarse:min-h-11"
            nativeButton={false}
            render={<a href={`mailto:${contactEmail ?? ""}?subject=${encodeURIComponent(t("calendarExport.what.writeOfficeSubject"))}`} data-testid="cal-write-office" />}
          >
            <Mail aria-hidden />
            {t("calendarExport.what.writeOffice")}
          </Button>
        </li>
      ) : null}
    </ul>
  );
}

/* ------------------------------------------------------------------------------------- 2 · how */

export function HowStep({ channels, onPick, domain, linkNote = null }: { channels: Channel[]; onPick: (c: Channel) => void; domain?: string | null; /** CAL10-F02: why there is no link channel */ linkNote?: string | null }) {
  const { t } = useI18n();
  const refreshId = useId();
  const note = linkNote ? <p className="type-footnote text-label-2" data-testid="cal-link-note">{linkNote}</p> : null;
  if (!channels.length) return <>{note}<p className="type-callout text-label-2" data-testid="cal-no-channels">{t("calendarExport.how.none")}</p></>;
  return (
    <div className="grid gap-4">
      {note}
      <ul className="grid gap-2" data-testid="cal-channels">
        {channels.map((c) => {
          const Icon = c.kind === "push" ? RefreshCw : c.kind === "link" ? Link2 : Download;
          const lead = c.kind === "push" ? t("calendarExport.how.pushLead") : c.kind === "link" ? t("calendarExport.how.linkLead") : t("calendarExport.how.fileLead");
          return (
            <li key={channelKey(c)}>
              <BareButton className={cardClass} onClick={() => onPick(c)} data-testid={`cal-channel-${channelKey(c)}`}>
                <Icon className="mt-0.5 size-5 shrink-0 text-tint-text" aria-hidden />
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="type-headline text-label-1">{channelName(c, t)}</span>
                    {c.kind === "push" ? <Badge tone="tint">{t("calendarExport.how.recommended")}</Badge> : null}
                    {c.kind === "file" ? <Badge tone="warning">{t("calendarExport.how.fileBadge")}</Badge> : null}
                  </span>
                  <span className="type-footnote text-label-2">{lead}</span>
                  {c.kind === "push" ? (
                    <span className="type-footnote text-label-3">
                      {c.connected && c.account ? t("calendarExport.how.pushConnected", { account: c.account }) : t("calendarExport.how.pushNotConnected", { provider: providerName(c.provider, t) })}
                      {!c.connected && domain ? ` ${t("calendarExport.how.pushDomain", { domain })}` : ""}
                    </span>
                  ) : null}
                </span>
                <ChevronRight className="mt-0.5 size-4 shrink-0 self-center text-label-3" aria-hidden />
              </BareButton>
            </li>
          );
        })}
      </ul>
      <Advanced testId="cal-how-advanced">
      <section id={refreshId} aria-label={t("calendarExport.how.refreshTitle")} className="grid gap-1" data-testid="cal-refresh-times">
        <p className="type-footnote font-semibold text-label-1">{t("calendarExport.how.refreshTitle")}</p>
        <ul className="grid gap-0.5 type-footnote text-label-2">
          {channels.some((c) => c.kind === "push") ? <li>{t("calendarExport.how.refreshPush")}</li> : null}
          {channels.some((c) => c.kind === "link") ? (
            <>
              <li>{t("calendarExport.how.refreshApple")}</li>
              <li>{t("calendarExport.how.refreshGoogle")}</li>
              <li>{t("calendarExport.how.refreshOutlook")}</li>
            </>
          ) : null}
          {channels.some((c) => c.kind === "file") ? <li>{t("calendarExport.how.fileLead")}</li> : null}
        </ul>
      </section>
      </Advanced>
    </div>
  );
}

/* ------------------------------------------------------------------------------------- 3 · approve */

export function ApproveStep({
  choice,
  channel,
  fields,
  needsConsent,
  consent,
  onConsent,
  consentRef,
  locale,
}: {
  choice: ScopeChoice;
  channel: Channel;
  fields: FieldKey[];
  needsConsent: boolean;
  consent: boolean;
  onConsent: (v: boolean) => void;
  consentRef: RefObject<HTMLButtonElement | null>;
  locale: string;
}) {
  const { t } = useI18n();
  const consentId = useId();
  const sample = choice.sample ? sampleParts(choice.sample, locale, t("calendarExport.approve.section")) : null;
  const scope = choice.kind === "department_classes" && choice.departmentName ? t("calendarExport.scope.department_named", { department: choice.departmentName }) : scopeName(choice.kind, t);
  return (
    <div className="grid gap-4" data-testid="cal-approve">
      <p className="type-callout text-label-2" data-testid="cal-approve-where">
        {t("calendarExport.approve.where", { scope, channel: channelName(channel, t) })}
      </p>
      <ul className="grid gap-1.5" data-testid="cal-fields">
        {fields.map((f) => (
          <li key={f} className="flex items-center gap-2 type-callout text-label-1">
            <Check className="size-4 shrink-0 text-status-feasible-fg" aria-hidden />
            {t(`calendarExport.approve.field.${f}`)}
          </li>
        ))}
      </ul>
      <p className="type-footnote text-label-2" data-testid="cal-never">
        {choice.kind === "my_duties"
          ? t("calendarExport.approve.neverDuties")
          : fields.includes("co_instructors")
            ? t("calendarExport.approve.neverWithCo")
            : t("calendarExport.approve.never")}
      </p>
      <figure className="grid gap-1 rounded-2xl bg-fill-3 px-4 py-3 edge-control" data-testid="cal-sample">
        <figcaption className="type-caption font-medium text-label-3">{t("calendarExport.approve.sample")}</figcaption>
        {sample ? (
          <>
            <p className="type-headline text-label-1">{sample.what}</p>
            <p className="type-callout text-label-2 tnum">{[sample.where, sample.when].filter(Boolean).join(" — ")}</p>
          </>
        ) : (
          <p className="type-callout text-label-2">{t("calendarExport.approve.sampleNone")}</p>
        )}
      </figure>
      {channel.kind === "file" ? <p className="type-footnote text-status-warning-fg">{t("calendarExport.approve.fileNote")}</p> : null}
      {needsConsent ? (
        <div className="grid gap-1" data-testid="cal-consent">
          <label htmlFor={consentId} className="flex min-h-11 cursor-pointer items-start gap-3 type-callout text-label-1">
            <Checkbox id={consentId} ref={consentRef} checked={consent} onCheckedChange={(v) => onConsent(v === true)} className="mt-0.5" data-testid="cal-consent-tick" />
            <span>
              {choice.kind === "my_bookings"
                ? t("calendarExport.approve.consentBookings")
                : choice.kind === "my_duties"
                  ? t("calendarExport.approve.consentDuties")
                  : t("calendarExport.approve.consent")}
            </span>
          </label>
          <Link href={GRANT_PATH} className="ml-8 w-fit type-footnote font-medium text-tint-text underline-offset-4 hover:underline" data-testid="cal-notice-link">
            {t("calendarExport.approve.notice")}
          </Link>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------------------------- done · link */

function CopyRow({ id, label, value, testId }: { id: string; label: string; value: string; testId: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(
      () => {
        setCopied(true);
        toast.success(t("calendarExport.done.copied"));
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => undefined,
    );
  };
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} readOnly value={value} className="min-w-0 flex-1 font-mono" spellCheck={false} onFocus={(e) => e.currentTarget.select()} data-testid={`${testId}-value`} />
        <Button variant="outline" shape="rect" className="pointer-coarse:min-h-11" onClick={copy} aria-label={`${t("calendarExport.done.copy")}: ${label}`} data-testid={`${testId}-copy`}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          <span className="max-sm:sr-only">{copied ? t("calendarExport.done.copied") : t("calendarExport.done.copy")}</span>
        </Button>
      </div>
    </div>
  );
}

function CopyButton({ value, testId }: { value: string; testId: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(
      () => {
        setCopied(true);
        toast.success(t("calendarExport.done.copied"));
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => undefined,
    );
  };
  return (
    <Button variant="outline" className="min-h-11 w-full sm:w-fit" onClick={copy} data-testid={testId}>
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      {copied ? t("calendarExport.done.copied") : t("calendarExport.done.copy")}
    </Button>
  );
}

/** The subscribe actions of a fresh link (after approval, and after "Bağlantıyı yenile" in the manage list). */
export function LinkResult({ urls, name, testId = "cal-link" }: { urls: { https: string; webcal?: string | null; google?: string | null; outlook?: string | null }; name: string; testId?: string }) {
  const { t } = useI18n();
  const id = useId();
  const l = subscribeLinks(urls, name);
  return (
    <div className="grid gap-3" data-testid={testId}>
      <div className="grid gap-2 sm:grid-cols-3">
        <Button variant="secondary" className="min-h-11" nativeButton={false} render={<a href={l.webcal} data-testid={`${testId}-apple`} />}>
          <CalendarPlus aria-hidden />
          {t("calendarExport.done.apple")}
        </Button>
        <Button variant="secondary" className="min-h-11" nativeButton={false} render={<a href={l.google} target="_blank" rel="noopener noreferrer" data-testid={`${testId}-google`} />}>
          <CalendarPlus aria-hidden />
          {t("calendarExport.done.google")}
        </Button>
        <Button variant="secondary" className="min-h-11" nativeButton={false} render={<a href={l.outlook} target="_blank" rel="noopener noreferrer" data-testid={`${testId}-outlook`} />}>
          <CalendarPlus aria-hidden />
          {t("calendarExport.done.outlook")}
        </Button>
      </div>
      {!/^https?:\/\//i.test(l.https) ? (
        <p className="rounded-xl bg-status-warning px-3 py-2 type-footnote text-status-warning-fg" data-testid={`${testId}-no-url`}>
          {t("calendarExport.done.noPublicUrl")}
        </p>
      ) : null}
      <CopyButton value={l.https} testId={`${testId}-copy`} />
      <p className="rounded-xl bg-status-warning px-3 py-2 type-footnote text-status-warning-fg" data-testid={`${testId}-note`}>
        {t("calendarExport.done.linkNote")}
      </p>
      <p className="type-footnote text-label-2">{t("calendarExport.done.linkOnce")}</p>
      <Advanced testId={`${testId}-advanced`}>
        <CopyRow id={`${id}-https`} label={t("calendarExport.done.https")} value={l.https} testId={`${testId}-https`} />
        <CopyRow id={`${id}-webcal`} label={t("calendarExport.done.webcal")} value={l.webcal} testId={`${testId}-webcal`} />
      </Advanced>
    </div>
  );
}

