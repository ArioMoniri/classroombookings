/**
 * Turkish case suffixes with vowel harmony and consonant assimilation, for generated sentences
 * (planner usability m2: "17:30'den" → "17:30'dan", "4. hafta'den" → "4. haftadan", "A 204'ten").
 *
 * - Numbers, clock times, room and course codes are read aloud the Turkish way to find the last
 *   vowel and the last sound: 204 → "dört" → 'ten; 17:30 → "otuz" → 'dan; 240 → "kırk" → 'tan;
 *   "BME" → "be-me-e" → 'den; "%44" → "yüzde kırk dört" → 'ü.
 * - Proper names, codes and numbers take an apostrophe (A 204'e); common nouns do not (haftadan).
 * - Pure function, no dictionary: it covers the shapes SmartSched generates (codes, numbers, times,
 *   ordinals and ordinary words), not the whole language (e.g. loanword exceptions like "saat" → "saate").
 */

export type TrCase = "abl" | "loc" | "dat" | "acc" | "gen" | "ins";

const BACK = new Set(["a", "ı", "o", "u"]);
const VOWELS = new Set(["a", "e", "ı", "i", "o", "ö", "u", "ü"]);
/** voiceless consonants harden d → t ("fıstıkçı şahap") */
const HARD = new Set(["f", "s", "t", "k", "ç", "ş", "h", "p"]);

const UNITS = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"];
const TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"];

/** The last spoken word of a non-negative integer ("204" → "dört", "1500" → "yüz", "0" → "sıfır"). */
export function lastNumberWord(n: number): string {
  const v = Math.abs(Math.trunc(n));
  if (v === 0) return "sıfır";
  if (v % 10) return UNITS[v % 10] ?? "";
  if (v % 100) return TENS[Math.floor(v / 10) % 10] ?? "";
  if (v % 1000) return "yüz";
  if (v % 1_000_000) return "bin";
  if (v % 1_000_000_000) return "milyon";
  return "milyar";
}

const LETTER_NAMES: Record<string, string> = {
  a: "a", b: "be", c: "ce", ç: "çe", d: "de", e: "e", f: "fe", g: "ge", ğ: "yumuşakge", h: "he", ı: "ı", i: "i",
  j: "je", k: "ke", l: "le", m: "me", n: "ne", o: "o", ö: "ö", p: "pe", q: "kü", r: "re", s: "se", ş: "şe", t: "te",
  u: "u", ü: "ü", v: "ve", w: "ve", x: "iks", y: "ye", z: "ze",
};

const lower = (s: string) => s.toLocaleLowerCase("tr-TR");

/** What the end of `text` sounds like, as a Turkish word. */
export function spokenTail(text: string): string {
  const s = text.trim();
  // clock time 17:30 / 13.00 → the minutes, or the hour when the minutes are zero
  const time = /(\d{1,2})[:.](\d{2})$/.exec(s);
  if (time) return Number(time[2]) === 0 ? lastNumberWord(Number(time[1])) : lastNumberWord(Number(time[2]));
  // a trailing number (with or without thousands separators / decimals): 204, 1.524, 0,5
  const num = /(\d[\d.,]*)\s*%?$/.exec(s);
  if (num) {
    const raw = num[1] ?? "";
    const dec = /[.,](\d{1,2})$/.exec(raw);
    if (dec && !/[.,]\d{3}$/.test(raw)) return lastNumberWord(Number(dec[1]));
    return lastNumberWord(Number(raw.replace(/[.,]/g, "")));
  }
  const word = /([\p{L}]+)\W*$/u.exec(s)?.[1] ?? "";
  if (!word) return "";
  // an acronym / code (all capitals, ≤ 5 letters, or no vowel at all) is read letter by letter
  const isAcronym = (word === word.toLocaleUpperCase("tr-TR") && word.length <= 5 && word.length > 1) || ![...lower(word)].some((c) => VOWELS.has(c));
  if (isAcronym) return LETTER_NAMES[lower(word).at(-1) ?? ""] ?? lower(word);
  return lower(word);
}

function lastVowel(word: string): string {
  for (let i = word.length - 1; i >= 0; i--) if (VOWELS.has(word[i] ?? "")) return word[i] ?? "e";
  return "e";
}

function twoWay(v: string): "a" | "e" {
  return BACK.has(v) ? "a" : "e";
}
function fourWay(v: string): "ı" | "i" | "u" | "ü" {
  if (v === "a" || v === "ı") return "ı";
  if (v === "e" || v === "i") return "i";
  if (v === "o" || v === "u") return "u";
  return "ü";
}

/** Just the suffix for `text` ("dan", "ten", "ye", "nın" …), without the apostrophe. */
export function trSuffix(text: string, kind: TrCase): string {
  const tail = spokenTail(text);
  const last = tail.at(-1) ?? "e";
  const v = lastVowel(tail);
  const endsVowel = VOWELS.has(last);
  const d = HARD.has(last) ? "t" : "d";
  switch (kind) {
    case "abl":
      return `${d}${twoWay(v)}n`;
    case "loc":
      return `${d}${twoWay(v)}`;
    case "dat":
      return `${endsVowel ? "y" : ""}${twoWay(v)}`;
    case "acc":
      return `${endsVowel ? "y" : ""}${fourWay(v)}`;
    case "gen":
      return `${endsVowel ? "n" : ""}${fourWay(v)}n`;
    case "ins":
      return `${endsVowel ? "y" : ""}l${twoWay(v)}`;
  }
}

/** True for things that take an apostrophe: digits, codes with capitals, times, percentages, names. */
function needsApostrophe(text: string): boolean {
  const s = text.trim();
  return /\d|%$/.test(s.slice(-2)) || /\p{Lu}/u.test(s.charAt(0)) || /[A-ZÇĞİÖŞÜ]{2,}$/.test(s);
}

/**
 * `text` with its case suffix: `tr("A 204", "abl")` → "A 204'ten", `tr("4. hafta", "abl")` → "4. haftadan",
 * `tr("17:30", "abl")` → "17:30'dan". Pass `{ proper: false }` for a capitalised common noun at the start
 * of a sentence ("Hafta" → "Haftadan").
 */
export function tr(text: string, kind: TrCase, opts: { proper?: boolean } = {}): string {
  const proper = opts.proper ?? needsApostrophe(text);
  const suffix = trSuffix(text, kind);
  if (proper) return `${text}'${suffix}`;
  // common nouns ending in a voiceless stop soften before a vowel suffix only in a few roots; we keep it simple
  return `${text}${suffix}`;
}

/** Turkish puts the percent sign first: 44 → "%44"; 0.1 → "%0,1". */
export function trPercent(value: number, locale: string, fractionDigits = 0): string {
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: fractionDigits, minimumFractionDigits: 0 }).format(value);
}
