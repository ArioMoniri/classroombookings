"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { DEFAULT_LOCALE, LOCALE_COOKIE, formatNumber, translate, type Locale, type MessageKey, type Vars } from "./index";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, vars?: Vars) => string;
  n: (value: number, opts?: Intl.NumberFormatOptions) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      document.documentElement.lang = next;
    } catch {
      /* non-browser */
    }
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, vars) => translate(locale, key, vars),
      n: (v, opts) => formatNumber(locale, v, opts),
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => undefined,
      t: (key, vars) => translate(DEFAULT_LOCALE, key, vars),
      n: (v, opts) => formatNumber(DEFAULT_LOCALE, v, opts),
    };
  }
  return ctx;
}

export function useT() {
  return useI18n().t;
}
