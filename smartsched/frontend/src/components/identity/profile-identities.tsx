"use client";
/**
 * Profil › Güvenlik: the Google Workspace / OIDC / SAML sign-ins this account can link (idp-2026-10-18; backend
 * `GET /auth/sso/me/identities`, `POST /auth/sso/{slug}/link|unlink`, app/services/identity/links.py). Microsoft
 * keeps its own section (profile-microsoft.tsx). One row per provider, one action per row:
 *
 * - "Bağla": a confirmation ("this account will sign in with it"), then re-authentication only when the sign-in is
 *   older than 10 minutes (`useReauth`), then a real navigation to the provider; it comes back to
 *   `/profile?sso=linked&provider=<slug>` or `/profile?error=<code>&provider=<slug>`, shown on the row.
 * - "Bağlantıyı kaldır": a destructive confirmation, re-authentication, a toast; focus moves to the row's "Bağla".
 *
 * Accounts without a SmartSched password (IdP-only) see nothing here: they sign in at their provider.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/admin/kit";
import { SecurityRow } from "@/components/profile/security/mfa-row";
import { shortDate } from "@/components/profile/security/format";
import { ReauthCancelled, useReauth } from "@/components/profile/security/reauth-dialog";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { apiProblem, identity, identityKeys, useMyIdentities, type LinkedProvider } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";

const KNOWN_ERRORS = ["already_linked", "domain", "cancelled"] as const;
export type LinkNotice = { provider: string; kind: "linked" | "failed" | (typeof KNOWN_ERRORS)[number] };

/** The provider's answer in the address (`?sso=linked&provider=…`, `?error=…&provider=…`); Microsoft's has no
 * provider (or `entra`) and stays with ProfileSsoNotice. */
export function readLinkNotice(search: string): LinkNotice | null {
  const p = new URLSearchParams(search);
  const provider = p.get("provider");
  if (!provider || provider === "entra") return null;
  if (p.get("sso") === "linked") return { provider, kind: "linked" };
  const error = p.get("error");
  if (!error) return null;
  return { provider, kind: (KNOWN_ERRORS as readonly string[]).includes(error) ? (error as LinkNotice["kind"]) : "failed" };
}

const goTo = (url: string) => window.location.assign(url);

