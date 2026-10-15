"use client";
import { useEffect, useMemo } from "react";
import { crbs, useBookingContext, useCrbsMe, useOrgI18n, useProfile } from "@/lib/api/crbs";
import { displayLocale, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { dateFormatter, type DateFormatter } from "./date-format";

/**
 * Dates in the organisation's patterns and the user's language (CRBS `date_output_*`): `GET /org/i18n` for
 * the active language gives the patterns and what an empty pattern means there; `GET /bookings/context`
 * is the fallback (signed-in only, same patterns) while it loads or if the language is not enabled.
 */
export function useBookingFormat(): DateFormatter {
  const { locale } = useI18n();
  const i18n = useOrgI18n(locale);
  const ctx = useBookingContext();
  const bundle = i18n.data?.language === locale ? i18n.data : undefined;
  const patterns = bundle?.date_patterns ?? ctx.data?.date_patterns;
  const defaults = bundle?.date_defaults;
  return useMemo(() => dateFormatter(patterns, locale, defaults), [patterns, locale, defaults]);
}

const SYNC_KEY = "crbs.profile-language";

/**
 * At sign-in: the profile language (or the institution default) becomes the session's language before the
 * first page renders, and the per-session sync below then has nothing left to change. Never throws.
 */
export async function applySessionLanguage(userId: number, locale: Locale, setLocale: (l: Locale) => void): Promise<void> {
  try {
    const [profile, org] = await Promise.all([crbs.auth.profile(), crbs.org.public().catch(() => null)]);
    const wanted = displayLocale(profile.language || org?.default_language || null);
    if (wanted && wanted !== locale) setLocale(wanted);
    sessionStorage.setItem(SYNC_KEY, String(userId));
  } catch {
    /* keep the current language */
  }
}

/**
 * CRBS uses the language in the user's profile on every page. Apply it once per sign-in session (a later
 * manual switch in the shell is respected until the next sign-in); no profile language = organisation default.
 */
export function useProfileLanguage(): void {
  const { locale, setLocale } = useI18n();
  const me = useCrbsMe();
  const profile = useProfile();
  const org = useOrgI18n(undefined);
  const userId = me.data?.id;
  // a stored legacy code (`de`, from a CRBS import) is kept in the profile and shown English (P18-LANG)
  const wanted = profile.data ? displayLocale(profile.data.language || org.data?.default_language || null) : null;
  useEffect(() => {
    if (!userId || !wanted) return;
    let synced: string | null = null;
    try {
      synced = sessionStorage.getItem(SYNC_KEY);
    } catch {
      /* storage blocked: apply every time */
    }
    if (synced === String(userId)) return;
    try {
      sessionStorage.setItem(SYNC_KEY, String(userId));
    } catch {
      /* ignore */
    }
    if (wanted !== locale) setLocale(wanted);
  }, [userId, wanted, locale, setLocale]);
}
