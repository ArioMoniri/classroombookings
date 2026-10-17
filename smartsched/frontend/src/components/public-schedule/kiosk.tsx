"use client";
/**
 * Shared pieces of the public, no-login day view (V2): the kiosk frame (large type, clock, date switcher inside the
 * window today − 7 … + 120, language, last refresh), the item list and the one "not found" page. Every page refreshes
 * every 60 s (TanStack `refetchInterval`, also in a background tab: a wall screen is never focused).
 *
 * Data minimisation is the backend's: course codes only, generic block labels, bookings as "Rezerve / Booked" or not
 * at all. Nothing here adds a name.
 *
 * Motion: none beyond the "Şimdi" row's static highlight — a kiosk changes every minute and must not twitch (motion.md
 * §2: frequent changes get no motion).
 */
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, MonitorOff } from "lucide-react";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { Button, IconButton } from "@/components/ui/button";
import { coarseHitArea } from "@/components/ui/hit-area";
import { DateField } from "@/components/ui/date-field";
import { addDays, currentItem, isRateLimited, publicWindow, type PublicItem } from "@/lib/api/public-schedule";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

/** "09:41" in Istanbul time, ticking every 20 s (enough for a minute display). */
export function useClock(): { hhmm: string; iso: string } {
  const read = () => {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
    const g = (k: string) => parts.find((p) => p.type === k)?.value ?? "";
    return { hhmm: `${g("hour")}:${g("minute")}`, iso: `${g("year")}-${g("month")}-${g("day")}` };
  };
  const [now, setNow] = useState(read);
  useEffect(() => {
    const id = window.setInterval(() => setNow(read()), 20_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

/** `?date=` from the URL (null = the backend's today) and a setter that keeps the rest of the URL. */
export function useKioskDate(): [string | null, (d: string | null) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const date = params.get("date");
  const set = (d: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (d) next.set("date", d);
    else next.delete("date");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  return [date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : null, set];
}

export function useLongDate() {
  const { locale } = useI18n();
  return (iso: string) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Intl.DateTimeFormat(intlLocale(locale), { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)));
  };
}

export function KioskFrame({ title, subtitle, back, today, date, onDate, updatedAt, children }: { title: string; subtitle?: ReactNode; back?: { href: string; label: string }; today: string | null; date: string | null; onDate: (d: string | null) => void; updatedAt?: number; children: ReactNode }) {
  const { t, locale } = useI18n();
  const clock = useClock();
  const long = useLongDate();
  const shown = date ?? today;
  const win = today ? publicWindow(today) : null;
  const go = (n: number) => {
    if (!shown || !win) return;
    const next = addDays(shown, n);
    if (next < win.min || next > win.max) return;
    onDate(next === today ? null : next);
  };
  const updated = updatedAt ? new Intl.DateTimeFormat(intlLocale(locale), { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" }).format(new Date(updatedAt)) : null;
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[1800px] flex-col gap-5 px-[max(1rem,env(safe-area-inset-left))] pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1.5rem,env(safe-area-inset-bottom))] sm:px-8 sm:pt-6" data-testid="kiosk">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {back ? (
            <Link href={back.href} className={cn("relative inline-block type-callout font-medium text-tint-text underline-offset-4 hover:underline", coarseHitArea)} data-testid="kiosk-back">
              {back.label}
            </Link>
          ) : (
            <p className="type-callout font-medium text-label-2">{t("publicSchedule.brand")}</p>
          )}
          <h1 className="type-large-title text-label-1 lg:text-5xl lg:leading-tight" data-testid="kiosk-title">
            {title}
          </h1>
          {subtitle ? <p className="mt-1 type-title-3 font-normal text-label-2">{subtitle}</p> : null}
        </div>
        <div className="flex items-center gap-3 self-start sm:self-auto">
          <p className="type-title-1 font-semibold text-label-1 tabular-nums lg:text-5xl" aria-label={t("publicSchedule.clock", { time: clock.hhmm })} data-testid="kiosk-clock">
            {clock.hhmm}
          </p>
          <LocaleToggle />
        </div>
      </header>
      {shown && win ? (
        <nav className="flex flex-wrap items-center gap-2" aria-label={t("publicSchedule.dateNav")}>
          <IconButton label={t("publicSchedule.prevDay")} variant="outline" onClick={() => go(-1)} disabled={addDays(shown, -1) < win.min} data-testid="kiosk-prev">
            <ChevronLeft aria-hidden />
          </IconButton>
          <DateField value={shown} min={win.min} max={win.max} onChange={(v) => v && onDate(v === today ? null : v)} aria-label={t("publicSchedule.date")} className="w-44" data-testid="kiosk-date" />
          <IconButton label={t("publicSchedule.nextDay")} variant="outline" onClick={() => go(1)} disabled={addDays(shown, 1) > win.max} data-testid="kiosk-next">
            <ChevronRight aria-hidden />
          </IconButton>
          {date && date !== today ? (
            <Button variant="ghost" onClick={() => onDate(null)} data-testid="kiosk-today">
              {t("publicSchedule.today")}
            </Button>
          ) : null}
          <p className="type-title-3 font-medium text-label-1 sm:ml-2" data-testid="kiosk-long-date">
            {long(shown)}
          </p>
        </nav>
      ) : null}
      <main className="flex-1">{children}</main>
      <footer className="flex flex-wrap items-center justify-between gap-2 type-footnote text-label-3">
        <span>{t("publicSchedule.footer")}</span>
        {updated ? <span aria-live="off">{t("publicSchedule.updated", { time: updated })}</span> : null}
      </footer>
    </div>
  );
}

