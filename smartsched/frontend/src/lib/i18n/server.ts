import "server-only";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { DEFAULT_LOCALE, LOCALE_COOKIE, displayLocale, translate, type Locale, type MessageKey } from "./index";

/**
 * The request's interface language on the server: the language cookie the picker (and the profile language,
 * applied on the first bookings page) writes. A legacy code still in the cookie (`de`, from before the
 * 2026-10-15 TR + EN decision) is shown English; no cookie is the default (Turkish).
 */
export async function requestLocale(): Promise<Locale> {
  const jar = await cookies();
  return displayLocale(jar.get(LOCALE_COOKIE)?.value) ?? DEFAULT_LOCALE;
}

/**
 * `generateMetadata` for a page: the document title in the request's language (persona U-09: the titles were
 * English in the Turkish UI). The root layout's template adds " · SmartSched".
 */
export function localizedTitle(key: MessageKey) {
  return async function generateMetadata(): Promise<Metadata> {
    return { title: translate(await requestLocale(), key) };
  };
}
