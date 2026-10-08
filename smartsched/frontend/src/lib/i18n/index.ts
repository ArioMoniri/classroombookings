import en from "../../../messages/en.json";
import tr from "../../../messages/tr.json";
import cs from "../../../messages/cs.json";
import cy from "../../../messages/cy.json";
import da from "../../../messages/da.json";
import de from "../../../messages/de.json";
import es from "../../../messages/es.json";
import fi from "../../../messages/fi.json";
import fr from "../../../messages/fr.json";
import it from "../../../messages/it.json";
import nl from "../../../messages/nl.json";
import pt from "../../../messages/pt.json";
import ptBr from "../../../messages/pt-br.json";
import sv from "../../../messages/sv.json";
import localeData from "./locale-data.json";

/**
 * Turkish and English (SmartSched's own) plus the 12 other classroombookings languages (ROADMAP P18-LANG).
 * Codes are lower case, the same in the cookie, the profile (`PUT /auth/profile`), the org settings and
 * `GET /org/i18n` (the API lower-cases the query). The 12 message files are generated from the CRBS language
 * files by `smartsched/backend/tools/crbs_lang_import.py` and carry only the strings CRBS translates; every
 * other key falls back to English per key (`translate`), and an organisation can fill in the rest
 * (Admin → Settings → Translations, overlaid at runtime by the provider).
 */
export const LOCALES = ["tr", "en", "cs", "cy", "da", "de", "es", "fi", "fr", "it", "nl", "pt", "pt-br", "sv"] as const;
export type Locale = (typeof LOCALES)[number];
/** the CRBS languages besides English: partial catalogues, English per missing key */
export type CrbsLocale = Exclude<Locale, "tr" | "en">;
export const DEFAULT_LOCALE: Locale = "tr";
export const LOCALE_COOKIE = "NEXT_LOCALE";
/** the backend's default `languages` org setting (what the picker offers before `GET /org/i18n` answers) */
export const DEFAULT_ENABLED: readonly Locale[] = ["tr", "en"];

type Messages = typeof en;
type DeepPartial<T> = { [K in keyof T]?: T[K] extends string ? string : DeepPartial<T[K]> };

type Leaves<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Leaves<T[K], `${Prefix}${K}.`>;
}[keyof T & string];

export type MessageKey = Leaves<Messages>;

const dictionaries: Record<Locale, DeepPartial<Messages>> = { en, tr, cs, cy, da, de, es, fi, fr, it, nl, pt, "pt-br": ptBr, sv };

export interface LocaleInfo {
  /** endonym: the language's name in itself (ICU display names) */
  name: string;
  /** BCP 47 tag for Intl (numbers, plural rules) */
  tag: string;
  /** CRBS `application/language/<folder>` the strings came from */
  crbs: string | null;
}

type CrbsData = (typeof localeData)["languages"][CrbsLocale];
const CRBS_DATA = localeData.languages as Record<CrbsLocale, CrbsData>;

export const LOCALE_INFO: Record<Locale, LocaleInfo> = {
  tr: { name: "Türkçe", tag: "tr", crbs: null },
  en: { name: "English", tag: "en", crbs: "english" },
  ...(Object.fromEntries(Object.entries(CRBS_DATA).map(([code, d]) => [code, { name: d.name, tag: d.tag, crbs: d.crbs }])) as Record<CrbsLocale, LocaleInfo>),
};

export function isLocale(value: string | undefined | null): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** `DE`, `pt_BR`, `pt-BR` → a shipped code; anything else → null */
export function normalizeLocale(value: string | undefined | null): Locale | null {
  if (!value) return null;
  const v = value.trim().toLowerCase().replace(/_/g, "-");
  return isLocale(v) ? v : null;
}

/** BCP 47 tag of a locale for `Intl` (`pt` → `pt-PT`, `pt-br` → `pt-BR`). */
export function intlLocale(locale: Locale): string {
  return LOCALE_INFO[locale]?.tag ?? locale;
}

