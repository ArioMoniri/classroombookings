"use client";
/**
 * Admin › Kullanıcılar: sign-in security (docs/design/v3/auth.md §7; AUX-08, AU-B API.md §8). Mounted by the users
 * owner (ask A5) from `users-admin.tsx` (row menu) and the edit sheet:
 * - `useUserSecurity({ meId, onShowCode })` → `menuItems(user)` (the "Giriş" group after a separator), `block(user)`
 *   (the edit sheet's "Giriş ve güvenlik"), and `dialogs` (render once, outside the menu, so they outlive it);
 * - `MfaMethodTag` ("Yerel · 2FA", "2FA bekleniyor ({date})") and `MfaFilterSelect` + `matchesMfaFilter` for the list.
 * Per account kind (§7.2): local with e-mail → "Parola sıfırlama bağlantısı gönder", "2FA'yı sıfırla" (when on),
 * "Sıfırlama kodunu ekranda göster"; local without e-mail → the code, the reset and an explanation; LDAP → the reset +
 * "Parola kurum dizininde (LDAP) değiştirilir."; SSO → one explanation row, never a button (D10); own account → the
 * link to Profil › Giriş ve güvenlik. The dialogs state the consequence first, need a reason (10–500) and how the
 * identity was checked, and map every refusal of §7.3 / §7.4 to its sentence. "Oturumları sonlandır" (AU-15,
 * `POST /admin/users/{id}/sessions/revoke`) confirms first and works for every account but your own.
 */
import { ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { HttpError } from "@/lib/api/client";
import { authSecurity, authSecurityKeys, IDENTITY_CHECKS, maskIdentifier, mfaErrorCode, retryAfterSeconds, useAdminMfa, type AdminMfa, type IdentityCheck } from "@/lib/api/auth-security";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { rich } from "@/components/auth/signin-shell";
import { shortDate, relative } from "@/components/profile/security/format";
import type { MethodView } from "./users-admin-identity-model";

/* ---------------------------------------------------------------------------------------------- the model */

export type SecurityAccount = "local" | "ldap" | "sso";

/** The sign-in kind of a row (users-admin-identity-model `methodView`): SSO accounts get no SmartSched 2FA (D1). */
export function securityAccount(method: MethodView): SecurityAccount {
  if (method === "microsoft" || method === "microsoftInvite") return "sso";
  if (method === "ldap") return "ldap";
  return "local";
}

export type MfaListState = "on" | "off" | "pending";
export type MfaFilter = "" | MfaListState;

/** The list's 2FA state from the users status map (AU-18 `mfa_state`): `null` for identity-provider-only accounts
 *  (no tag, matches no 2FA filter). `mfa_grace_until` is null for `pending` until the first sign-in under the policy. */
export function mfaListState(s: unknown): MfaListState | null {
  const v = s && typeof s === "object" ? (s as { mfa_state?: unknown }).mfa_state : undefined;
  return v === "on" || v === "off" || v === "pending" ? v : null;
}

export function matchesMfaFilter(state: MfaListState | null, filter: MfaFilter): boolean {
  return filter === "" || state === filter;
}

export interface SecurityUser {
  id: number;
  /** the name shown in the dialogs */
  name: string;
  email?: string | null;
  account: SecurityAccount;
  /** the identity provider's name for SSO rows ("Microsoft") */
  providerName?: string | null;
  /** from the list (ask AU-B), when known */
  mfa?: MfaListState | null;
  /** role code, for the "must set up again" sentence */
  role?: string | null;
  lastLoginAt?: string | null;
}

/** Reason chips of §7.3; "compromised" hides "Geçiş anahtarlarını koru". */
export const REASON_CHIPS = ["lost", "codes", "compromised"] as const;
export type ReasonChip = (typeof REASON_CHIPS)[number];
const CHIP_KEY: Record<ReasonChip, MessageKey> = { lost: "auth.admin.chipLost", codes: "auth.admin.chipCodes", compromised: "auth.admin.chipCompromised" };
const CHECK_KEY: Record<IdentityCheck, MessageKey> = { in_person: "auth.admin.idInPerson", video_call: "auth.admin.idVideo", phone_callback: "auth.admin.idPhone", other: "auth.admin.idOther" };
export const REASON_MIN = 10;
export const REASON_MAX = 500;

/** Client-side check of the reset form (§7.3): reason 10–500 characters and an identity check. */
export function resetProblem(reason: string, check: IdentityCheck | ""): "reason" | "identity" | null {
  const n = reason.trim().length;
  if (n < REASON_MIN || n > REASON_MAX) return "reason";
  if (!check) return "identity";
  return null;
}

/** "Açık · uygulama + 2 geçiş anahtarı" / "Kapalı". */
export function adminStatusText(t: ReturnType<typeof useI18n>["t"], s: AdminMfa): string {
  const parts: string[] = [];
  if (s.totp_enabled) parts.push(t("auth.admin.methodApp"));
  if (s.passkeys.length) parts.push(t("auth.admin.methodPasskeys", { n: s.passkeys.length }));
  return parts.length ? t("auth.admin.statusOnDetail", { methods: parts.join(" + ") }) : t("auth.admin.statusOff");
}

const hasFactor = (s: AdminMfa | undefined) => Boolean(s && (s.totp_enabled || s.passkeys.length > 0));

/* ------------------------------------------------------------------------------------------ list pieces */

export function MfaMethodTag({ state, graceUntil }: { state: MfaListState | null; graceUntil?: string | null }) {
  const { t, locale } = useI18n();
  if (state === "on")
    return (
      <Badge variant="secondary" className="gap-1" data-testid="mfa-tag">
        <ShieldCheck aria-hidden className="size-3.5" />
        {t("auth.admin.tag2fa")}
      </Badge>
    );
  if (state === "pending")
    return (
      <Badge variant="secondary" className="gap-1 text-status-warning-fg" data-testid="mfa-tag-pending">
        <ShieldAlert aria-hidden className="size-3.5" />
        {graceUntil ? t("auth.admin.tagPendingDate", { date: shortDate(graceUntil, locale) }) : t("auth.admin.tagPendingFirst")}
      </Badge>
    );
  return null;
}

export function MfaFilterSelect({ value, onChange, className }: { value: MfaFilter; onChange: (v: MfaFilter) => void; className?: string }) {
  const { t } = useI18n();
  const id = useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="type-footnote font-semibold text-label-2">
        {t("auth.admin.filter")}
      </label>
      <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value as MfaFilter)} data-testid="mfa-filter">
        <option value="">{t("auth.admin.filterAll")}</option>
        <option value="on">{t("auth.admin.filterOn")}</option>
        <option value="off">{t("auth.admin.filterOff")}</option>
        <option value="pending">{t("auth.admin.filterPending")}</option>
      </NativeSelect>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ the actions */

type Kind = "reset" | "link" | "sessions";
type Open = { kind: Kind; user: SecurityUser } | null;

export function useUserSecurity({ meId, onShowCode }: { meId: number | null | undefined; onShowCode?: (userId: number) => void }): {
  menuItems: (u: SecurityUser) => ReactNode;
  block: (u: SecurityUser) => ReactNode;
  dialogs: ReactNode;
} {
  const [open, setOpen] = useState<Open>(null);
  const actions = (u: SecurityUser) => ({
    own: meId != null && u.id === meId,
    link: u.account === "local" && Boolean(u.email),
    reset: u.account !== "sso" && u.mfa !== "off",
    code: u.account === "local" && Boolean(onShowCode),
    // AU-15: SmartSched sessions end for every kind of account (SSO too); your own via Profil
    sessions: !(meId != null && u.id === meId),
  });
  const menuItems = (u: SecurityUser) => <SecurityMenuItems u={u} a={actions(u)} onOpen={(kind) => setOpen({ kind, user: u })} onShowCode={onShowCode} />;
  const block = (u: SecurityUser) => <SecurityBlock u={u} a={actions(u)} onOpen={(kind) => setOpen({ kind, user: u })} onShowCode={onShowCode} />;
  const close = () => setOpen(null);
  const dialogs = (
    <>
      <ResetMfaDialog user={open?.kind === "reset" ? open.user : null} onClose={close} />
      <ResetLinkDialog user={open?.kind === "link" ? open.user : null} onClose={close} onShowCode={onShowCode} />
      <EndSessionsDialog user={open?.kind === "sessions" ? open.user : null} onClose={close} />
    </>
  );
  return { menuItems, block, dialogs };
}

