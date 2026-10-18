/**
 * RF-05 (owner request 2026-10-17, "the xlsx data and details must be editable by admins"): pure helpers of the
 * /admin/catalog screens — the five lists, what a delete would touch, the edit body (changed fields only), the
 * number fields typed the way the planning lists write them, and Turkish-first error text.
 */
import { HttpError } from "@/lib/api/client";
import type { CatalogEntity, CatalogUsage } from "@/lib/api/catalog-admin";
import type { MessageKey } from "@/lib/i18n";

export type CatalogTab = "instructors" | "courses" | "programs" | "faculties" | "sections";

export const CATALOG_TABS: readonly { id: CatalogTab; entity: CatalogEntity; href: `/admin/catalog/${string}`; labelKey: MessageKey; canCreate: boolean }[] = [
  { id: "instructors", entity: "instructor", href: "/admin/catalog/instructors", labelKey: "catalog.tabs.instructors", canCreate: true },
  { id: "courses", entity: "course", href: "/admin/catalog/courses", labelKey: "catalog.tabs.courses", canCreate: true },
  { id: "programs", entity: "program", href: "/admin/catalog/programs", labelKey: "catalog.tabs.programs", canCreate: true },
  { id: "faculties", entity: "faculty", href: "/admin/catalog/faculties", labelKey: "catalog.tabs.faculties", canCreate: true },
  // sections are created with their meetings by the programme wizard (/programs/new)
  { id: "sections", entity: "section", href: "/admin/catalog/sections", labelKey: "catalog.tabs.sections", canCreate: false },
];

export const MODES = ["F2F", "ONLINE", "HYBRID", "UZEM", "ASYNC", "HOSPITAL", "SIMULATION", "OTHER"] as const;

type T = (key: MessageKey, params?: Record<string, string | number>) => string;

const USE_ORDER = ["sections", "programs", "exam_requests", "users", "bookings", "meetings", "runs"] as const;

/** The consequence lines of a delete ("3 şube", "12 ders saati talebi de arşivlenir"), in a fixed order. */
export function usageLines(usage: Pick<CatalogUsage, "uses">, t: T): string[] {
  return USE_ORDER.filter((k) => (usage.uses[k] ?? 0) > 0).map((k) => t(`catalog.uses.${k}`, { n: usage.uses[k] ?? 0 }));
}

/** What the confirm dialog offers: refuse (in use), archive (sections) or delete. */
export function deleteMode(usage: Pick<CatalogUsage, "blocked" | "action">): "blocked" | "archive" | "delete" {
  if (usage.blocked) return "blocked";
  return usage.action === "archive" ? "archive" : "delete";
}

/** Only the fields whose value changed (an unchanged save sends nothing and writes no audit row). */
export function changedFields<V extends Record<string, unknown>>(initial: V, current: V): Partial<V> {
  const out: Partial<V> = {};
  for (const k of Object.keys(current) as (keyof V)[]) {
    if (JSON.stringify(initial[k] ?? null) !== JSON.stringify(current[k] ?? null)) out[k] = current[k];
  }
  return out;
}

/** "" → null, "80" / " 80 " → 80; anything else (negative, decimal, "12:30", above `hi`) → "invalid". */
export function parseWhole(text: string, hi: number): number | null | "invalid" {
  const s = text.trim();
  if (s === "") return null;
  if (!/^\d+$/.test(s)) return "invalid";
  const n = Number(s);
  return n <= hi ? n : "invalid";
}

/** "" → null, "4,5" / "4.5" → 4.5 (comma decimals of the planning lists); out of 0..hi → "invalid". */
export function parseDecimal(text: string, hi = 60): number | null | "invalid" {
  const s = text.trim().replace(",", ".");
  if (s === "") return null;
  if (!/^\d+(\.\d+)?$/.test(s)) return "invalid";
  const n = Number(s);
  return n <= hi ? n : "invalid";
}

/** A number for an input box: 4.5 → "4,5" in Turkish. */
export function numText(v: number | null | undefined, locale: string): string {
  if (v === null || v === undefined) return "";
  return locale === "tr" ? String(v).replace(".", ",") : String(v);
}

/** "3-0-2" (theory-practice-lab hours), "" when none is known. */
export function hoursText(c: { t_hours: number | null; u_hours: number | null; l_hours: number | null }): string {
  if (c.t_hours === null && c.u_hours === null && c.l_hours === null) return "";
  return [c.t_hours, c.u_hours, c.l_hours].map((h) => h ?? 0).join("-");
}

function detailOf(e: HttpError): Record<string, unknown> | null {
  const d = e.detail;
  if (d && typeof d === "object" && !Array.isArray(d)) return d as Record<string, unknown>;
  return null;
}

/** The backend answers in English (catalogue service); people read Turkish first, so the text comes from the status. */
export function catalogErrorText(e: unknown, t: T, locale: string): string {
  if (!(e instanceof HttpError)) return t("catalog.error.generic");
  const d = detailOf(e);
  if (e.status === 409) {
    const existing = d?.existing as Record<string, unknown> | undefined;
    const name = existing ? String(existing.full_name ?? existing.display_code ?? existing.name ?? "") : "";
    if (existing && name) return t("catalog.error.duplicate", { name });
    if (d && ("sections" in d || "programs" in d || "uses" in d)) return t("catalog.error.inUse");
    return t("catalog.error.duplicatePlain");
  }
  if (e.status === 404) return t("catalog.error.notFound");
  if (e.status === 403) return t("catalog.error.forbidden");
  if (e.status === 422) return locale === "en" && e.message ? `${t("catalog.error.invalid")} (${e.message})` : t("catalog.error.invalid");
  return t("catalog.error.generic");
}

/** "Son değişiklik: Ayşe Yılmaz, 18 Eki 2026 09:40" (Europe/Istanbul), or the untouched-import line. */
export function lastChangeText(last: CatalogUsage["last_change"], t: T, locale: string): string {
  if (!last?.at) return t("catalog.neverChanged");
  const time = new Date(last.at).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { timeZone: "Europe/Istanbul", dateStyle: "medium", timeStyle: "short" });
  return t("catalog.lastChange", { name: last.actor || t("catalog.system"), time });
}

/** Case- and dot-insensitive Turkish fold for client-side filtering of short lists (faculties). */
export const fold = (s: string) => s.toLocaleLowerCase("tr-TR").normalize("NFC");
