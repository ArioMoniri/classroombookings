"use client";
/**
 * The calendar-sync consent step (consent gates 2026-10-16; backend `app/services/calendar_feeds.py`
 * `require_sync_consent`). With the institution's calendar-sync sign-off on, making a private calendar link,
 * resetting the links or connecting Google / Microsoft needs the person's active `calendar_sync` consent:
 * `GET /calendar/sync` says so in `consent {purpose, required, granted}`, and the action answers 409
 * `consent_required` (`message_tr` / `message_en`, `grant_path` `/profile#privacy`) without it.
 *
 * - `needsCalendarConsent(status)`: ask first (required and not granted).
 * - `<CalendarConsentStep>`: an inline step that says what the consent covers and how to withdraw it, with one
 *   button that gives it (`POST /me/consents/calendar_sync`; every calendar query is refreshed) and then runs the
 *   action the person started. Focus moves to the step when it opens; Escape or "Not now" closes it.
 * - `consentRefusal(err, locale)` + `<ConsentRefusal>`: the backend's own sentence with a link to `grant_path`, for a
 *   409 that arrives anyway (another tab withdrew it, the sign-off was switched on meanwhile).
 */
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { CalendarCheck2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { SPRING_PRESS, useMotionSafe } from "@/components/ui/motion-presets";
import type { SyncStatus } from "@/lib/api/crbs";
import { kvkkKeys, useConsent } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { coarseHitArea } from "@/components/ui/hit-area";

/** `GET /calendar/sync` in the TanStack cache (bookings/calendar-sync.tsx, settings/calendar-connections.tsx) */
const SYNC_STATUS_KEY = ["crbs", "calendar-sync"] as const;

/** where a person gives a consent when the backend names no other place */
export const GRANT_PATH = "/profile#privacy";

/** The screen must ask for the consent before making a link or a connection. */
export function needsCalendarConsent(status: Pick<SyncStatus, "consent"> | null | undefined): boolean {
  return !!status?.consent?.required && !status.consent.granted;
}

/** A 409 `consent_required` → the backend's sentence in the reader's language and where to give the consent; else null. */
export function consentRefusal(err: unknown, locale: string): { text: string; href: string; purpose: string | null } | null {
  const e = wave1Error(err);
  if (e.code !== "consent_required") return null;
  const d = e.data;
  const en = typeof d.message_en === "string" ? d.message_en : e.message;
  const text = locale === "tr" ? (e.messageTr ?? en) : en;
  const path = typeof d.grant_path === "string" && d.grant_path.startsWith("/") && !d.grant_path.startsWith("//") ? d.grant_path : GRANT_PATH;
  return { text, href: path, purpose: typeof d.purpose === "string" ? d.purpose : null };
}

/** The refusal with its link. Showing it refreshes the consent state the screens hold (calendar sync status and
 * Profil › Gizlilik), so the link opens a Gizlilik that shows the consent as not given. */
export function ConsentRefusal({ refusal, className, testId = "calendar-consent-refused" }: { refusal: { text: string; href: string }; className?: string; testId?: string }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  useEffect(() => {
    void qc.invalidateQueries({ queryKey: kvkkKeys.me });
    void qc.invalidateQueries({ queryKey: SYNC_STATUS_KEY });
  }, [qc, refusal]);
  return (
    <Alert tone="error" className={className} data-testid={testId}>
      {refusal.text}{" "}
      <Link href={refusal.href} className={cn("relative font-medium underline underline-offset-4", coarseHitArea)} data-testid="calendar-consent-link">
        {t("calendarPush.me.consentLink")}
      </Link>
    </Alert>
  );
}

/**
 * The inline consent step: "Give consent and continue" gives it and calls `onGranted`, which runs the action the
 * person started (make the link, reset, connect). The parent closes the step (`onCancel`, or in `onGranted`).
 */
export function CalendarConsentStep({ onGranted, onCancel, className, testId = "calendar-consent-step" }: { onGranted: () => void; onCancel: () => void; className?: string; testId?: string }) {
  const { t, locale } = useI18n();
  const m = useConsent();
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const transition = useMotionSafe(SPRING_PRESS);
  useEffect(() => {
    ref.current?.focus({ preventScroll: false });
  }, []);
  const grant = () => {
    setError(null);
    m.mutate(
      { purpose: "calendar_sync", grant: true },
      {
        onSuccess: () => {
          toast.success(t("privacy.consent.granted"));
          onGranted();
        },
        onError: (e) => setError(errorText(wave1Error(e), locale)),
      },
    );
  };
  return (
    <motion.div
      ref={ref}
      tabIndex={-1}
      role="group"
      aria-labelledby={titleId}
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition}
      onKeyDown={(e) => {
        if (e.key === "Escape" && !m.isPending) {
          e.stopPropagation();
          onCancel();
        }
      }}
      className={cn("flex flex-col gap-2 rounded-xl bg-tint-soft px-3 py-3 edge-tint focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)", className)}
      data-testid={testId}
    >
      <p id={titleId} className="flex items-center gap-2 type-callout font-semibold text-label-1">
        <CalendarCheck2 className="size-4 shrink-0 text-tint-text" aria-hidden />
        {t("privacy.calendarConsent.title")}
      </p>
      <p className="type-footnote text-label-1">{t("privacy.calendarConsent.body")}</p>
      <p className="type-footnote text-label-2">
        {t("privacy.calendarConsent.withdraw")}{" "}
        <Link href={GRANT_PATH} className={cn("relative font-medium text-tint-text underline-offset-4 hover:underline", coarseHitArea)}>
          {t("calendarPush.me.consentLink")}
        </Link>
      </p>
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="calendar-consent-error">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" className="pointer-coarse:min-h-11" onClick={grant} {...busyProps(m.isPending)} data-testid="calendar-consent-grant">
          <BusyLabel busy={m.isPending} label={t("busy.saving")}>
            {t("privacy.calendarConsent.grant")}
          </BusyLabel>
        </Button>
        <Button size="sm" variant="ghost" className="pointer-coarse:min-h-11" onClick={onCancel} disabled={m.isPending} data-testid="calendar-consent-cancel">
          {t("privacy.calendarConsent.cancel")}
        </Button>
      </div>
    </motion.div>
  );
}
