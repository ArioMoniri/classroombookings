/**
 * Pure helpers of the season profiles screen (AS-15): versions grouped per key, the version a key stands on, a
 * profile key from its name, the "applies to" sentence and the weight edits the form sends.
 */
import type { AppliesTo, Labelled, Profile } from "@/lib/api/seasons";

export interface ProfileGroup {
  key: string;
  /** the active version, else the newest draft, else the newest version */
  current: Profile;
  /** a draft newer than the active version (an edit waiting for approval) */
  draft: Profile | null;
  /** newest first */
  versions: Profile[];
}

/** One row per profile key: built-ins first, then by name. */
export function groupProfiles(profiles: readonly Profile[], locale: "tr" | "en" = "tr"): ProfileGroup[] {
  const byKey = new Map<string, Profile[]>();
  for (const p of profiles) byKey.set(p.key, [...(byKey.get(p.key) ?? []), p]);
  const out: ProfileGroup[] = [];
  for (const [key, list] of byKey) {
    const versions = [...list].sort((a, b) => b.version - a.version);
    const active = versions.find((v) => v.status === "active") ?? null;
    const newestDraft = versions.find((v) => v.status === "draft") ?? null;
    const draft = newestDraft && (!active || newestDraft.version > active.version) ? newestDraft : null;
    const current = active ?? newestDraft ?? versions[0];
    if (current) out.push({ key, current, draft: active ? draft : null, versions });
  }
  const name = (g: ProfileGroup) => (locale === "tr" ? g.current.name.tr || g.current.name.en : g.current.name.en || g.current.name.tr);
  return out.sort((a, b) => Number(b.current.builtin) - Number(a.current.builtin) || name(a).localeCompare(name(b), locale));
}

const TR_ASCII: Record<string, string> = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", Ç: "c", Ğ: "g", Ö: "o", Ş: "s", Ü: "u" };
const RESERVED = new Set(["standard", "exam_week", "none"]);

/** "Final haftası (PC)" → "final_haftasi_pc" (backend rule: 1-64 chars a-z, 0-9, - and _; never a built-in key) */
export function profileKey(name: string): string {
  const base = name
    .replace(/[çğıİöşüÇĞÖŞÜ]/g, (c) => TR_ASCII[c] ?? c)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 56);
  const key = base || "profil";
  return RESERVED.has(key) ? `${key}_1` : key;
}

/** "Final · Sınav dönemi; Bütünleme · Tüm dönemler" from the server's labels ("*" = every one) */
export function appliesText(applies: readonly AppliesTo[], seasons: readonly Labelled[], kinds: readonly Labelled[], locale: "tr" | "en", any: { season: string; kind: string }): string {
  const lab = (list: readonly Labelled[], key: string, star: string) => (key === "*" ? star : (list.find((x) => x.key === key)?.label[locale] ?? key));
  return applies.map((a) => `${lab(seasons, a.season, any.season)} · ${lab(kinds, a.period_kind, any.kind)}`).join("; ");
}

/** The weight inputs of the form (strings, blank = the standard value) → the sparse override the backend stores. */
export function weightOverrides(inputs: Readonly<Record<string, string>>, defaults: Readonly<Record<string, number>>): { weights: Record<string, number>; invalid: string[] } {
  const weights: Record<string, number> = {};
  const invalid: string[] = [];
  for (const [k, raw] of Object.entries(inputs)) {
    const v = raw.trim();
    if (!v) continue;
    const n = Number(v);
    if (!Number.isInteger(n) || n < 0 || n > 10000) {
      invalid.push(k);
      continue;
    }
    if (defaults[k] !== n) weights[k] = n;
  }
  return { weights, invalid };
}

/** The row to focus after an action removed or changed `key` (the next row, else the previous, else none). */
export function nextRowKey(keys: readonly string[], key: string): string | null {
  const i = keys.indexOf(key);
  if (i < 0) return keys[0] ?? null;
  return keys[i + 1] ?? keys[i - 1] ?? null;
}
