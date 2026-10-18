"use client";
/**
 * Profil › Giriş ve güvenlik (`/profile#security`, docs/design/v3/auth.md §6; AUX-06/07). One glass card, one row per
 * subject: Parola, İki aşamalı doğrulama, Geçiş anahtarları, Oturumlar ve cihazlar (sessions + remembered devices,
 * "Diğer tüm oturumları kapat"), Son girişler. The only primary is "Aç" (2FA off). SSO-only accounts (D1) get one explanation row instead of the first
 * three; the devices and history stay. The target of every security e-mail.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { authSecurityKeys, useMfaStatus } from "@/lib/api/auth-security";
import { IdentityLinkRows } from "@/components/identity/profile-identities";
import { useOrgPublic } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { HistoryRow } from "./sign-in-history";
import { MfaRow, SecurityRow } from "./mfa-row";
import { PasskeysRow } from "./passkeys-list";
import { SessionsRow } from "./sessions-list";

/** "Değiştir": the existing password form of the profile page (`#pf-pw`), focused. */
function focusPasswordForm() {
  const heading = document.getElementById("pf-pw");
  const section = heading?.closest("section") ?? heading;
  section?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  const field = section?.querySelector<HTMLInputElement>("input:not([type=hidden]):not([disabled])");
  field?.focus({ preventScroll: true });
}

export function SecuritySection() {
  const { t } = useI18n();
  const org = useOrgPublic().data?.name ?? null;
  const qc = useQueryClient();
  const q = useMfaStatus();
  const refresh = () => void qc.invalidateQueries({ queryKey: authSecurityKeys.status });
  const s = q.data;
  return (
    <section id="security" aria-labelledby="pf-security" className="scroll-mt-20" data-testid="security-section">
      <h2 id="pf-security" className="mb-3 type-title-3 text-label-1">
        {t("auth.security.title")}
      </h2>
      <Card variant="glass" className="px-4">
        {q.isLoading ? (
          <div aria-busy="true" aria-label={t("auth.security.loading")} className="flex flex-col gap-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : !s ? (
          <Alert tone="error">{t("auth.security.loadFailed")}</Alert>
        ) : (
          <ul className="flex flex-col divide-y divide-(--hairline)">
            {s.account_type === "sso" ? (
              <SecurityRow title={t("auth.security.ssoTitle")} status={t("auth.security.ssoText")} testId="security-sso" />
            ) : (
              <>
                <SecurityRow
                  title={t("auth.security.password")}
                  status={s.account_type === "ldap" ? t("auth.security.passwordLdap") : t("auth.security.passwordStatus")}
                  action={
                    s.account_type === "ldap" ? null : (
                      <Button type="button" variant="secondary" shape="rect" onClick={focusPasswordForm} data-testid="password-change">
                        {t("auth.security.change")}
                      </Button>
                    )
                  }
                  testId="security-password"
                />
                <MfaRow status={s} org={org} onChanged={refresh} />
                {s.reason !== "mfa_off" ? <PasskeysRow status={s} org={org} onChanged={refresh} /> : null}
                {/* idp-2026-10-18: link / unlink a Google, OIDC or SAML sign-in (Microsoft has its own section) */}
                <IdentityLinkRows />
              </>
            )}
            <SessionsRow devices={s.trusted_devices} onChanged={refresh} />
            <HistoryRow />
          </ul>
        )}
      </Card>
    </section>
  );
}
