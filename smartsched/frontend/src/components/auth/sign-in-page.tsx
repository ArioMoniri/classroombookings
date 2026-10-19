"use client";
/**
 * /login — "Institution sheet, one door plus a quiet second door" (docs/design/v2/sign-in.md). The server page
 * reads `GET /org/public` (+ the invite banner) and passes it here, so the doors are decided before the first
 * paint (§4.3). Door 1: the Microsoft button (§7) + two hints. Door 2: a disclosure that reveals the
 * local/LDAP form (§5.3). Notices (§6.2/§6.3) in the order error, invite, reason, maintenance, login message.
 *
 * Motion (§10, "Door 2 opens / closes"): "The password form appears under the row you pressed, and the column
 * makes room." The form mounts in AnimatePresence with opacity 0 → 1 (dur.fast, 60 ms after the layout starts),
 * exit opacity → 0 in 80 ms; the footer below moves with `layout="position"` on springs.smooth (transform only,
 * no height animation); the chevron rotates on springs.snappy. Reduced motion: no layout animation, opacity
 * tween.reduced (100 ms), the chevron flips at once. Reduced transparency: the same (the sheet goes opaque).
 */
import { ChevronDown, Clock, Info, Mail } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import type { OrgPublicAuth } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";
import { roleLabelIn } from "@/lib/i18n/roles";
import { ease, springs, tween, useFinePointer, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { LocalSignInForm, rememberMethod } from "./local-sign-in";
import { MicrosoftSignIn } from "./microsoft-sign-in";
import { rich, SignInShell } from "./signin-shell";
import { doorsFor, startUrl, type InviteState, type SignInParams, type SsoErrorCode } from "./signin-model";
import { LocalInviteAccept, useInviteProvider } from "@/components/identity/local-invite-accept";
import { ProviderButtons } from "@/components/identity/provider-buttons";

export interface SignInPageProps {
  /** `null`: the backend could not be reached when the page rendered */
  org: OrgPublicAuth | null;
  params: SignInParams;
  invite: InviteState;
  lastMethodLocal: boolean;
  /** AUX-03: the last sign-in on this browser used a passkey (opens door 2, footnote) */
  lastMethodPasskey?: boolean;
}

const HINT_IDS = { domain: "signin-hint-account", signup: "signin-hint-signup" } as const;

export function SignInPage({ org, params, invite, lastMethodLocal: lastLocalCookie, lastMethodPasskey = false }: SignInPageProps) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const fine = useFinePointer();
  const auth = org?.auth ?? null;
  // AUX-03 (auth.md §4.2): a passkey last time opens door 2 like the password form did
  const lastMethodLocal = lastLocalCookie || lastMethodPasskey;
  const doors = doorsFor({ auth, reachable: org !== null, params, invite, lastMethodLocal });
  // passwordless passkeys (`/org/public` → passkeys.sign_in): autofill + the door-2 button; never on an invite
  const passkeySignIn = Boolean(org?.passkeys?.sign_in) && !doors.offline && !invite;
  // wave 3b W3-IDP (design v3 integrations.md §6): several providers → equal buttons in the admins' order; the
  // password form stays the quiet second door; an invite shows only the invited method (local: set a password)
  const buttons = auth?.providers ?? [];
  const multi = !doors.offline && (buttons.length > 1 || (buttons.length === 1 && buttons[0].kind !== "entra"));
  const invitedProvider = useInviteProvider(invite?.state === "valid" ? invite.token : null).data;
  const invitedSlug = invite?.state === "valid" ? (invitedProvider?.provider ?? null) : null;
  const localInvite = invitedSlug === "local";
  const disclosure = multi ? !localInvite && invite?.state !== "valid" && ((auth?.local_enabled ?? true) || params.methodLocal) : doors.disclosure;
  const formPrimary = localInvite || (multi ? false : !doors.microsoft);
  const [open, setOpen] = useState(multi ? disclosure && (params.methodLocal || lastMethodLocal) : doors.formOpenInitially);
  const [userOpened, setUserOpened] = useState(false);
  const orgName = org?.name?.trim() || null;
  const domain = auth?.microsoft.domain_hint?.trim() || null;
  const validInvite = invite?.state === "valid" ? invite : null;
  // an invite that the backend refused on lookup reads like the matching callback error
  const error: SsoErrorCode | null = params.error ?? (invite?.state === "expired" ? "invite_expired" : invite?.state === "invalid" ? "invite_invalid" : null);
  const base = auth?.microsoft.start_url ?? null;
  const msHref = startUrl({ base, next: params.next, invite: validInvite?.token ?? null, loginHint: validInvite?.loginHint ?? null });

  const hint1 = orgName ? (domain ? t("signin.microsoft.hintDomain", { org: orgName, domain }) : t("signin.microsoft.hint", { org: orgName })) : domain ? t("signin.microsoft.hintNoOrgDomain", { domain }) : t("signin.microsoft.hintNoOrg");
  // T-R1-30: the sign-up role in the reader's language: the API's TR/EN label, else the code through lib/i18n/roles
  // (a built-in role still carrying "Teacher" reads "Öğretim elemanı"), never the stored English name on its own
  const role = auth?.self_signup_role_label?.[locale]?.trim() || roleLabelIn(locale, { code: auth?.self_signup_role_code, name: auth?.self_signup_role_name }) || t("signin.microsoft.defaultRole");

  return (
    <SignInShell logoUrl={org?.logo_url} kvkkUrl={org?.kvkk_notice_url ?? null} testId="signin-page" hero>
      <Notices org={org} params={params} error={error} invite={invite} base={base} offline={doors.offline} />
      <h1 id="signin-title" className="type-large-title text-label-1">
        {t("signin.title")}
      </h1>
      <p className="mt-1.5 type-callout text-label-2" data-testid="signin-subtitle">
        {orgName ? t("signin.subtitle", { org: orgName }) : t("signin.subtitleNoOrg")}
      </p>

      {localInvite && invite?.state === "valid" ? (
        <div className="mt-7 flex flex-col gap-2" data-testid="signin-local-invite">
          {/* AUX-05: SetPasswordForm brings its own title "Parolanızı belirleyin" and the account line */}
          <LocalInviteAccept token={invite.token} org={orgName} next={params.next} />
        </div>
      ) : multi ? (
        <div className="mt-7 min-[600px]:[@media(max-height:960px)]:mt-5">
          <ProviderButtons
            providers={buttons}
            invited={invitedSlug}
            next={params.next}
            inviteToken={validInvite?.token ?? null}
            loginHint={validInvite?.loginHint ?? null}
            onNavigate={() => rememberMethod("microsoft")}
          />
        </div>
      ) : doors.microsoft ? (
        <div className="mt-7 min-[600px]:[@media(max-height:960px)]:mt-5">
          <MicrosoftSignIn href={msHref} label={t("signin.microsoft.label")} busyLabel={t("signin.microsoft.busy")} describedBy={`${HINT_IDS.domain} ${HINT_IDS.signup}`} onNavigate={() => rememberMethod("microsoft")} />
          <div className="mt-3 flex flex-col gap-1.5 type-footnote text-label-2" data-testid="signin-hints">
            {validInvite ? (
              <p id={HINT_IDS.domain}>{t("signin.microsoft.inviteHint")}</p>
            ) : (
              <>
                <p id={HINT_IDS.domain}>{hint1}</p>
                <p id={HINT_IDS.signup}>{doors.selfSignup ? rich(t("signin.microsoft.signup"), { role }) : t("signin.microsoft.noAccount")}</p>
              </>
            )}
          </div>
        </div>
      ) : null}

      {disclosure ? (
        // short screens (≤ 960 px tall) tighten the gaps between the doors: see SHEET_TOKENS in signin-shell.tsx
        <div className="mt-6 pt-2 hairline-t min-[600px]:[@media(max-height:960px)]:mt-4">
          <Button type="button" variant="ghost" shape="rect" size="lg" aria-expanded={open}
            aria-controls="signin-door2"
            onClick={() => {
              setUserOpened(!open);
              setOpen((o) => !o);
            }}
            className={cn("-mx-2 w-[calc(100%+16px)] justify-between px-2 text-left type-callout font-semibold whitespace-normal active:scale-100")}
            data-testid="login-disclosure"
          >
            <span>{t("signin.local.disclosure")}</span>
            <motion.span aria-hidden className="flex" animate={{ rotate: open ? 180 : 0 }} transition={reduce ? { duration: 0 } : springs.snappy}>
              <ChevronDown className="size-4 stroke-[1.75]" />
            </motion.span>
          </Button>
          <AnimatePresence initial={false}>
            {open ? (
              <motion.div
                key="door2"
                id="signin-door2"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: reduce ? tween.reduced : { duration: 0.12, ease: ease.out, delay: 0.06 } }}
                exit={{ opacity: 0, transition: reduce ? tween.reduced : { duration: 0.08, ease: ease.in } }}
                className="pt-2"
              >
                <p className="mb-4 type-footnote text-label-2">{t("signin.local.lead")}</p>
                <LocalSignInForm next={params.next} primary={false} resetLink={doors.resetLink} lastMethodLocal={lastLocalCookie} autoFocus={userOpened} passkeySignIn={passkeySignIn} lastMethodPasskey={lastMethodPasskey} />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      ) : formPrimary ? (
        <div className="mt-7 min-[600px]:[@media(max-height:960px)]:mt-5" id="signin-door2">
          <LocalSignInForm next={params.next} primary resetLink={doors.resetLink} lastMethodLocal={false} autoFocus={fine && !error && !localInvite && !params.mfa} footnote={doors.offline || localInvite ? undefined : t("signin.local.noAccount")} passkeySignIn={passkeySignIn && !localInvite} lastMethodPasskey={lastMethodPasskey} />
        </div>
      ) : null}
    </SignInShell>
  );
}

