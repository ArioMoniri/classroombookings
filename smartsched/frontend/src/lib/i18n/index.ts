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

/**
 * Admin translation overrides of one language, flattened to full message keys (`crbs.bookings.title` → text).
 * They come from `GET /org/i18n` (CRBS `lang` table, edited in /admin/settings) and win over the shipped
 * messages at runtime, so an override needs no rebuild.
 */
export type MessageOverrides = Readonly<Record<string, string>>;

/**
 * `GET /org/i18n` `messages` (set → key → text) → overrides for this frontend. The set is the first segment
 * of the message key and the key is the rest (`crbs` + `bookings.title`), as the admin editor explains.
 * Only keys this frontend ships are kept (the bundle also carries the backend's own sets, e.g. the e-mail
 * texts), and an empty text means "no override" so a cleared row falls back to the shipped string.
 */
export function overridesFromBundle(messages: Readonly<Record<string, Readonly<Record<string, string>>>> | null | undefined): MessageOverrides {
  const out: Record<string, string> = {};
  if (!messages) return out;
  for (const [set, keys] of Object.entries(messages)) {
    const prefix = set.trim();
    if (!prefix || !keys) continue;
    for (const [key, text] of Object.entries(keys)) {
      const k = key.trim();
      if (!k || typeof text !== "string" || text.trim() === "") continue;
      const full = `${prefix}.${k}`;
      if (lookup(dictionaries.en, full) === undefined && lookup(dictionaries.tr, full) === undefined) continue;
      out[full] = text;
    }
  }
  return out;
}

export function translate(locale: Locale, key: MessageKey, vars?: Vars, overrides?: MessageOverrides): string {
  const own = overrides && Object.hasOwn(overrides, key) ? overrides[key] : undefined;
  const raw = own ?? lookup(dictionaries[locale], key) ?? lookup(dictionaries.en, key) ?? key;
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
