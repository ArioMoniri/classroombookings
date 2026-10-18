"use client";
/**
 * Profile › Microsoft hesabı (sign-in.md §13 "the self-service route", §14 `GET /auth/sso/me`, `POST/DELETE
 * /auth/sso/entra/link`). Linking proves both sides: the person re-enters the SmartSched password and confirms,
 * then the browser goes to Microsoft (`authorize_url`) and comes back to `/profile?sso=linked` or
 * `/profile?error=<code>`. Unlinking needs a confirmation; the backend refuses (409) when no password would remain.
 */
import { Link2, Unlink } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { MicrosoftLogo } from "@/components/auth/microsoft-sign-in";
import { normalizeProfileSsoError } from "@/components/auth/signin-model";
import { ConfirmDialog, Field } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { apiProblem, identity, identityKeys, useAuthProviders, useIdentityMutation, useSsoMe } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";

/** `?sso=linked|already_linked` / `?error=<code>` after the round trip to Microsoft (§14). */
export function ProfileSsoNotice() {
  const { t } = useI18n();
  const params = useSearchParams();
  // another provider's link (Google / OIDC / SAML) is shown on its own row in Profil › Güvenlik
  const other = Boolean(params.get("provider")) && params.get("provider") !== "entra";
  const sso = other ? null : params.get("sso");
  const error = other ? null : normalizeProfileSsoError(params.get("error"));
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error && error !== "cancelled") ref.current?.focus();
  }, [error]);
  if (sso === "linked")
    return (
      <Alert tone="success" data-testid="profile-sso-linked">
        {t("profile.microsoft.linkedNotice")}
      </Alert>
    );
  if (sso === "already_linked" || error === "already_linked")
    return (
      <div ref={ref} tabIndex={-1} className="rounded-xl outline-hidden">
        <Alert tone="error" data-testid="profile-sso-error">
          {t("profile.microsoft.error.already_linked")}
        </Alert>
      </div>
    );
  if (!error) return null;
  if (error === "cancelled")
    return (
      <Alert tone="neutral" data-testid="profile-sso-cancelled">
        {t("profile.microsoft.error.cancelled")}
      </Alert>
    );
  return (
    <div ref={ref} tabIndex={-1} className="rounded-xl outline-hidden">
      <Alert tone="error" data-testid="profile-sso-error">
        {t(`profile.microsoft.error.${error}`)}
      </Alert>
    </div>
  );
}

export function MicrosoftAccountSection() {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const providers = useAuthProviders();
  const me = useSsoMe();
  const [linking, setLinking] = useState(false);
  const [unlinking, setUnlinking] = useState(false);
  const unlink = useIdentityMutation(() => identity.unlink(), [identityKeys.me]);
  const enabled = Boolean(providers.data?.auth.microsoft.enabled);
  const d = me.data;
  // nothing to show when Microsoft is off and this account was never linked
  if (!d || (!enabled && !d.linked)) return null;
  return (
    <section aria-labelledby="pf-microsoft" id="microsoft" className="scroll-mt-20">
      <h2 id="pf-microsoft" className="mb-3 type-title-3 text-label-1">
        {t("profile.microsoft.title")}
      </h2>
      <Card variant="glass" className="gap-3 px-4" data-testid="profile-microsoft">
        {d.linked ? (
          <div className="flex flex-wrap items-center gap-3">
            <MicrosoftLogo size={20} />
            <span className="min-w-0 flex-1">
              <span className="block type-headline text-label-1">{d.display_name || d.email_at_login || t("profile.microsoft.account")}</span>
              <span className="block truncate type-footnote text-label-2">
                {[
                  d.email_at_login,
                  d.linked_at
                    ? t("profile.microsoft.linkedOn", {
                        date: fmt.dateTime(d.linked_at),
                      })
                    : null,
                  d.last_login_at
                    ? t("profile.microsoft.lastLogin", {
                        date: fmt.dateTime(d.last_login_at),
                      })
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
            <Button variant="ghost" onClick={() => setUnlinking(true)} data-testid="profile-ms-unlink">
              <Unlink aria-hidden />
              {t("profile.microsoft.unlink")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="type-callout text-label-2">{d.pending_bind ? t("profile.microsoft.pendingBind") : t("profile.microsoft.notLinked")}</p>
            {d.has_password ? (
              <Button variant="outline" className="self-start" onClick={() => setLinking(true)} data-testid="profile-ms-link">
                <Link2 aria-hidden />
                {t("profile.microsoft.link")}
              </Button>
            ) : (
              <p className="type-footnote text-label-3">{t("profile.microsoft.noPassword")}</p>
            )}
          </div>
        )}
      </Card>
      {linking ? <LinkDialog onClose={() => setLinking(false)} /> : null}
      <ConfirmDialog
        open={unlinking}
        onOpenChange={setUnlinking}
        title={t("profile.microsoft.unlinkTitle")}
        description={d.has_password ? t("profile.microsoft.unlinkBody") : t("profile.microsoft.unlinkNoPassword")}
        confirmLabel={t("profile.microsoft.unlink")}
        destructive
        busy={unlink.isPending}
        onConfirm={() =>
          unlink.mutate(undefined, {
            onSuccess: () => {
              toast.success(t("profile.microsoft.unlinked"));
              setUnlinking(false);
            },
            onError: (e) => {
              const p = apiProblem(e, locale);
              toast.error(p.code === "last_sign_in" ? t("profile.microsoft.unlinkNoPassword") : (p.text ?? t("profile.microsoft.failed")));
              setUnlinking(false);
            },
          })
        }
      />
    </section>
  );
}

function LinkDialog({ onClose }: { onClose: () => void }) {
  const { t, locale } = useI18n();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirmId = useId();
  return (
    <ConfirmDialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={t("profile.microsoft.linkTitle")}
      description={t("profile.microsoft.linkBody")}
      confirmLabel={t("profile.microsoft.linkConfirm")}
      busy={busy}
      onConfirm={async () => {
        if (!password || !confirm) return setError(t("profile.microsoft.linkIncomplete"));
        setError(null);
        setBusy(true);
        try {
          const out = await identity.link(password);
          // the backend built the Microsoft URL (PKCE, state, nonce): a real navigation, never fetch
          window.location.assign(out.authorize_url);
        } catch (e) {
          setBusy(false);
          const p = apiProblem(e, locale);
          setError(p.code === "password" ? t("profile.microsoft.wrongPassword") : (p.text ?? t("profile.microsoft.failed")));
          setPassword("");
        }
      }}
    >
      <div className="flex flex-col gap-3" data-testid="profile-ms-link-dialog">
        <Field label={t("profile.microsoft.password")} htmlFor="ms-link-password">
          <Input id="ms-link-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="ms-link-password" />
        </Field>
        <label htmlFor={confirmId} className="flex items-start gap-2 type-footnote text-label-1">
          <Checkbox id={confirmId} checked={confirm} onCheckedChange={(v) => setConfirm(v === true)} className="mt-0.5" data-testid="ms-link-confirm" />
          <span>{t("profile.microsoft.linkAck")}</span>
        </label>
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
    </ConfirmDialog>
  );
}
