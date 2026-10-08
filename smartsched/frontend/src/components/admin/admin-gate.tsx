"use client";
/**
 * Permission gate + section navigation for /admin/* (CRBS `MY_Controller::require_permission`). The
 * backend enforces every permission again; this only keeps people out of screens that would 403.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { MessageKey } from "@/lib/i18n";
import { toast } from "sonner";
import { crbsError } from "@/lib/api/crbs";
import { adminSectionsFor, canAccessRoute, hasPermission, usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { useProfileLanguage } from "@/components/bookings/use-booking-format";
import { Loading, NoAccess } from "./kit";
import { wave1Requirement, wave1SectionsFor } from "./wave1-sections";

export function AdminGate({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const { perms, loading } = usePermissions();
  useProfileLanguage();
  if (loading) return <Loading />;
  // wave-1 screens carry their own permission (audit.view need not come with a setup.* right)
  const w1 = wave1Requirement(pathname);
  if (!(w1 !== undefined ? hasPermission(perms, w1) : canAccessRoute(perms, pathname))) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("crbs.admin.noAccessBody")} />;
  const sections: { id: string; href: string; labelKey: MessageKey }[] = [...adminSectionsFor(perms), ...wave1SectionsFor(perms)];
  return (
    <div className="flex flex-col gap-5">
      {sections.length > 1 ? (
        <nav aria-label={t("crbs.admin.title")} className="-mx-1 overflow-x-auto px-1 pb-1 scrollbar-thin">
          <ul className="flex w-max gap-1">
            <li>
              <AdminLink href="/admin" active={pathname === "/admin"}>
                {t("crbs.admin.title")}
              </AdminLink>
            </li>
            {sections.map((s) => (
              <li key={s.id}>
                <AdminLink href={s.href} active={pathname === s.href || pathname.startsWith(`${s.href}/`)}>
                  {t(s.labelKey)}
                </AdminLink>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      {children}
    </div>
  );
}

function AdminLink({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      // on a phone the tab strip scrolls sideways: keep the current screen's tab in view
      ref={active ? (el: HTMLAnchorElement | null) => el?.scrollIntoView?.({ block: "nearest", inline: "nearest" }) : undefined}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex h-7 items-center rounded-full px-3 type-footnote font-medium whitespace-nowrap outline-none focus-visible:outline-2 focus-visible:outline-(--focus)",
        active ? "bg-tint-soft text-tint-text" : "text-label-2 hover:bg-fill-2 hover:text-label-1",
      )}
    >
      {children}
    </Link>
  );
}

/** Toast for admin mutations: the backend's reason in the user's language where a code exists. */
export function useErrorToast() {
  const { t } = useI18n();
  return (e: unknown) => toast.error(bookingErrorMessage(crbsError(e), t));
}
