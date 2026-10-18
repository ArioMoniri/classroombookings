/**
 * PER-F04: a Bahar file previewed onto Güz (the target defaults to the current term) would change 1,900 Güz rows on
 * one click. The file's season word (bahar / güz / yaz, in its name) against the target term's name: a mismatch is
 * said above the counts and "Uygula" waits until the person confirms the target.
 */
type Season = "spring" | "fall" | "summer";

const fold = (s: string) =>
  s
    .toLocaleLowerCase("tr")
    .replace(/ı/g, "i")
    .replace(/ü/g, "u")
    .replace(/ğ/g, "g")
    .replace(/ş/g, "s")
    .replace(/ö/g, "o")
    .replace(/ç/g, "c");

export function seasonOf(text: string): Season | null {
  const s = fold(text);
  const has = (w: string) => new RegExp(`(^|[^a-z])${w}([^a-z]|$)`).test(s);
  const found = new Set<Season>();
  if (has("bahar") || has("spring")) found.add("spring");
  if (has("guz") || has("fall") || has("autumn")) found.add("fall");
  if (has("yaz") || has("summer")) found.add("summer");
  return found.size === 1 ? [...found][0]! : null;
}

export interface TermMismatch {
  /** the target term's name */
  target: string;
  /** a term whose name matches the file's season (the likely right target), if any */
  likely: { id: number; name: string } | null;
}

export function termMismatch(filename: string, target: { name: string } | undefined, terms: readonly { id: number; name: string }[]): TermMismatch | null {
  if (!target) return null;
  const file = seasonOf(filename.replace(/\.[a-z]+$/i, ""));
  const want = seasonOf(target.name);
  if (!file || !want || file === want) return null;
  const likely = terms.find((t) => seasonOf(t.name) === file) ?? null;
  return { target: target.name, likely: likely ? { id: likely.id, name: likely.name } : null };
}
