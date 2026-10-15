"use client";
/** The 404 page in the user's language (persona U-09: Next's default English "This page could not be found."). */
import Link from "next/link";
import { useI18n } from "@/lib/i18n/provider";

export function NotFoundView() {
  const { t } = useI18n();
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="type-caption font-semibold tracking-wide text-label-3">404</p>
      <h1 className="type-title-1 text-label-1">{t("wave1.notFound.title")}</h1>
      <p className="max-w-md type-callout text-label-2">{t("wave1.notFound.body")}</p>
      <Link href="/bookings" className="mt-2 inline-flex h-11 items-center rounded-full bg-tint px-5 type-callout font-medium text-tint-foreground outline-hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)">
        {t("wave1.notFound.home")}
      </Link>
    </main>
  );
}