/** The one answer for "off", "unknown" and "outside the window" (the backend never says which). */
export function PublicNotFound() {
  const { t } = useI18n();
  return (
    <div className="mx-auto flex min-h-dvh max-w-xl flex-col items-start justify-center gap-3 px-6" data-testid="public-not-found">
      <MonitorOff className="size-8 text-label-3" aria-hidden />
      <h1 className="type-title-1 text-label-1">{t("publicSchedule.notFoundTitle")}</h1>
      <p className="type-body text-label-2">{t("publicSchedule.notFound")}</p>
      <LocaleToggle />
    </div>
  );
}

export function PublicError({ error }: { error: unknown }) {
  const { t } = useI18n();
  return (
    <p role="status" className="rounded-xl bg-status-warning px-4 py-3 type-body text-status-warning-fg" data-testid="public-error">
      {isRateLimited(error) ? t("publicSchedule.rateLimited") : t("publicSchedule.offline")}
    </p>
  );
}

const KIND_CLASS: Record<PublicItem["kind"], string> = {
  class: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--status-locked-solid)_12%)]",
  booked: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--cat-3)_17%)]",
  reserved: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_6%)]",
};

/** The day of one room: time, label, kind; the running item is marked "Şimdi" on today's page. */
export function ItemList({ items, live, hhmm, large, emptyText, slotDisplay }: { items: PublicItem[]; live: boolean; hhmm: string; large?: boolean; emptyText: string; slotDisplay?: PublicSlotLabels }) {
  const { t, locale } = useI18n();
  // W3-SLOT: the administrator's label choice (period ordinals, start time or range); the kiosk has no schedule
  // period names, so "period" reads as ordinals; "both" keeps the time, as before
  const when = (it: PublicItem): string => {
    if (slotDisplay?.label === "period")
      return it.start_period === it.end_period ? t("slotDisplay.ordinal", { n: it.start_period }) : t("publicSchedule.periodSpan", { from: it.start_period, to: it.end_period });
    return slotDisplay?.time_format === "start" ? it.start : `${it.start}–${it.end}`;
  };
  const now = live ? currentItem(items, hhmm) : null;
  if (!items.length) return <p className={cn("text-label-2", large ? "type-title-3 font-normal" : "type-callout")}>{emptyText}</p>;
  return (
    <ol className="flex flex-col gap-1.5">
      {items.map((it) => {
        const isNow = now === it;
        const past = live && it.end <= hhmm;
        return (
          <li
            key={`${it.start}-${it.end}-${it.kind}-${it.label.tr}`}
            className={cn("flex items-baseline gap-3 rounded-lg px-3 edge-hairline", large ? "py-3" : "py-2", KIND_CLASS[it.kind], past && "opacity-60", isNow && "outline-2 -outline-offset-2 outline-(--accent)")}
            data-kind={it.kind}
            data-now={isNow ? "true" : undefined}
          >
            <span className={cn("shrink-0 font-semibold text-label-1 tabular-nums", large ? "type-title-3" : "type-callout")} data-slot="kiosk-when" aria-label={`${it.start}–${it.end}, ${when(it)}`}>
              {when(it)}
            </span>
            <span className={cn("min-w-0 flex-1 truncate font-medium text-label-1", large ? "type-title-2" : "type-headline")}>{locale === "tr" ? it.label.tr : it.label.en}</span>
            {isNow ? <span className="shrink-0 rounded-full bg-tint px-2 py-0.5 type-caption font-semibold text-tint-foreground">{t("publicSchedule.now")}</span> : <span className="shrink-0 type-footnote text-label-2">{t(`publicSchedule.kind.${it.kind}`)}</span>}
          </li>
        );
      })}
    </ol>
  );
}