function lookup(dict: DeepPartial<Messages> | Messages, key: string): string | undefined {
  let node: unknown = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

function countLeaves(node: unknown): number {
  if (typeof node === "string") return 1;
  if (typeof node !== "object" || node === null) return 0;
  return Object.values(node).reduce<number>((n, v) => n + countLeaves(v), 0);
}

const TOTAL = countLeaves(en);

export interface Coverage {
  /** keys the locale ships (for the CRBS languages: translated by CRBS) */
  translated: number;
  total: number;
  /** 0 … 1 */
  ratio: number;
  /** some keys fall back to English */
  partial: boolean;
}

const coverageCache = new Map<Locale, Coverage>();

/** Share of the message keys a locale translates; the rest falls back to English per key. */
export function coverage(locale: Locale): Coverage {
  const hit = coverageCache.get(locale);
  if (hit) return hit;
  const translated = locale === "en" ? TOTAL : Math.min(TOTAL, countLeaves(dictionaries[locale]));
  const out = { translated, total: TOTAL, ratio: TOTAL ? translated / TOTAL : 1, partial: translated < TOTAL };
  coverageCache.set(locale, out);
  return out;
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

const pluralRules = new Map<Locale, Intl.PluralRules>();

/** CLDR plural category of `n` in the locale (`one`, `few`, `many`, `other`, … Welsh has six). */
export function pluralCategory(locale: Locale, n: number): Intl.LDMLPluralRule {
  let rules = pluralRules.get(locale);
  if (!rules) {
    rules = new Intl.PluralRules(intlLocale(locale));
    pluralRules.set(locale, rules);
  }
  return rules.select(n);
}

/** index after the `}` that closes the `{` at `open` (or -1) */
function closing(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return i + 1;
  }
  return -1;
}

/**
 * ICU-style plurals in a message (`{n, plural, =0 {none} one {# room} other {# rooms}}`), chosen with the
 * locale's CLDR rules; `#` is the number in the locale's format. Shipped messages do not use them yet; they let
 * translators and organisation overrides write correct plurals in any of the 14 languages.
 */
function formatPlurals(raw: string, vars: Vars, locale: Locale): string {
  const head = /\{(\w+),\s*plural,/g;
  let out = "";
  let last = 0;
  for (let m = head.exec(raw); m; m = head.exec(raw)) {
    const end = closing(raw, m.index);
    if (end < 0) break;
    const name = m[1]!;
    const value = Number(vars[name]);
    if (!(name in vars) || Number.isNaN(value)) continue;
    const body = raw.slice(m.index + m[0].length, end - 1);
    const forms = new Map<string, string>();
    const sel = /\s*(=\d+|zero|one|two|few|many|other)\s*\{/g;
    for (let s = sel.exec(body); s; s = sel.exec(body)) {
      const open = s.index + s[0].length - 1;
      const stop = closing(body, open);
      if (stop < 0) break;
      forms.set(s[1]!, body.slice(open + 1, stop - 1));
      sel.lastIndex = stop;
    }
    const form = forms.get(`=${value}`) ?? forms.get(pluralCategory(locale, value)) ?? forms.get("other") ?? "";
    out += raw.slice(last, m.index) + form.replace(/#/g, formatNumber(locale, value));
    last = end;
    head.lastIndex = end;
  }
  return out + raw.slice(last);
}

export function translate(locale: Locale, key: MessageKey, vars?: Vars, overrides?: MessageOverrides): string {
  const own = overrides && Object.hasOwn(overrides, key) ? overrides[key] : undefined;
  // per key: the override, the locale's own text, English, the key itself
  const raw = own ?? lookup(dictionaries[locale] ?? dictionaries.en, key) ?? lookup(dictionaries.en, key) ?? key;
  if (!vars) return raw;
  const text = raw.includes(", plural,") ? formatPlurals(raw, vars, locale) : raw;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => (name in vars ? String(vars[name]) : `{${name}}`));
}

export function formatNumber(locale: Locale, n: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(intlLocale(locale), opts).format(n);
}

/** Turkish-aware upper-casing for codes (i → İ). */
export function upperCode(text: string, locale: Locale): string {
  return text.toLocaleUpperCase(locale === "tr" ? "tr-TR" : "en-US");
}

/**
 * The side of a Turkish/English text pair (`{ tr, en }` from the solver, studio and diagnosis APIs) to show:
 * Turkish for Turkish, English for every other language (those texts have no CRBS source).
 */
export function pairLang(locale: Locale): "tr" | "en" {
  return locale === "tr" ? "tr" : "en";
}
