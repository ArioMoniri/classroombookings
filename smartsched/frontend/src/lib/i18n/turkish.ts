/**
 * Shared grammar for generated sentences (round-1 R1-S-23, T-R1-38): the Turkish case suffix of a number or a
 * code, percentages (`%95'i`, `%100`, `%0,6`), decimal commas (`12,0`) and week ordinals (`3. hafta`, not
 * `3. haftalar`). Lanes B (T-R1-20), F (T-R1-42) and H (T-R1-47/48) use these instead of string concatenation.
 *
 * Turkish vowel harmony follows the *spoken* last word, so a number takes the suffix of how it is read:
 * 0 = "sıfır" → 'ı, 95 = "doksan beş" → 'i, 100 = "yüz" → 'ü, 0,6 = "sıfır virgül altı" → 'yı. A code ending in
 * letters follows its last vowel (`LAB` → 'ı). Mirrors the backend's `app/services/tr_grammar.py`.
 */
import { formatNumber, type Locale } from "./index";

const UNITS: Record<string, string> = { "1": "bir", "2": "iki", "3": "üç", "4": "dört", "5": "beş", "6": "altı", "7": "yedi", "8": "sekiz", "9": "dokuz" };
const TENS: Record<string, string> = { "1": "on", "2": "yirmi", "3": "otuz", "4": "kırk", "5": "elli", "6": "altmış", "7": "yetmiş", "8": "seksen", "9": "doksan" };
const VOWELS = "aıoueiöüAIOUEİÖÜ";
const FRONT = "eiöüEİÖÜ";
const ROUND = "oöuüOÖUÜ";
/** voiceless consonants (fıstıkçı şahap): -ta/-te, -tan/-ten */
const VOICELESS = "fstkçşhpFSTKÇŞHP";

/** How the last group of digits is read ("2026" → "altı", "100" → "yüz", "1000" → "bin"). */
function spokenNumber(digits: string): string {
  const n = digits.replace(/^0+/, "");
  if (!n) return "sıfır";
  if (n.at(-1) !== "0") return UNITS[n.at(-1)!]!;
  if (n.length >= 2 && n.at(-2) !== "0") return TENS[n.at(-2)!]!;
  if (n.length >= 3 && n.at(-3) !== "0") return "yüz";
  if (n.length >= 4) return n.length <= 6 ? "bin" : n.length <= 9 ? "milyon" : "milyar";
  return "on";
}

/** The word whose vowels decide the suffix of `text` (a number, a code such as `B 201`, a name). */
export function spokenTail(text: string): string {
  const t = text.trim().replace(/[%'’.]+$/, "");
  const digits = /(\d+)$/.exec(t);
  if (digits) return spokenNumber(digits[1]!);
  const words = t.split(/\s+/);
  return words.at(-1) ?? t;
}

/** `poss`: the 3rd-person possessive ("%72'si", "%95'i", "B 201'i"), the subject of "...'si planlandı" sentences (lane F, T-R1-38). */
export type TrCase = "acc" | "dat" | "loc" | "abl" | "gen" | "poss";

/** The bare suffix (no apostrophe) of `text` in the case: `suffix("95", "acc") === "i"`, `suffix("0", "acc") === "ı"`. */
export function suffix(text: string, kase: TrCase): string {
  const word = spokenTail(text);
  const vowels = [...word].filter((c) => VOWELS.includes(c));
  const last = vowels.at(-1) ?? "e";
  const front = FRONT.includes(last);
  const round = ROUND.includes(last);
  const endsVowel = VOWELS.includes(word.at(-1) ?? "");
  const voiceless = VOICELESS.includes(word.at(-1) ?? "");
  const four = front ? (round ? "ü" : "i") : round ? "u" : "ı";
  const two = front ? "e" : "a";
  switch (kase) {
    case "acc":
      return (endsVowel ? "y" : "") + four;
    case "dat":
      return (endsVowel ? "y" : "") + two;
    case "gen":
      return (endsVowel ? "n" : "") + four + "n";
    case "poss":
      return (endsVowel ? "s" : "") + four;
    case "loc":
      return (voiceless ? "t" : "d") + two;
    case "abl":
      return (voiceless ? "t" : "d") + two + "n";
  }
}

/** `text` with the case suffix after an apostrophe (proper names, codes, numbers): `withSuffix("B 201", "dat") === "B 201'e"`. */
export function withSuffix(text: string, kase: TrCase): string {
  return `${text.trimEnd()}'${suffix(text, kase)}`;
}

export interface PctOptions {
  locale?: Locale;
  /** fraction digits; default: none for whole numbers, else up to 1 */
  digits?: number;
  /** a Turkish case suffix after the number (`%95'i`); ignored in English */
  suffix?: TrCase;
}

/**
 * A percentage of 0..100 (not a ratio): Turkish `%95`, `%0,6`, `%100'ü`; English `95%`, `0.6%`. Never `100 %`.
 */
export function pct(value: number, opts: PctOptions = {}): string {
  const locale = opts.locale ?? "tr";
  const v = Number.isFinite(value) ? value : 0;
  const digits = opts.digits ?? (Number.isInteger(v) ? 0 : 1);
  const num = formatNumber(locale, v, { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false });
  if (locale !== "tr") return `${num}%`;
  const out = `%${num}`;
  return opts.suffix ? `${out}'${suffix(num, opts.suffix)}` : out;
}

/** A decimal with a fixed number of fraction digits in the locale (`12,0` in Turkish, `12.0` in English). */
export function fixed(value: number, digits: number, locale: Locale = "tr"): string {
  return formatNumber(locale, Number.isFinite(value) ? value : 0, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** One week: `3. hafta` / `week 3`. */
export function ordinalWeek(n: number, locale: Locale = "tr"): string {
  return locale === "tr" ? `${n}. hafta` : `week ${n}`;
}

/** Sorted runs of consecutive numbers: [1,2,3,5] → [[1,3],[5,5]]. */
function runs(values: readonly number[]): [number, number][] {
  const sorted = [...new Set(values)].sort((a, b) => a - b);
  const out: [number, number][] = [];
  for (const v of sorted) {
    const last = out.at(-1);
    if (last && v === last[1] + 1) last[1] = v;
    else out.push([v, v]);
  }
  return out;
}

/**
 * Several weeks in one phrase, singular for one week: `3. hafta`, `3. ve 5. haftalar`, `1.–4. haftalar`,
 * `1.–4. ve 6. haftalar`; English `week 3`, `weeks 3 and 5`, `weeks 1–4`. Empty → "".
 */
export function weekList(weeks: readonly number[], locale: Locale = "tr"): string {
  const parts = runs(weeks);
  if (!parts.length) return "";
  const count = parts.reduce((s, [a, b]) => s + b - a + 1, 0);
  if (count === 1) return ordinalWeek(parts[0]![0], locale);
  const tr = locale === "tr";
  const label = parts.map(([a, b]) => (a === b ? (tr ? `${a}.` : `${a}`) : b === a + 1 ? (tr ? `${a}., ${b}.` : `${a}, ${b}`) : tr ? `${a}.–${b}.` : `${a}–${b}`));
  const flat = label.join(", ").split(", ");
  const joined = flat.length === 1 ? flat[0]! : `${flat.slice(0, -1).join(", ")} ${tr ? "ve" : "and"} ${flat.at(-1)}`;
  return tr ? `${joined} haftalar` : `weeks ${joined}`;
}
