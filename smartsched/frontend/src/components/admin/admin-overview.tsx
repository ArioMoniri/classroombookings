"use client";
/** /admin — the CRBS setup dashboard: a checklist of what bookings need, then the screens by group. */
import { CheckCircle2, ChevronRight, Circle } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { useSetupRequirements, useSetupStatus } from "@/lib/api/crbs";
import { adminSectionsFor, usePermissions, type AdminSection } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { Loading, PageTitle, SectionTitle } from "./kit";
import { RequirementsList } from "./requirements-list";

const GROUPS: { id: AdminSection["group"]; key: MessageKey }[] = [
  { id: "people", key: "crbs.admin.group.people" },
  { id: "rooms", key: "crbs.admin.group.rooms" },
  { id: "calendar", key: "crbs.admin.group.calendar" },
  { id: "organisation", key: "crbs.admin.group.organisation" },
];

export function AdminOverview() {
  const { t, n } = useI18n();
  const { perms, can } = usePermissions();
  const status = useSetupStatus();
  // the installer's server checks stay visible after setup (they list versions and paths: setup.settings only)
  const showReqs = can("setup.settings");
  const reqs = useSetupRequirements(showReqs);
  const sections = adminSectionsFor(perms);
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
  return (
    <div className="flex flex-col gap-8">
      <PageTitle title={t("crbs.admin.title")} subtitle={t("crbs.admin.lead")} />
      <section aria-labelledby="checklist">
        <SectionTitle id="checklist">{t("crbs.setup.checklist", { done, total: checks.length })}</SectionTitle>
        <Card variant="glass" className="py-0">
          {status.isLoading ? (
            <Loading className="px-4" />
          ) : (
            <ul>
              {checks.map((x) => (
                <li key={x.key} className="shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                  <Link href={x.href} className="flex items-center gap-3 px-4 py-2.5 outline-none hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
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
          <RequirementsList query={reqs} />
        </section>
      ) : null}
      {GROUPS.map((g) => {
        const items = sections.filter((s) => s.group === g.id);
        if (!items.length) return null;
        return (
          <section key={g.id} aria-labelledby={`grp-${g.id}`}>
            <SectionTitle id={`grp-${g.id}`}>{t(g.key)}</SectionTitle>
            <Card variant="plain" className="py-0">
              <ul>
                {items.map((s) => (
                  <li key={s.id} className="shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                    <Link href={s.href} className="flex items-center gap-3 px-4 py-3 outline-none hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
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
    </div>
  );
}