function FocusOnMount({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div ref={ref} tabIndex={-1} className="rounded-xl outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" data-testid="signin-error-focus">
      {children}
    </div>
  );
}

function NoticeAction({ href, children, testId }: { href: string; children: ReactNode; testId: string }) {
  return (
    <a href={href} className={cn(buttonVariants({ variant: "secondary", size: "md", shape: "rect" }), "mt-2.5 min-h-11 bg-black/5 text-current dark:bg-white/10")} data-testid={testId}>
      {children}
    </a>
  );
}

function Notices({ org, params, error, invite, base, offline }: { org: SignInPageProps["org"]; params: SignInParams; error: SsoErrorCode | null; invite: InviteState; base: string | null; offline: boolean }) {
  const { t } = useI18n();
  const orgName = org?.name?.trim() || null;
  const items: ReactNode[] = [];

  if (error === "cancelled") {
    items.push(
      <Alert key="cancelled" tone="neutral" data-testid="signin-notice-cancelled">
        {t("signin.notice.cancelled")}
      </Alert>,
    );
  } else if (error === "not_enabled") {
    // T-R1-09 (R1-A-29): Microsoft sign-in is off here: a state, not a failure with a support code
    items.push(
      <Alert key="not_enabled" tone="neutral" data-testid="signin-notice-not_enabled">
        {t("signin.error.notEnabled")}
      </Alert>,
    );
  } else if (error) {
    const body = errorBody(error, t, { org: orgName, ref: params.ref, invited: params.invitedMasked, signedIn: params.signedIn });
    const action =
      error === "tenant" ? (
        <NoticeAction href={startUrl({ base, next: params.next, prompt: "select_account" })} testId="signin-try-another">
          {t("signin.error.tryAnother")}
        </NoticeAction>
      ) : error === "invite_mismatch" ? (
        <NoticeAction href={startUrl({ base, next: params.next, invite: params.invite, prompt: "select_account", loginHint: invite?.state === "valid" ? invite.loginHint : null })} testId="signin-switch-account">
          {t("signin.error.switchAccount")}
        </NoticeAction>
      ) : null;
    items.push(
      <FocusOnMount key="error">
        <Alert tone="error" title={body.title} data-testid={`signin-error-${error}`}>
          <span>{body.text}</span>
          {action ? <span className="block">{action}</span> : null}
        </Alert>
      </FocusOnMount>,
    );
  }

  // AUX-04 (auth.md §5.4): back from the second step
  if (params.mfa === "tooMany" || params.mfa === "locked") {
    items.push(
      <FocusOnMount key="mfa">
        <Alert tone="error" data-testid={`signin-mfa-${params.mfa}`}>
          {params.mfa === "locked" ? t("auth.mfa.locked", { n: params.mfaMinutes ?? 15 }) : t("auth.mfa.tooMany")}
        </Alert>
      </FocusOnMount>,
    );
  } else if (params.mfa === "expired") {
    items.push(
      <Alert key="mfa" tone="neutral" icon={<Clock />} data-testid="signin-mfa-expired">
        {t("auth.mfa.expired")}
      </Alert>,
    );
  }

  if (invite?.state === "valid") {
    items.push(
      <Alert key="invite" tone="info" icon={<Mail />} title={invite.inviter ? t("signin.invite.banner", { inviter: invite.inviter }) : t("signin.invite.bannerNoInviter")} data-testid="signin-invite">
        {invite.role ? t("signin.invite.details", { role: invite.role, masked: invite.masked ?? "—", n: invite.daysLeft }) : t("signin.invite.detailsNoRole", { masked: invite.masked ?? "—", n: invite.daysLeft })}
      </Alert>,
    );
  }

  if (params.reason) {
    const key = params.reason === "expired" ? "signin.notice.expired" : params.reason === "signed_out" ? "signin.notice.signedOut" : "signin.notice.password";
    items.push(
      <Alert key="reason" tone="neutral" icon={params.reason === "expired" ? <Clock /> : <Info />} data-testid="login-session-notice">
        {t(key)}
      </Alert>,
    );
  }

  if (org?.maintenance_mode) {
    items.push(
      <Alert key="maintenance" tone="warning" title={t("signin.notice.maintenanceTitle")} data-testid="login-maintenance">
        {org.maintenance_message?.trim() || t("signin.notice.maintenanceDefault")}
      </Alert>,
    );
  }

  if (org?.login_message?.trim()) {
    items.push(
      <Alert key="message" tone="info" data-testid="login-message">
        <span className="whitespace-pre-line">{org.login_message}</span>
      </Alert>,
    );
  }

  if (org?.setup_required) {
    items.push(
      <Alert key="setup" tone="info" title={t("signin.notice.setupTitle")} data-testid="login-setup">
        <Link href="/setup" className="font-medium underline">
          {t("signin.notice.setupLink")}
        </Link>
      </Alert>,
    );
  }

  if (offline) {
    items.push(
      <Alert key="offline" tone="warning" data-testid="signin-offline">
        {t("signin.notice.offline")}
      </Alert>,
    );
  }

  if (!items.length) return null;
  return (
    <div className="mb-6 flex flex-col gap-3" data-testid="signin-notices">
      {items}
    </div>
  );
}

