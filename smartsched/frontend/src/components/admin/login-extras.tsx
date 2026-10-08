"use client";
/**
 * Login page additions from CRBS `Login::index`, for the shell agent's /login (that page is theirs):
 * `<LoginBrand />` (org logo + name), `<LoginNotices />` (login message, maintenance banner, first-run
 * hint) and `<ForgotPasswordLink />` (→ /reset-password). All read the public `GET /org/public`.
 */
import Link from "next/link";
import { useOrgPublic } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert } from "./kit";

export function LoginBrand() {
  const org = useOrgPublic();
  if (!org.data?.logo_url && !org.data?.name) return null;
  return (
    <div className="mb-4 flex items-center gap-3" data-testid="login-brand">
      {org.data.logo_url ? <img src={org.data.logo_url} alt="" className="h-10 max-w-40 object-contain" /> : null}
      {org.data.name ? <p className="type-headline text-label-1">{org.data.name}</p> : null}
    </div>
  );
}

export function LoginNotices() {
  const { t } = useI18n();
  const org = useOrgPublic();
  const d = org.data;
  if (!d) return null;
  return (
    <div className="mb-4 flex flex-col gap-2">
      {d.setup_required ? (
        <Alert tone="info" title={t("crbs.login.setupTitle")}>
          <Link href="/setup" className="font-medium underline">
            {t("crbs.login.setupLink")}
          </Link>
        </Alert>
      ) : null}
      {d.maintenance_mode ? (
        <Alert tone="warning" title={t("crbs.maintenance.title")} testId="login-maintenance">
          {d.maintenance_message || t("crbs.maintenance.default")}
        </Alert>
      ) : null}
      {d.login_message ? (
        <Alert tone="info" testId="login-message">
          <span className="whitespace-pre-line">{d.login_message}</span>
        </Alert>
      ) : null}
    </div>
  );
}

export function ForgotPasswordLink({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <Link href="/reset-password" className={className ?? "type-callout text-tint-text underline-offset-4 hover:underline"} data-testid="forgot-password">
      {t("crbs.login.forgot")}
    </Link>
  );
}
