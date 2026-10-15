"use client";
/**
 * The 404 page in the user's language (persona U-09: Next's default English "This page could not be found.").
 * Inside the shell (UI/UX review §3) it is a left-aligned page with a role-aware home link; outside (signed out,
 * the root not-found) it stays the centred public page.
 */
import Link from "next/link";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/api/shell-extra";
import { useHydrated } from "@/lib/use-hydrated";

export function NotFoundView({ inShell = false }: { inShell?: boolean }) {
  const { t } = useI18n();
  const { can, me } = usePermissions();
  const hydrated = useHydrated();
  // planners go to their overview, everyone else to the bookings (the admin was sent to bookings before)
  const home = hydrated && me && can("planning.view") ? "/dashboard" : "/bookings";
  const link = (
    <Link href={home} className="mt-2 inline-flex h-11 items-center self-start rounded-full bg-tint px-5 type-callout font-medium text-tint-foreground outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-(--focus)" data-testid="not-found-home">
      {t("wave1.notFound.home")}
    </Link>
  );
  if (inShell) {
    return (
      <div className="flex max-w-xl flex-col gap-2 pt-6" data-testid="not-found">
        <p className="type-caption font-semibold tracking-wide text-label-3">404</p>
        <h1 className="type-title-1 text-label-1">{t("wave1.notFound.title")}</h1>
        <p className="type-callout text-label-2">{t("wave1.notFound.body")}</p>
        {link}
      </div>
    );
  }
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center" data-testid="not-found">
      <p className="type-caption font-semibold tracking-wide text-label-3">404</p>
      <h1 className="type-title-1 text-label-1">{t("wave1.notFound.title")}</h1>
      <p className="max-w-md type-callout text-label-2">{t("wave1.notFound.body")}</p>
      <div className="flex justify-center">{link}</div>
    </main>
  );
}