type Acts = { own: boolean; link: boolean; reset: boolean; code: boolean; sessions: boolean };

type T = ReturnType<typeof useI18n>["t"];

function explanation(t: T, u: SecurityUser, a: Acts): string | null {
  if (u.account === "sso") return u.providerName ? t("auth.admin.ssoRowNamed", { provider: u.providerName }) : t("auth.admin.ssoRow");
  if (u.account === "ldap") return t("auth.admin.ldapRow");
  if (!a.link && !u.email) return t("auth.admin.noEmailRow");
  return null;
}

function SecurityMenuItems({ u, a, onOpen, onShowCode }: { u: SecurityUser; a: Acts; onOpen: (k: Kind) => void; onShowCode?: (id: number) => void }) {
  const { t } = useI18n();
  const note = explanation(t, u, a);
  return (
    <>
      <DropdownMenuSeparator />
      <DropdownMenuGroup data-testid={`user-security-menu-${u.id}`}>
        <DropdownMenuLabel>{t("auth.admin.group")}</DropdownMenuLabel>
        {u.account === "sso" ? null : (
          <>
            {a.link ? (
              <DropdownMenuItem onClick={() => onOpen("link")} data-testid={`user-send-link-${u.id}`}>
                {t("auth.admin.sendLink")}
              </DropdownMenuItem>
            ) : null}
            {a.own ? (
              <DropdownMenuItem render={<Link href="/profile#security" />} data-testid={`user-own-security-${u.id}`}>
                {t("auth.admin.ownRow")}
              </DropdownMenuItem>
            ) : a.reset ? (
              <DropdownMenuItem variant="destructive" onClick={() => onOpen("reset")} data-testid={`user-reset-mfa-${u.id}`}>
                {t("auth.admin.reset")}
              </DropdownMenuItem>
            ) : null}
            {a.code ? (
              <DropdownMenuItem onClick={() => onShowCode?.(u.id)} data-testid={`user-show-code-${u.id}`}>
                {t("auth.admin.showCode")}
              </DropdownMenuItem>
            ) : null}
          </>
        )}
        {a.sessions ? (
          <DropdownMenuItem onClick={() => onOpen("sessions")} data-testid={`user-end-sessions-${u.id}`}>
            {t("auth.admin.endSessions")}
          </DropdownMenuItem>
        ) : null}
        {/* D10: an explanation, not a disabled button (the reason is the content, also on touch) */}
        {note ? (
          <p role="note" className="max-w-72 px-1.5 py-1.5 type-footnote text-label-2" data-testid={`user-security-note-${u.id}`}>
            {note}
          </p>
        ) : null}
      </DropdownMenuGroup>
    </>
  );
}

