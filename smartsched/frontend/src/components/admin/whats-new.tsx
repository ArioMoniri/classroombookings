"use client";
/**
 * "What's new" (CRBS `Changelog` library + `Dashboard::changelog_status`): entries parsed from the backend
 * CHANGELOG.md with a per-user unread flag. `WhatsNewIndicator` is a self-contained header button (dot when
 * unread, opens a sheet, marks as seen) that the shell can mount; `WhatsNewPanel` is the inline list.
 */
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { crbs, useChangelog, useCrbsMutation, type Changelog } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { Loading } from "./kit";

function Entries({ data }: { data: Changelog }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  if (!data.entries.length) return <p className="type-callout text-label-2">{t("crbs.news.none")}</p>;
  return (
    <ol className="flex flex-col gap-4">
      {data.entries.slice(0, 8).map((e) => (
        <li key={e.version}>
          <p className="type-headline text-label-1">
            {e.version}
            {e.date ? <span className="ml-2 type-footnote font-normal text-label-3">{fmt.short(e.date)}</span> : null}
          </p>
          {Object.entries(e.sections).map(([section, items]) => (
            <div key={section} className="mt-1">
              <p className="type-footnote font-semibold text-label-2">{section}</p>
              <ul className="list-disc pl-5 type-callout text-label-1">
                {items.map((it, i) => (
                  <li key={i}>{it}</li>
                ))}
              </ul>
            </div>
          ))}
        </li>
      ))}
    </ol>
  );
}

export function WhatsNewPanel() {
  const { t } = useI18n();
  const q = useChangelog();
  const seen = useCrbsMutation(() => crbs.org.changelogSeen(), [["crbs", "changelog"]]);
  return (
    <Card variant="glass" className="gap-3 px-4">
      {q.isLoading ? <Loading /> : q.data ? <Entries data={q.data} /> : null}
      {q.data?.unread ? (
        <div>
          <Button variant="outline" size="sm" onClick={() => seen.mutate(undefined)}>
            {t("crbs.news.markSeen")}
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

/** Header button for the shell: a dot while there is something new; opening it marks it as seen. */
export function WhatsNewIndicator({ className }: { className?: string }) {
  const { t } = useI18n();
  const q = useChangelog();
  const [open, setOpen] = useState(false);
  const seen = useCrbsMutation(() => crbs.org.changelogSeen(), [["crbs", "changelog"]]);
  // the shell mounts two indicators (mobile bar, desktop bar under Suspense); the later one would hydrate with the
  // changelog already cached and differ from the server HTML, so the cache-fed dot waits for hydration
  const hydrated = useHydrated();
  const unread = hydrated && !!q.data?.unread;
  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className={className}
        aria-label={unread ? t("crbs.news.unread") : t("crbs.news.title")}
        onClick={() => {
          setOpen(true);
          if (unread) seen.mutate(undefined);
        }}
        data-testid="whats-new"
      >
        <span className="relative">
          <Sparkles aria-hidden />
          {unread ? <span aria-hidden className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-tint shadow-[0_0_0_2px_var(--mat-chrome-solid,white)]" /> : null}
        </span>
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="gap-0 data-[side=right]:sm:max-w-md">
          <SheetHeader className="px-5 pt-5">
            <SheetTitle className="type-title-3">{t("crbs.news.title")}</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">{q.data ? <Entries data={q.data} /> : <Loading />}</div>
        </SheetContent>
      </Sheet>
    </>
  );
}
