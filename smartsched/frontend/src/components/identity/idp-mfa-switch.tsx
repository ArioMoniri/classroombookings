"use client";
/**
 * "IdP MFA'yı zorunlu tut" for one identity provider (AU-16, AU-B API.md §12; mounted in the provider wizard's
 * "Kullanıma al" step). `GET /admin/auth/providers/idp-mfa` lists the switch per provider and `PUT …/{id}/idp-mfa`
 * saves it at once (audited `auth.idp_mfa_setting`); both need `setup.authentication`, so the block hides without it.
 * SAML cannot be checked (no `amr`): the row explains instead of offering a switch. Entra gets the optional-claim note.
 * Off by default; it only bites for roles set to Zorunlu in Ayarlar › Giriş güvenliği.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { authSecurity, authSecurityKeys, mfaErrorText, type IdpMfaRow } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";

export function IdpMfaSwitch({ providerId }: { providerId: number }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const allowed = can("setup.authentication");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: authSecurityKeys.idpMfa, queryFn: authSecurity.idpMfa, enabled: allowed, retry: false, staleTime: 30_000 });
  const [busy, setBusy] = useState(false);
  const ids = { sw: useId(), help: useId() };
  const row = q.data?.find((r) => r.id === providerId);
  if (!allowed || !row) return null;

  if (!row.supported) {
    return (
      <div className="flex flex-col gap-1" data-testid="idp-mfa">
        <span className="type-callout font-semibold text-label-1">{t("auth.idp.switch")}</span>
        <p className="type-footnote text-label-2" data-testid="idp-mfa-saml">
          {t("auth.idp.samlNote")}
        </p>
      </div>
    );
  }

  const toggle = async (require: boolean) => {
    setBusy(true);
    const before = qc.getQueryData<IdpMfaRow[]>(authSecurityKeys.idpMfa);
    qc.setQueryData<IdpMfaRow[]>(authSecurityKeys.idpMfa, (list) => list?.map((r) => (r.id === providerId ? { ...r, require_idp_mfa: require } : r)));
    try {
      await authSecurity.setIdpMfa(providerId, require);
      toast.success(t("auth.idp.saved"));
      void qc.invalidateQueries({ queryKey: authSecurityKeys.idpMfa });
    } catch (e) {
      qc.setQueryData(authSecurityKeys.idpMfa, before);
      toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-start justify-between gap-4" data-testid="idp-mfa">
      <div className="flex flex-col gap-1">
        <label htmlFor={ids.sw} className="type-callout font-semibold text-label-1">
          {t("auth.idp.switch")}
        </label>
        <div id={ids.help} className="flex flex-col gap-1 type-footnote text-label-2">
          <p>{t("auth.idp.switchHelp")}</p>
          <p>{t("auth.idp.onlyRequired")}</p>
          {row.kind === "entra" ? <p data-testid="idp-mfa-entra">{t("auth.idp.entraNote")}</p> : null}
        </div>
      </div>
      <Switch id={ids.sw} checked={row.require_idp_mfa} disabled={busy} onCheckedChange={(v) => void toggle(Boolean(v))} aria-describedby={ids.help} data-testid="idp-mfa-switch" />
    </div>
  );
}