function SecurityBlock({ u, a, onOpen, onShowCode }: { u: SecurityUser; a: Acts; onOpen: (k: Kind) => void; onShowCode?: (id: number) => void }) {
  const { t, locale } = useI18n();
  const q = useAdminMfa(u.id, u.account !== "sso");
  const note = explanation(t, u, a);
  const method = u.account === "sso" ? (u.providerName ?? "SSO") : u.account === "ldap" ? "LDAP" : t("auth.admin.methodLocal");
  const status = u.account === "sso" ? null : q.data ? adminStatusText(t, q.data) : q.isLoading ? t("auth.admin.loading") : null;
  return (
    <section aria-labelledby={`sec-${u.id}`} className="flex flex-col gap-3" data-testid="user-security-block">
      <h3 id={`sec-${u.id}`} className="type-headline text-label-1">
        {t("auth.admin.blockTitle")}
      </h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 type-callout">
        <dt className="text-label-2">{t("auth.admin.method")}</dt>
        <dd className="text-label-1">{method}</dd>
        {status ? (
          <>
            <dt className="text-label-2">{t("auth.admin.mfaLabel")}</dt>
            <dd className="text-label-1" data-testid="user-security-status">
              {status}
            </dd>
          </>
        ) : null}
        <dt className="text-label-2">{t("auth.admin.lastSignIn")}</dt>
        <dd className="text-label-1">{u.lastLoginAt ? relative(u.lastLoginAt, locale) : t("auth.security.never")}</dd>
      </dl>
      {u.account !== "sso" ? (
        <div className="flex flex-wrap gap-2 max-sm:[&>*]:w-full">
          {a.link ? (
            <Button type="button" variant="secondary" shape="rect" onClick={() => onOpen("link")} data-testid="block-send-link">
              {t("auth.admin.sendLink")}
            </Button>
          ) : null}
          {a.own ? (
            <Link href="/profile#security" className="inline-flex min-h-11 items-center type-callout text-tint underline-offset-2 hover:underline" data-testid="block-own">
              {t("auth.admin.ownRow")}
            </Link>
          ) : a.reset && (q.data ? hasFactor(q.data) : true) ? (
            <Button type="button" variant="secondary" shape="rect" className="text-status-infeasible-fg" onClick={() => onOpen("reset")} data-testid="block-reset-mfa">
              {t("auth.admin.reset")}
            </Button>
          ) : null}
          {a.code ? (
            <Button type="button" variant="ghost" shape="rect" onClick={() => onShowCode?.(u.id)} data-testid="block-show-code">
              {t("auth.admin.showCode")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {a.sessions ? (
        <Button type="button" variant="secondary" shape="rect" className="self-start max-sm:w-full" onClick={() => onOpen("sessions")} data-testid="block-end-sessions">
          {t("auth.admin.endSessions")}
        </Button>
      ) : null}
      {note ? (
        <p className="type-footnote text-label-2" data-testid="block-note">
          {note}
        </p>
      ) : null}
    </section>
  );
}

/* ----------------------------------------------------------------------------------------- the dialogs */

function resetErrorKey(e: unknown): MessageKey {
  const c = mfaErrorCode(e);
  if (c === "own_account") return "auth.admin.errOwn";
  if (c === "sso_account") return "auth.admin.errSso";
  if (c === "account_disabled") return "auth.admin.errDisabled";
  if (e instanceof HttpError && e.status === 403) return "auth.admin.err403";
  return "auth.admin.errGeneric";
}

export function ResetMfaDialog({ user, onClose }: { user: SecurityUser | null; onClose: () => void }) {
  return (
    <Dialog open={user !== null} onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent role="alertdialog" className="sm:max-w-[520px]" data-testid="reset-mfa-dialog">
        {user ? <ResetMfaForm key={user.id} user={user} onClose={onClose} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function ResetMfaForm({ user, onClose }: { user: SecurityUser; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const summary = useAdminMfa(user.id).data;
  const ids = { reason: useId(), hint: useId(), count: useId(), check: useId(), err: useId(), keep: useId() };
  const [chip, setChip] = useState<ReasonChip | null>(null);
  const [reason, setReason] = useState("");
  const [check, setCheck] = useState<IdentityCheck | "">("");
  const [keep, setKeep] = useState(false);
  const [problem, setProblem] = useState<"reason" | "identity" | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const passkeys = summary?.passkeys.length ?? 0;
  const keepOffered = passkeys > 0 && chip !== "compromised";
  const policy = qc.getQueryData<{ mfa_policy?: string; mfa_roles?: string[] }>(authSecurityKeys.policy);
  const required = policy?.mfa_policy === "required_for_roles" && Boolean(user.role && policy.mfa_roles?.includes(user.role));

  const pickChip = (c: ReasonChip, on: boolean) => {
    setChip(on ? c : null);
    if (on) setReason(t(CHIP_KEY[c]));
    if (c === "compromised" && on) setKeep(false);
    setProblem(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const p = resetProblem(reason, check);
    setProblem(p);
    if (p || busy) return;
    setBusy(true);
    setError(null);
    try {
      await authSecurity.adminReset(user.id, { reason: reason.trim(), identity_check: check as IdentityCheck, keep_passkeys: keepOffered && keep });
      toast.success(t("auth.admin.resetDone", { name: user.name }));
      void qc.invalidateQueries({ queryKey: authSecurityKeys.admin(user.id) });
      onClose();
    } catch (err) {
      setError(resetErrorKey(err));
    } finally {
      setBusy(false);
    }
  };

  const n = reason.trim().length;
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{t("auth.admin.resetTitle", { name: user.name })}</DialogTitle>
        <DialogDescription data-testid="reset-consequence">
          {keepOffered && keep ? t("auth.admin.resetBodyKeep") : t("auth.admin.resetBody", { name: user.name })}
          {required ? ` ${t("auth.admin.resetRequired")}` : ""}
        </DialogDescription>
      </DialogHeader>
      {error ? (
        <Alert tone="error" data-testid="reset-error">
          {t(error)}
        </Alert>
      ) : null}
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("auth.admin.reason")}>
        {REASON_CHIPS.map((c) => (
          <Chip key={c} selected={chip === c} onSelectedChange={(on) => pickChip(c, on)} data-testid={`reset-chip-${c}`}>
            {t(CHIP_KEY[c])}
          </Chip>
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.reason} className="type-callout font-semibold text-label-1">
          {t("auth.admin.reason")}
        </label>
        <Textarea
          id={ids.reason}
          rows={3}
          maxLength={REASON_MAX}
          value={reason}
          onChange={(e) => (setReason(e.target.value), setProblem(null))}
          aria-invalid={problem === "reason" || undefined}
          aria-describedby={[ids.hint, ids.count, problem === "reason" ? ids.err : ""].filter(Boolean).join(" ")}
          required
          data-testid="reset-reason"
        />
        <div className="flex justify-between gap-3 type-footnote text-label-2">
          <span id={ids.hint}>{t("auth.admin.reasonHint")}</span>
          <span id={ids.count} className="shrink-0 tabular-nums" aria-live="off">
            {n}/{REASON_MAX}
          </span>
        </div>
        {problem === "reason" ? (
          <p id={ids.err} className="type-footnote text-status-infeasible-fg" data-testid="reset-reason-error">
            {t("auth.admin.reasonShort")}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.check} className="type-callout font-semibold text-label-1">
          {t("auth.admin.identity")}
        </label>
        <NativeSelect id={ids.check} value={check} onChange={(e) => (setCheck(e.target.value as IdentityCheck | ""), setProblem(null))} aria-invalid={problem === "identity" || undefined} aria-describedby={problem === "identity" ? `${ids.check}-err` : undefined} required data-testid="reset-identity">
          <option value="">{t("auth.admin.identityPick")}</option>
          {IDENTITY_CHECKS.map((c) => (
            <option key={c} value={c}>
              {t(CHECK_KEY[c])}
            </option>
          ))}
        </NativeSelect>
        {problem === "identity" ? (
          <p id={`${ids.check}-err`} className="type-footnote text-status-infeasible-fg" data-testid="reset-identity-error">
            {t("auth.admin.identityRequired")}
          </p>
        ) : null}
      </div>
      {keepOffered ? (
        <label htmlFor={ids.keep} className="flex min-h-11 cursor-pointer items-center gap-3 type-callout text-label-1">
          <Checkbox id={ids.keep} checked={keep} onCheckedChange={(v) => setKeep(Boolean(v))} data-testid="reset-keep-passkeys" />
          {t("auth.admin.keepPasskeys", { n: passkeys })}
        </label>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="secondary" shape="rect" onClick={onClose}>
          {t("auth.admin.cancel")}
        </Button>
        <BusyButton type="submit" variant="destructive" shape="rect" busy={busy} busyLabel={t("busy.working")} data-testid="reset-confirm">
          {t("auth.admin.resetConfirm")}
        </BusyButton>
      </DialogFooter>
    </form>
  );
}

type LinkError = { key: MessageKey; vars?: Record<string, number>; offerCode: boolean };

function linkError(e: unknown): LinkError {
  const c = mfaErrorCode(e);
  if (c === "no_email") return { key: "auth.admin.errNoEmail", offerCode: true };
  if (c === "mail_not_configured") return { key: "auth.admin.errMail", offerCode: true };
  if (c === "mail_failed" || (e instanceof HttpError && e.status === 502)) return { key: "auth.admin.errMailFailed", offerCode: false };
  if (c === "sso_account") return { key: "auth.admin.errSsoLink", offerCode: false };
  if (c === "directory_account") return { key: "auth.admin.errLdap", offerCode: false };
  if (c === "account_disabled") return { key: "auth.admin.errDisabled", offerCode: false };
  if (e instanceof HttpError && e.status === 429) return { key: "auth.admin.err429", vars: { n: Math.max(1, Math.ceil((retryAfterSeconds(e) ?? 60) / 60)) }, offerCode: false };
  if (e instanceof HttpError && e.status === 403) return { key: "auth.admin.err403", offerCode: false };
  return { key: "auth.admin.errGeneric", offerCode: false };
}

export function ResetLinkDialog({ user, onClose, onShowCode }: { user: SecurityUser | null; onClose: () => void; onShowCode?: (id: number) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LinkError | null>(null);
  const masked = user?.email ? maskIdentifier(user.email) : "";
  const close = () => (setError(null), onClose());
  const send = async () => {
    if (!user || busy) return;
    setBusy(true);
    setError(null);
    try {
      await authSecurity.adminResetLink(user.id);
      toast.success(t("auth.admin.linkDone", { masked }));
      close();
    } catch (e) {
      setError(linkError(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={user !== null} onOpenChange={(o) => (!o ? close() : undefined)}>
      <DialogContent data-testid="reset-link-dialog">
        <DialogHeader>
          <DialogTitle>{t("auth.admin.linkTitle", { name: user?.name ?? "" })}</DialogTitle>
          <DialogDescription>{rich(t("auth.admin.linkBody"), { masked })}</DialogDescription>
        </DialogHeader>
        {error ? (
          <Alert tone={error.offerCode ? "warning" : "error"} data-testid="reset-link-error">
            <span className="flex flex-col gap-2">
              {t(error.key, error.vars)}
              {error.offerCode && onShowCode && user ? (
                <Button type="button" variant="secondary" shape="rect" className="self-start" onClick={() => (close(), onShowCode(user.id))} data-testid="reset-link-show-code">
                  {t("auth.admin.showCodeAction")}
                </Button>
              ) : null}
            </span>
          </Alert>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="secondary" shape="rect" onClick={close}>
            {t("auth.admin.cancel")}
          </Button>
          <BusyButton type="button" shape="rect" busy={busy} busyLabel={t("busy.working")} onClick={() => void send()} data-testid="reset-link-send">
            {t("auth.admin.linkSend")}
          </BusyButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EndSessionsDialog({ user, onClose }: { user: SecurityUser | null; onClose: () => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const close = () => (setError(null), onClose());
  const run = async () => {
    if (!user || busy) return;
    setBusy(true);
    setError(null);
    try {
      const out = await authSecurity.adminEndSessions(user.id);
      toast.success(t("auth.admin.endSessionsDone", { name: user.name, n: out.revoked }));
      close();
    } catch (e) {
      setError(e instanceof HttpError && e.status === 403 ? "auth.admin.err403" : "auth.admin.errGeneric");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={user !== null} onOpenChange={(o) => (!o ? close() : undefined)}>
      <DialogContent role="alertdialog" data-testid="end-sessions-dialog">
        <DialogHeader>
          <DialogTitle>{t("auth.admin.endSessionsTitle", { name: user?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("auth.admin.endSessionsBody", { name: user?.name ?? "" })}</DialogDescription>
        </DialogHeader>
        {error ? <Alert tone="error">{t(error)}</Alert> : null}
        <DialogFooter>
          <Button type="button" variant="secondary" shape="rect" onClick={close}>
            {t("auth.admin.cancel")}
          </Button>
          <BusyButton type="button" variant="destructive" shape="rect" busy={busy} busyLabel={t("busy.working")} onClick={() => void run()} data-testid="end-sessions-confirm">
            {t("auth.admin.endSessions")}
          </BusyButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
