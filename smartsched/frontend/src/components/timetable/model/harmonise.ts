/**
 * Turkish case suffixes after a placeholder ("{time}'de", "Run #{run}'de") follow the value's vowel harmony:
 * 09:00 → "dokuz" → 'da, 14:20 → "yirmi" → 'de, #6 → "altı" → 'da (ROADMAP: Turkish suffix-harmony helper for
 * generated sentences). The i18n `t()` interpolates blindly, so this reads the raw template (t with each
 * placeholder as its own name), harmonises every `{name}'suffix`, then substitutes.
 */
import { harmoniseAfter } from "@/components/common/tr-suffix";

type T = (key: string, vars?: Record<string, string | number>) => string;

export function harmonised<K extends string>(t: (key: K, vars?: Record<string, string | number>) => string, locale: string, key: K, vars: Record<string, string | number>): string {
  if (!locale.startsWith("tr")) return t(key, vars);
  const names = Object.fromEntries(Object.keys(vars).map((k) => [k, `\u0000${k}\u0000`]));
  const raw = (t as unknown as T)(key, names);
  return raw.replace(/\u0000(\w+)\u0000(['’][a-zçğıöşü]+)?/g, (_, name: string, suffix: string | undefined) => {
    const value = String(vars[name] ?? "");
    return suffix ? value + harmoniseAfter(value, suffix) : value;
  });
}
