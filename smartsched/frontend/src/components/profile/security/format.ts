/** Dates of the security rows (Europe/Istanbul, the reader's language). */
import { utcDate } from "@/lib/api/auth-security";

const tag = (locale: string) => (locale === "tr" ? "tr-TR" : "en-GB");

export function shortDate(iso: string | null | undefined, locale: string): string {
  const d = utcDate(iso);
  return d ? new Intl.DateTimeFormat(tag(locale), { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Istanbul" }).format(d) : "";
}

export function dateTime(iso: string | null | undefined, locale: string): string {
  const d = utcDate(iso);
  return d ? new Intl.DateTimeFormat(tag(locale), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" }).format(d) : "";
}

/** "3 gün önce" / "3 days ago"; minutes, hours or days. */
export function relative(iso: string | null | undefined, locale: string, now: number = Date.now()): string {
  const d = utcDate(iso);
  if (!d) return "";
  const s = Math.round((d.getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(tag(locale), { numeric: "auto" });
  const a = Math.abs(s);
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86_400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86_400), "day");
}