type T = ReturnType<typeof useI18n>["t"];

/** §6.3 copy. `failed` is the same text for every refusal; only `ref` differs (no enumeration). */
export function errorBody(code: Exclude<SsoErrorCode, "cancelled" | "not_enabled">, t: T, v: { org: string | null; ref: string | null; invited: string | null; signedIn: string | null }): { title: string; text: string } {
  switch (code) {
    case "tenant":
      return { title: t("signin.error.tenantTitle"), text: v.org ? t("signin.error.tenant", { org: v.org }) : t("signin.error.tenantNoOrg") };
    case "unavailable":
      return { title: t("signin.error.unavailableTitle"), text: t("signin.error.unavailable") };
    case "signup_closed":
      return { title: t("signin.error.signupClosedTitle"), text: t("signin.error.signupClosed") };
    case "invite_expired":
      return { title: t("signin.error.inviteExpiredTitle"), text: t("signin.error.inviteExpired") };
    case "invite_invalid":
      return { title: t("signin.error.inviteInvalidTitle"), text: t("signin.error.inviteInvalid") };
    case "domain":
      return { title: t("identity.signin.errorDomainTitle"), text: t("identity.signin.errorDomain") };
    case "invite_provider":
      return { title: t("identity.signin.errorInviteProviderTitle"), text: t("identity.signin.errorInviteProvider") };
    case "idp_mfa_required":
      // AU-16: the policy requires 2FA for the role and the identity provider asserted none
      return { title: t("auth.idp.mfaRequiredTitle"), text: t("auth.idp.mfaRequired") };
    case "invite_mismatch":
      return { title: t("signin.error.inviteMismatchTitle"), text: v.invited && v.signedIn ? t("signin.error.inviteMismatch", { invited: v.invited, signedIn: v.signedIn }) : t("signin.error.inviteMismatchPlain") };
    case "failed":
    default:
      // E2EB-F18: the same hint for every refusal (an existing unlinked account among them), so nothing is revealed
      return { title: t("signin.error.failedTitle"), text: `${v.ref ? t("signin.error.failed", { ref: v.ref }) : t("signin.error.failedNoRef")} ${t("signin.error.failedLinkHint")}` };
  }
}
