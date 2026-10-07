import en from "../../../messages/en.json";
import tr from "../../../messages/tr.json";

export const LOCALES = ["tr", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "tr";
export const LOCALE_COOKIE = "NEXT_LOCALE";

type Messages = typeof en;

type Leaves<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Leaves<T[K], `${Prefix}${K}.`>;
}[keyof T & string];

export type MessageKey = Leaves<Messages>;

const dictionaries: Record<Locale, Messages> = { en, tr: tr as Messages };

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "tr" || value === "en";
}

function lookup(dict: Messages, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

export type Vars = Record<string, string | number>;

export function translate(locale: Locale, key: MessageKey, vars?: Vars): string {
  const raw = lookup(dictionaries[locale], key) ?? lookup(dictionaries.en, key) ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, name: string) => (name in vars ? String(vars[name]) : `{${name}}`));
}

export function formatNumber(locale: Locale, n: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale, opts).format(n);
}

/** Turkish-aware upper-casing for codes (i → İ). */
export function upperCode(text: string, locale: Locale): string {
  return text.toLocaleUpperCase(locale === "tr" ? "tr-TR" : "en-US");
}