export function IdentityLinkRows({ navigate = goTo, notice: given }: { navigate?: (url: string) => void; notice?: LinkNotice | null }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const q = useMyIdentities();
  const { run, dialog } = useReauth();
  const [notice, setNotice] = useState<LinkNotice | null>(() => given ?? (typeof window === "undefined" ? null : readLinkNotice(window.location.search)));
  // E2EB-F16: once read, the return keys leave the address, so a reload (or an unlink) does not show it again
  useEffect(() => {
    if (given || !notice) return;
    const u = new URL(window.location.href);
    for (const k of ["sso", "provider", "error"]) u.searchParams.delete(k);
    window.history.replaceState(window.history.state, "", `${u.pathname}${u.search}${u.hash}`);
  }, [given, notice]);
  const [linking, setLinking] = useState<LinkedProvider | null>(null);
  const [unlinking, setUnlinking] = useState<LinkedProvider | null>(null);
  const [ack, setAck] = useState(false);
  const [ackError, setAckError] = useState(false);
  const [busy, setBusy] = useState(false);
  const focusSlug = useRef<string | null>(null);
  const ackId = useId();
  const noticeRef = useRef<HTMLDivElement>(null);
  const d = q.data;

  useEffect(() => {
    if (notice && notice.kind !== "linked" && notice.kind !== "cancelled") noticeRef.current?.focus();
  }, [notice, d]);
  // after unlinking, the row's button changes: keep the focus on the row ("Bağla"), never on <body>
  useEffect(() => {
    if (!focusSlug.current) return;
    const el = document.querySelector<HTMLElement>(`[data-testid="idp-link-${focusSlug.current}"]`);
    if (el) {
      el.focus();
      focusSlug.current = null;
    }
  }, [d]);

  if (!d || !d.has_password || d.providers.length === 0) return null;
  const label = (p: LinkedProvider) => (locale === "en" ? (p.label_en ?? p.label) : p.label);

  const startLink = async (p: LinkedProvider) => {
    if (!ack) return setAckError(true);
    setLinking(null);
    try {
      const out = await run((pw) => identity.linkProvider(p.slug, pw));
      // the backend built the provider URL (PKCE / state / nonce, or a SAML request): a real navigation
      navigate(out.authorize_url);
    } catch (e) {
      if (!(e instanceof ReauthCancelled)) toast.error(apiProblem(e, locale).text ?? t("profile.identities.failed"));
    }
  };

  const doUnlink = async (p: LinkedProvider) => {
    setUnlinking(null);
    setBusy(true);
    try {
      await run((pw) => identity.unlinkProvider(p.slug, pw));
      toast.success(t("profile.identities.unlinked", { provider: label(p) }));
      if (notice?.provider === p.slug) setNotice(null); // E2EB-F16: "bağlandı" no longer holds
      focusSlug.current = p.slug;
      await qc.invalidateQueries({ queryKey: identityKeys.myIdentities });
    } catch (e) {
      if (!(e instanceof ReauthCancelled)) toast.error(apiProblem(e, locale).text ?? t("profile.identities.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {d.providers.map((p) => {
        const mine = notice?.provider === p.slug ? notice : null;
        const status = p.linked
          ? [p.email_at_login, p.linked_at ? t("profile.identities.linkedOn", { date: shortDate(p.linked_at, locale) }) : null].filter(Boolean).join(" · ")
          : t("profile.identities.notLinked");
        return (
          <SecurityRow
            key={p.slug}
            title={label(p)}
            testId={`security-idp-${p.slug}`}
            status={
              <>
                {status}
                {!p.enabled ? <span className="block type-footnote text-label-3">{t("profile.identities.providerOff")}</span> : null}
              </>
            }
            action={
              p.linked ? (
                <Button type="button" variant="ghost" shape="rect" disabled={busy} onClick={() => setUnlinking(p)} data-testid={`idp-unlink-${p.slug}`}>
                  {t("profile.identities.unlink")}
                </Button>
              ) : p.enabled ? (
                <Button
                  type="button"
                  variant="secondary"
                  shape="rect"
                  onClick={() => {
                    setAck(false);
                    setAckError(false);
                    setLinking(p);
                  }}
                  data-testid={`idp-link-${p.slug}`}
                >
                  {t("profile.identities.link")}
                </Button>
              ) : null
            }
          >
            {mine ? (
              <div ref={noticeRef} tabIndex={-1} className="rounded-xl outline-hidden">
                <Alert tone={mine.kind === "linked" ? "success" : mine.kind === "cancelled" ? "neutral" : "error"} data-testid={`idp-notice-${p.slug}`}>
                  {mine.kind === "linked" ? t("profile.identities.linkedNotice", { provider: label(p) }) : t(`profile.identities.error.${mine.kind}`, { provider: label(p) })}
                </Alert>
              </div>
            ) : null}
          </SecurityRow>
        );
      })}
      <ConfirmDialog
        open={linking !== null}
        onOpenChange={(o) => (!o ? setLinking(null) : undefined)}
        title={linking ? t("profile.identities.linkTitle", { provider: label(linking) }) : ""}
        description={linking ? t("profile.identities.linkBody", { provider: label(linking) }) : undefined}
        confirmLabel={linking ? t("profile.identities.linkConfirm", { provider: label(linking) }) : ""}
        onConfirm={() => linking && void startLink(linking)}
      >
        <div className="flex flex-col gap-3" data-testid="idp-link-dialog">
          <label htmlFor={ackId} className="flex min-h-11 items-start gap-2 type-footnote text-label-1">
            <Checkbox
              id={ackId}
              checked={ack}
              onCheckedChange={(v) => {
                setAck(v === true);
                setAckError(false);
              }}
              className="mt-0.5"
            />
            <span>{linking ? t("profile.identities.linkAck", { provider: label(linking) }) : null}</span>
          </label>
          {ackError ? <Alert tone="error">{t("profile.identities.linkIncomplete")}</Alert> : null}
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={unlinking !== null}
        onOpenChange={(o) => (!o ? setUnlinking(null) : undefined)}
        title={unlinking ? t("profile.identities.unlinkTitle", { provider: label(unlinking) }) : ""}
        description={unlinking ? t("profile.identities.unlinkBody", { provider: label(unlinking) }) : undefined}
        confirmLabel={t("profile.identities.unlink")}
        destructive
        busy={busy}
        onConfirm={() => unlinking && void doUnlink(unlinking)}
      />
      {dialog}
    </>
  );
}
