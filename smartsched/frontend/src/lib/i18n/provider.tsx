"use client";

import { QueryClientContext, keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { OrgI18n } from "@/lib/api/crbs";
import { DEFAULT_ENABLED, DEFAULT_LOCALE, LOCALES, LOCALE_COOKIE, formatNumber, overridesFromBundle, translate, type Locale, type MessageKey, type MessageOverrides, type Vars } from "./index";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** the languages the organisation enabled (CRBS setup/Language; `GET /org/i18n` `languages`), in
   *  shipped order and always with the active one; the backend default (tr, en) until it answers */
  languages: readonly Locale[];
  t: (key: MessageKey, vars?: Vars) => string;
  n: (value: number, opts?: Intl.NumberFormatOptions) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

const NO_OVERRIDES: MessageOverrides = Object.freeze({});
/** every `useOrgI18n(lang)` key (`crbsKeys.i18n`) */
const I18N_PREFIX = ["crbs", "i18n"] as const;
/** `crbsKeys.i18n(lang)`: the provider shares the cache entry of `useOrgI18n` (one request per language). */
export const orgI18nKey = (lang: Locale) => [...I18N_PREFIX, lang] as const;

/**
 * `useOrgI18n(locale)` with the same key, fetcher and cache options. The API module is imported when the
 * query runs, not at module load: lib/i18n stays below the API layer, and the provider still renders where
 * that module is replaced (component tests mock `@/lib/api/crbs` wholesale); a failed load is a query error,
 * which leaves the shipped messages in place.
 */
function useOrgBundle(locale: Locale) {
  return useQuery<OrgI18n>({
    queryKey: orgI18nKey(locale),
    queryFn: async () => (await import("@/lib/api/crbs")).crbs.org.i18n(locale),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

interface LoadedOverrides {
  locale: Locale;
  overrides: MessageOverrides;
}

/** org `languages` → shipped locales in shipped order; null when unknown */
function enabledLocales(list: readonly string[] | null | undefined): readonly Locale[] | null {
  if (!list?.length) return null;
  const set = new Set(list.map((l) => l.toLowerCase()));
  const out = LOCALES.filter((l) => set.has(l));
  return out.length ? out : null;
}

/**
 * Loads the admin overrides of the active language (`GET /org/i18n?language=…`, public, cached 5 min) and
 * hands them to the provider. A bundle for another language (the previous one is kept while the new one
 * loads, or the backend answered with its default language) is never applied.
 */
function OrgOverridesLoader({ locale, onLoad, onLanguages }: { locale: Locale; onLoad: (loaded: LoadedOverrides | null) => void; onLanguages: (languages: readonly Locale[] | null) => void }) {
  const q = useOrgBundle(locale);
  const qc = useQueryClient();
  // the admin editor (/admin/settings) refetches its translation list after every save or delete; refresh the
  // bundle then too, so an edited text shows at once instead of after the 5 min cache
  useEffect(
    () =>
      qc.getQueryCache().subscribe((event) => {
        const key = event.query.queryKey;
        if (event.type === "updated" && event.action.type === "success" && key[0] === "crbs" && key[1] === "translations") {
          void qc.invalidateQueries({ queryKey: I18N_PREFIX });
        }
      }),
    [qc],
  );
  // the enabled languages are org-wide: any bundle (also the previous language's, kept while loading) has them
  const enabled = useMemo(() => enabledLocales(q.data?.languages), [q.data?.languages]);
  useEffect(() => {
    onLanguages(enabled);
  }, [enabled, onLanguages]);
  const bundle = q.data?.language === locale ? q.data : undefined;
  const overrides = useMemo(() => (bundle ? overridesFromBundle(bundle.messages) : null), [bundle]);
  useEffect(() => {
    onLoad(overrides ? { locale, overrides } : null);
  }, [locale, overrides, onLoad]);
  return null;
}

export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const [loaded, setLoaded] = useState<LoadedOverrides | null>(null);
  const [enabled, setEnabled] = useState<readonly Locale[] | null>(null);
  // the overrides need the API; without a QueryClient (isolated component tests) the shipped messages apply
  const hasQueryClient = useContext(QueryClientContext) !== undefined;

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      document.documentElement.lang = next;
    } catch {
      /* non-browser */
    }
  }, []);

  const overrides = loaded?.locale === locale ? loaded.overrides : NO_OVERRIDES;
  const languages = useMemo<readonly Locale[]>(() => {
    const base = enabled ?? DEFAULT_ENABLED;
    return base.includes(locale) ? base : LOCALES.filter((l) => l === locale || base.includes(l));
  }, [enabled, locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      languages,
      t: (key, vars) => translate(locale, key, vars, overrides),
      n: (v, opts) => formatNumber(locale, v, opts),
    }),
    [locale, setLocale, languages, overrides],
  );

  return (
    <I18nContext.Provider value={value}>
      {hasQueryClient ? <OrgOverridesLoader locale={locale} onLoad={setLoaded} onLanguages={setEnabled} /> : null}
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => undefined,
      languages: DEFAULT_ENABLED,
      t: (key, vars) => translate(DEFAULT_LOCALE, key, vars),
      n: (v, opts) => formatNumber(DEFAULT_LOCALE, v, opts),
    };
  }
  return ctx;
}

export function useT() {
  return useI18n().t;
}
