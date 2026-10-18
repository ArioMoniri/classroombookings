"use client";
/** /admin — the CRBS setup dashboard: a checklist of what bookings need, then the screens by group. */
import { tourAnchorFor } from "@/components/welcome/tour/anchors";
import { CheckCircle2, ChevronRight, Circle, Download } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppVersion, useSetupRequirements, useSetupStatus } from "@/lib/api/crbs";
import { adminSectionsFor, usePermissions, type AdminSection } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { PageTitle, SectionTitle } from "./kit";
import { RequirementsList } from "./requirements-list";
import { BookingWeekly } from "./booking-weekly";
import { wave1SectionsFor } from "./wave1-sections";

/** WG-05: the admin tour's anchors on the setup groups */
const TOUR_GROUP: Record<AdminSection["group"], string> = { people: "admin-group-users", rooms: "admin-group-resources", calendar: "admin-group-timetable", organisation: "admin-group-organisation" };
const GROUPS: { id: AdminSection["group"]; key: MessageKey }[] = [
  { id: "people", key: "crbs.admin.group.people" },
  { id: "rooms", key: "crbs.admin.group.rooms" },
  { id: "calendar", key: "crbs.admin.group.calendar" },
  { id: "organisation", key: "crbs.admin.group.organisation" },
];

export function AdminOverview() {
  const { t, n } = useI18n();
  const { perms, can, loading } = usePermissions();
  const status = useSetupStatus();
  // the installer's server checks stay visible after setup (they list versions and paths: setup.settings only)
  const showReqs = can("setup.settings");
  const reqs = useSetupRequirements(showReqs);
  const sections: Pick<AdminSection, "href" | "labelKey" | "descriptionKey" | "group">[] = [...adminSectionsFor(perms), ...wave1SectionsFor(perms)];
  // CRBS Setup menu "Export" (Menu_model.php:149): the CSV export form lives on /my-bookings (UI gap audit #14)
  const canExport = can("system.export_bookings");
  const version = useAppVersion();
  const c = status.data?.checks;
  const checks: { key: MessageKey; done: boolean; value?: number; href: string; optional?: boolean }[] = c
    ? [
        { key: "crbs.setup.check.name", done: c.organisation_name, href: "/admin/settings" },
        { key: "crbs.setup.check.rooms", done: c.bookable_rooms > 0, value: c.bookable_rooms, href: "/rooms" },
        { key: "crbs.setup.check.groups", done: c.room_groups > 0, value: c.room_groups, href: "/admin/rooms" },
        { key: "crbs.setup.check.schedules", done: c.schedules > 0, value: c.schedules, href: "/admin/schedules" },
        { key: "crbs.setup.check.terms", done: c.terms > 0, value: c.terms, href: "/admin/sessions" },
        { key: "crbs.setup.check.holidays", done: c.holidays > 0, value: c.holidays, href: "/admin/holidays" },
        { key: "crbs.setup.check.weeks", done: c.timetable_weeks > 0, value: c.timetable_weeks, href: "/admin/weeks", optional: true },
        { key: "crbs.setup.check.smtp", done: c.smtp_configured, href: "/admin/email", optional: true },
      ]
    : [];
  const done = checks.filter((x) => x.done).length;
  // mobile-b phase 2 (CLS 0.40 at 390): the section list and the server checks depend on the permissions; until
  // they are known, one viewport-tall placeholder stands under the title instead of sections appearing one by one
  if (loading) {
    return (
      <div className="flex flex-col gap-8">
        <PageTitle title={t("crbs.admin.title")} subtitle={t("crbs.admin.lead")} />
        <div className="min-h-[80dvh] space-y-3" aria-busy="true" data-testid="admin-overview-loading">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-[22rem] w-full rounded-2xl" />
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-8">
      <PageTitle title={t("crbs.admin.title")} subtitle={t("crbs.admin.lead")} />
      <section aria-labelledby="checklist">
        <SectionTitle id="checklist">{t("crbs.setup.checklist", { done, total: checks.length })}</SectionTitle>
        <Card className="py-0">
          {status.isLoading ? (
            // the eight checklist rows, at their own height (the list replaced a one-line spinner)
            <ul aria-busy="true" data-testid="setup-checklist-loading">
              {Array.from({ length: 8 }, (_, i) => (
                <li key={i} className="flex min-h-11 items-center px-4 py-2.5 not-last:edge-hairline-b pointer-fine:min-h-0">
                  <Skeleton className="h-5 w-full" />
                </li>
              ))}
            </ul>
          ) : (
            <ul>
              {checks.map((x) => (
                <li key={x.key} className="not-last:edge-hairline-b">
                  <Link href={x.href} className="flex min-h-11 items-center gap-3 px-4 py-2.5 outline-hidden pointer-fine:min-h-0 hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
                    {x.done ? <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden /> : <Circle className="size-4 text-label-3" aria-hidden />}
                    <span className="flex-1 type-callout text-label-1">
                      {t(x.key)}
                      {x.optional ? <span className="ml-2 type-footnote text-label-3">{t("crbs.setup.optional")}</span> : null}
                    </span>
                    <span className="type-callout text-label-2 tabular-nums">{x.value !== undefined ? n(x.value) : x.done ? t("crbs.common.yes") : t("crbs.common.no")}</span>
                    <span className="sr-only">{x.done ? t("crbs.setup.done") : t("crbs.setup.todo")}</span>
                    <ChevronRight className="size-4 text-label-3" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
      {showReqs ? (
        <section aria-labelledby="requirements">
          <SectionTitle id="requirements">{t("crbs.setup.req.title")}</SectionTitle>
          {/* the server checks are a dozen rows: keep their place while they load (CLS) */}
          {reqs.isLoading ? <Skeleton className="h-[28rem] w-full rounded-2xl" data-testid="setup-requirements-loading" /> : <RequirementsList query={reqs} />}
        </section>
      ) : null}
      {GROUPS.map((g) => {
        const items = sections.filter((s) => s.group === g.id);
        if (!items.length) return null;
        return (
          <section key={g.id} aria-labelledby={`grp-${g.id}`} data-tour={TOUR_GROUP[g.id]}>
            <SectionTitle id={`grp-${g.id}`}>{t(g.key)}</SectionTitle>
            <Card variant="plain" className="py-0">
              <ul>
                {items.map((s) => (
                  <li key={s.href} className="not-last:edge-hairline-b">
                    <Link href={s.href} data-tour={tourAnchorFor(s.href)} className="flex items-center gap-3 px-4 py-3 outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
                      <span className="min-w-0 flex-1">
                        <span className="block type-headline text-label-1">{t(s.labelKey)}</span>
                        <span className="block type-footnote text-label-2">{t(s.descriptionKey)}</span>
                      </span>
                      <ChevronRight className="size-4 text-label-3" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        );
      })}
      {/* CH-07: bookings and request outcomes per week of the current term (self-gated on system.export_bookings) */}
      <BookingWeekly />
      {canExport ? (
        <section aria-labelledby="grp-data">
          <SectionTitle id="grp-data">{t("admingaps.overview.data")}</SectionTitle>
          <Card variant="plain" className="py-0">
            <Link href="/my-bookings#export-title" data-testid="admin-export" className="flex items-center gap-3 px-4 py-3 outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
              <Download className="size-4 text-label-2" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block type-headline text-label-1">{t("crbs.export.title")}</span>
                <span className="block type-footnote text-label-2">{t("admingaps.overview.exportLead")}</span>
              </span>
              <ChevronRight className="size-4 text-label-3" aria-hidden />
            </Link>
          </Card>
        </section>
      ) : null}
      {version.data ? (
        <p className="type-footnote text-label-3 tabular-nums" data-testid="admin-version">
          {t("admingaps.shell.version", { version: version.data })}
        </p>
      ) : null}
    </div>
  );
}
