"use client";
/**
 * Users › Microsoft sign-in parts (docs/design/v2/sign-in.md §12–§13): the status "dot + word" and sign-in method
 * columns, the "Kendi kaydı" / "Acil durum hesabı" tags, the break-glass warning, the invite sheet (only roles the
 * inviter may grant), "Sonraki Microsoft girişinde bağla" (with an extra confirmation for privileged accounts, never
 * yourself), the edit dialog's "Kimlikler" section and the instructor link (flow F-05).
 *
 * Data: `GET /auth/sso/admin/user-status` + `GET /auth/sso/admin/invites`, joined to the user list client-side
 * (§14). Errors are `{detail: {code, en, tr}}`.
 *
 * Motion (§10): the invite sheet is the Sheet primitive (pattern 4: springs.sheet, exit 120 ms; reduced motion
 * opacity); "invite created" is a toast with "Bağlantıyı kopyala" — no row insert animation (the list has > 40 rows).
 */
import { Copy, Link2, Lock, Mail, RefreshCcw, Trash2, Unlink, UserCheck, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { MicrosoftLogo } from "@/components/auth/microsoft-sign-in";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusDot } from "@/components/ui/data-table";
import { DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { useDepartments, useRoles, type AdminUser } from "@/lib/api/crbs";
import { roleValueFor, type InvitePrefill } from "@/lib/handover";
import { apiProblem, identity, identityKeys, useIdentityMutation, useInstructorSearch, type Invite, type InviteIn, type PublicAuth, type UserIdentityStatus } from "@/lib/api/identity";
import { useI18n } from "@/lib/i18n/provider";
import { roleDescription, roleLabel } from "@/lib/i18n/roles";
import { useFinePointer } from "@/lib/motion";
import { isPrivilegedRole, roleGrantCheck, usePermissions } from "@/lib/permissions";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { ConfirmDialog, Field, SelectField } from "./kit";
import { cleanInviteEmail, methodView, selfSignupRecent, type MethodView, type StatusView } from "./users-admin-identity-model";

const IDENTITY_KEYS = [identityKeys.userStatus, identityKeys.invites, ["crbs", "users"]];

export function copyText(text: string, done: string, failed: string) {
  void (navigator.clipboard?.writeText(text) ?? Promise.reject(new Error("no clipboard"))).then(
    () => toast.success(done),
    () => toast.error(failed),
  );
}

/* --------------------------------------------------------------------------------------------- cells */

export function IdentityStatusCell({ view, inviterName }: { view: StatusView; inviterName?: string | null }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const sub =
    view.word === "invited"
      ? [view.daysLeft !== null ? t("sso.users.daysLeft", { n: view.daysLeft }) : null, inviterName].filter(Boolean).join(" · ")
      : view.word === "binding"
        ? t("sso.users.bindingSub")
        : view.word === "inviteExpired" && view.expiredAt
          ? t("sso.users.expiredOn", { date: fmt.short(view.expiredAt.slice(0, 10)) || view.expiredAt.slice(0, 10) })
          : null;
  return (
    <span className="flex flex-col" data-testid="identity-status" data-status={view.word}>
      <StatusDot tone={view.tone}>{t(`sso.users.status.${view.word}`)}</StatusDot>
      {sub ? <span className="pl-4 type-footnote text-label-3">{sub}</span> : null}
    </span>
  );
}

export function MethodCell({ m }: { m: MethodView }) {
  const { t } = useI18n();
  if (m === "none") return <span className="text-label-3">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5 text-label-1" data-testid="identity-method" data-method={m}>
      {m === "microsoft" || m === "microsoftInvite" ? <MicrosoftLogo size={12} /> : m === "binding" ? <Link2 className="size-3.5 text-label-2" aria-hidden /> : null}
      {t(`sso.users.method.${m}`)}
    </span>
  );
}

export function IdentityTags({ s }: { s: UserIdentityStatus | undefined }) {
  const { t } = useI18n();
  return (
    <>
      {selfSignupRecent(s) ? (
        <Badge variant="secondary" className="ml-2" data-testid="tag-self-signup">
          {t("sso.users.tagSelf")}
        </Badge>
      ) : null}
      {s?.break_glass ? (
        <Badge variant="secondary" tone="tint" className="ml-2" data-testid="tag-break-glass">
          <Lock className="size-3" aria-hidden />
          {t("sso.users.tagBreakGlass")}
        </Badge>
      ) : null}
    </>
  );
}

export function BreakGlassWarning({ onCreateLocal }: { onCreateLocal: () => void }) {
  const { t } = useI18n();
  return (
    <Alert
      tone="warning"
      title={t("sso.users.breakGlassTitle")}
      data-testid="break-glass-warning"
      action={
        <Button className="pointer-coarse:h-11" size="sm" variant="secondary" onClick={onCreateLocal}>
          {t("sso.users.createLocal")}
        </Button>
      }
    >
      {t("sso.users.breakGlassBody")}
    </Alert>
  );
}

/* ----------------------------------------------------------------------------------------- row menu */

/** The identity actions of a row (§13 "Row menu by state"). */
export function IdentityMenuItems({ user, s, invite, canManage, msEnabled, onBind, onRevoke }: { user: AdminUser; s: UserIdentityStatus | undefined; invite: Invite | undefined; canManage: boolean; msEnabled: boolean; onBind: (u: AdminUser) => void; onRevoke: (inv: Invite, kind: "invite" | "bind") => void }) {
  const { t, locale } = useI18n();
  const renew = useIdentityMutation((id: number) => identity.renewInvite(id), IDENTITY_KEYS);
  const items: ReactNode[] = [];
  const status = s?.status ?? "none";
  if ((status === "invited" || status === "invite_expired") && invite) {
    if (status === "invited" && invite.link)
      items.push(
        <DropdownMenuItem key="copy" onClick={() => copyText(invite.link ?? "", t("sso.users.linkCopied"), t("sso.users.copyFailed"))} data-testid={`invite-copy-${user.id}`}>
          <Copy aria-hidden />
          {t("sso.users.copyLink")}
        </DropdownMenuItem>,
      );
    items.push(
      <DropdownMenuItem
        key="renew"
        disabled={!canManage}
        onClick={() =>
          renew.mutate(invite.id, {
            onSuccess: (out) => {
              toast.success(t("sso.users.renewed"), out.link ? { action: { label: t("sso.users.copyLink"), onClick: () => copyText(out.link ?? "", t("sso.users.linkCopied"), t("sso.users.copyFailed")) } } : undefined);
            },
            onError: (e) => toast.error(apiProblem(e, locale).text ?? t("sso.users.failed")),
          })
        }
        data-testid={`invite-renew-${user.id}`}
      >
        <RefreshCcw aria-hidden />
        {t("sso.users.renew")}
      </DropdownMenuItem>,
      <DropdownMenuItem key="revoke" variant="destructive" disabled={!canManage} onClick={() => onRevoke(invite, "invite")} data-testid={`invite-revoke-${user.id}`}>
        <XCircle aria-hidden />
        {status === "invited" ? t("sso.users.revoke") : t("sso.users.deleteInvite")}
      </DropdownMenuItem>,
    );
  } else if (status === "binding" && invite) {
    items.push(
      <DropdownMenuItem key="unbind" disabled={!canManage} onClick={() => onRevoke(invite, "bind")} data-testid={`bind-cancel-${user.id}`}>
        <XCircle aria-hidden />
        {t("sso.users.cancelBind")}
      </DropdownMenuItem>,
    );
  } else if (status === "none" && msEnabled && user.is_active) {
    items.push(
      <DropdownMenuItem key="bind" disabled={!canManage} onClick={() => onBind(user)} data-testid={`bind-${user.id}`}>
        <Link2 aria-hidden />
        {t("sso.users.bindNext")}
      </DropdownMenuItem>,
    );
  }
  if (!items.length) return null;
  return (
    <>
      <DropdownMenuSeparator />
      {items}
    </>
  );
}

/** Revoke an invite / cancel a scheduled binding (the account stays). */
export function RevokeDialog({ value, onClose }: { value: { invite: Invite; kind: "invite" | "bind" } | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const del = useIdentityMutation((id: number) => identity.deleteInvite(id), IDENTITY_KEYS);
  return (
    <ConfirmDialog
      open={!!value}
      onOpenChange={(o) => !o && onClose()}
      title={value?.kind === "bind" ? t("sso.users.cancelBindTitle") : t("sso.users.revokeTitle", { email: value?.invite.email ?? "" })}
      description={value?.kind === "bind" ? t("sso.users.cancelBindBody") : t("sso.users.revokeBody")}
      confirmLabel={value?.kind === "bind" ? t("sso.users.cancelBind") : t("sso.users.revoke")}
      destructive={value?.kind !== "bind"}
      busy={del.isPending}
      onConfirm={() =>
        value &&
        del.mutate(value.invite.id, {
          onSuccess: () => {
            toast.success(value.kind === "bind" ? t("sso.users.bindCancelled") : t("sso.users.revoked"));
            onClose();
          },
          onError: (e) => toast.error(apiProblem(e, locale).text ?? t("sso.users.failed")),
        })
      }
    />
  );
}

/* ------------------------------------------------------------------------------------- bind confirm */

/**
 * "Sonraki Microsoft girişinde bağla": the next Microsoft sign-in whose verified address equals `email` binds to
 * this account. Privileged accounts (admin role, approver scope, a role that grants setup.roles) need a second,
 * explicit confirmation that names the risk; your own account is refused (the Profile route proves both sides).
 */
export function BindDialog({ user, privileged, onClose }: { user: AdminUser | null; privileged: boolean; onClose: () => void }) {
  const { t, locale } = useI18n();
  const { userId } = usePermissions();
  const [email, setEmail] = useState(user?.email ?? "");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ackId = useId();
  const bind = useIdentityMutation((v: { id: number; email: string }) => identity.bind(v.id, { email: v.email || null }), IDENTITY_KEYS);
  const self = !!user && user.id === userId;
  return (
    <ConfirmDialog
      open={!!user}
      onOpenChange={(o) => !o && onClose()}
      title={t("sso.users.bindTitle", { name: user?.displayname || user?.full_name || user?.username || user?.email || "" })}
      description={t("sso.users.bindBody")}
      confirmLabel={t("sso.users.bindConfirm")}
      busy={bind.isPending}
      onConfirm={() => {
        if (!user || self || (privileged && !ack)) return;
        setError(null);
        bind.mutate(
          { id: user.id, email: email.trim() },
          {
            onSuccess: () => {
              toast.success(t("sso.users.bindScheduled"));
              onClose();
            },
            onError: (e) => {
              const p = apiProblem(e, locale);
              setError(p.code === "self" ? t("sso.users.bindSelf") : (p.text ?? t("sso.users.failed")));
            },
          },
        );
      }}
    >
      <div className="flex flex-col gap-3" data-testid="bind-dialog">
        {self ? (
          <Alert tone="warning">
            {t("sso.users.bindSelf")}{" "}
            <Link href="/profile#microsoft" className="font-medium underline">
              {t("sso.users.goProfile")}
            </Link>
          </Alert>
        ) : null}
        <Field label={t("sso.users.bindEmail")} htmlFor="bind-email" hint={t("sso.users.bindEmailHint")}>
          <Input id="bind-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="bind-email" />
        </Field>
        {privileged && !self ? (
          <div className="flex flex-col gap-2 rounded-xl bg-status-warning px-3 py-2.5 text-status-warning-fg" data-testid="bind-privileged">
            <p className="type-callout font-semibold">{t("sso.users.bindPrivilegedTitle")}</p>
            <p className="type-footnote">{t("sso.users.bindPrivilegedBody")}</p>
            <label htmlFor={ackId} className="flex items-start gap-2 type-footnote">
              <Checkbox id={ackId} checked={ack} onCheckedChange={(v) => setAck(v === true)} className="mt-0.5" data-testid="bind-privileged-ack" />
              <span>{t("sso.users.bindPrivilegedAck")}</span>
            </label>
          </div>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
    </ConfirmDialog>
  );
}

/* --------------------------------------------------------------------------------------- invite sheet */

const SEEDED = [
  { code: "TEACHER", key: "crbs.users.roleTeacher" },
  { code: "VIEWER", key: "crbs.users.roleViewer" },
  { code: "PLANNER", key: "crbs.users.rolePlanner" },
  { code: "ADMIN", key: "crbs.users.roleAdmin" },
] as const;

export function InviteSheet({ open, onOpenChange, auth, canListRoles, prefill = null, local = false }: { open: boolean; onOpenChange: (o: boolean) => void; auth: PublicAuth | undefined; canListRoles: boolean; /** HX-06 `?invite=1&…`: the fields it opens with (sent only by "Davet et") */ prefill?: InvitePrefill | null; /** E2EA-F10: password sign-in only, the link lets the person set a password (`provider: "local"`) */ local?: boolean }) {
  const fine = useFinePointer();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* also opened by the `?invite=1` hand-over (no trigger was pressed): focus goes to "Davet et" on close */}
      <SheetContent side={fine ? "right" : "bottom"} className="flex flex-col gap-0 overflow-y-auto sm:max-w-md" finalFocus={() => document.querySelector<HTMLElement>('[data-testid="users-invite"]') ?? true} data-testid="invite-sheet">
        {open ? <InviteForm onDone={() => onOpenChange(false)} domainHint={local ? null : (auth?.microsoft.domain_hint ?? null)} canListRoles={canListRoles} prefill={prefill} local={local} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function InviteForm({ onDone, domainHint, canListRoles, prefill, local }: { onDone: () => void; domainHint: string | null; canListRoles: boolean; prefill: InvitePrefill | null; local: boolean }) {
  const { t, locale } = useI18n();
  const { perms } = usePermissions();
  const roles = useRoles(canListRoles);
  const departments = useDepartments();
  const [email, setEmail] = useState(prefill?.email ?? "");
  const [name, setName] = useState(prefill?.name ?? "");
  const [role, setRole] = useState("");
  const [dept, setDept] = useState(prefill?.department ?? "");
  const [error, setError] = useState<{ text: string; code: string | null } | null>(null);
  // RF-03: the invitation e-mail is on by default when SMTP is set up (/admin/email); without SMTP the switch
  // stays off and says so, with a link to set it up
  const mail = useQuery({ queryKey: identityKeys.inviteMail, queryFn: identity.inviteMail, retry: false, staleTime: 60_000 });
  const mailReady = mail.data?.configured === true;
  const [sendChoice, setSendChoice] = useState<boolean | null>(null);
  const sendMail = mailReady && (sendChoice ?? true);
  const create = useIdentityMutation((body: InviteIn) => identity.createInvite(body), IDENTITY_KEYS);
  const renewPending = useIdentityMutation((id: number) => identity.renewInvite(id), IDENTITY_KEYS);
  const cleaned = cleanInviteEmail(email, domainHint);
  // only roles the inviter may grant (no escalation): the backend refuses the rest with 403
  const options = roles.data
    ? roles.data
        .filter((r) => roleGrantCheck(perms, r).allowed)
        .map((r) => {
          const label = roleLabel(t, r);
          const summary = roleDescription(t, r);
          return { value: `id:${r.id}`, label, summary: summary && summary !== label ? summary : null, privileged: isPrivilegedRole(r) };
        })
    : SEEDED.filter((r) => roleGrantCheck(perms, { code: r.code }).allowed).map((r) => ({ value: `code:${r.code}`, label: t(r.key), summary: null, privileged: r.code === "ADMIN" }));
  const groupName = useId();
  // the hand-over's role, once the options are known, and only one the inviter may grant
  const wantRole = prefill?.role ? roleValueFor(prefill.role, roles.data ? roles.data : undefined) : "";
  const roleReady = !canListRoles || !!roles.data;
  const [rolePrefilled, setRolePrefilled] = useState(false);
  if (!rolePrefilled && roleReady && wantRole) {
    setRolePrefilled(true);
    if (!role && options.some((o) => o.value === wantRole)) setRole(wantRole);
  }
  const submit = () => {
    setError(null);
    if (!cleaned.valid) return setError({ text: t("sso.users.invite.badEmail"), code: null });
    if (!role) return setError({ text: t("sso.users.invite.needRole"), code: null });
    const body: InviteIn = { email: cleaned.email, full_name: name.trim() || null, department_id: dept ? Number(dept) : null, ...(role.startsWith("id:") ? { role_id: Number(role.slice(3)) } : { role: role.slice(5) }), send_email: sendMail, locale: locale === "en" ? "en" : "tr", ...(local ? { provider: "local" } : {}) };
    create.mutate(body, {
      onSuccess: (inv) => {
        const copy = inv.link ? { action: { label: t("sso.users.copyLink"), onClick: () => copyText(inv.link ?? "", t("sso.users.linkCopied"), t("sso.users.copyFailed")) } } : undefined;
        if (sendMail && inv.email_status === "SENT") toast.success(t("sso.users.invite.mailed", { email: inv.email }), copy);
        else if (sendMail) toast.warning(t("sso.users.invite.mailFailed"), copy);
        else toast.success(t("sso.users.invite.sent", { email: inv.email }), copy);
        onDone();
      },
      onError: (e) => {
        const p = apiProblem(e, locale);
        const text =
          p.code === "invite_pending"
            ? t("sso.users.invite.pending")
            : p.code === "account_bound"
              ? t("sso.users.invite.bound")
              : p.code === "account_exists"
                ? t("sso.users.invite.exists")
                : (p.text ?? t("sso.users.failed"));
        setError({ text, code: p.code });
      },
    });
  };
  return (
    <form
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <SheetHeader className="pr-12">
        <SheetTitle>{t("sso.users.invite.title")}</SheetTitle>
        <SheetDescription>{t(local ? "sso.users.invite.leadLocal" : "sso.users.invite.lead")}</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-4 px-4 pb-4">
        <Field label={t("sso.users.invite.email")} htmlFor="invite-email" hint={cleaned.domainMismatch || local ? undefined : domainHint ? t("sso.users.invite.emailHint", { domain: domainHint }) : t("sso.users.invite.emailHintPlain")}>
          <Input id="invite-email" type="email" inputMode="email" autoComplete="off" autoCapitalize="none" spellCheck={false} required value={email} onChange={(e) => setEmail(e.target.value)} onBlur={() => cleaned.valid && setEmail(cleaned.email)} data-testid="invite-email" />
        </Field>
        {cleaned.domainMismatch ? (
          <p className="-mt-2 type-footnote text-status-warning-fg" data-testid="invite-domain-warning">
            {t("sso.users.invite.otherDomain")}
          </p>
        ) : null}
        <Field label={t("sso.users.invite.name")} htmlFor="invite-name">
          <Input id="invite-name" value={name} placeholder={t("sso.users.invite.namePlaceholder")} onChange={(e) => setName(e.target.value)} data-testid="invite-name" />
        </Field>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1.5 type-footnote font-medium text-label-2">{t("sso.users.invite.role")}</legend>
          {options.map((o) => (
            <label key={o.value} className="flex cursor-pointer items-start gap-3 rounded-xl bg-(--mat-thick) px-3 py-2.5 edge-hairline has-checked:bg-tint-soft has-checked:edge-tint has-focus-visible:outline-2 has-focus-visible:outline-solid has-focus-visible:outline-(--focus)">
              <input type="radio" name={groupName} value={o.value} checked={role === o.value} onChange={() => setRole(o.value)} className="mt-1 accent-(--accent)" data-testid={`invite-role-${o.value}`} />
              <span className="min-w-0">
                <span className="block type-callout font-semibold text-label-1">{o.label}</span>
                {o.summary || o.privileged ? <span className="block type-footnote text-label-2">{[o.summary, o.privileged ? t("sso.users.invite.audited") : null].filter(Boolean).join(" ")}</span> : null}
              </span>
            </label>
          ))}
        </fieldset>
        <Field label={t("sso.users.invite.department")} htmlFor="invite-dept">
          <SelectField id="invite-dept" value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">{t("crbs.book.departmentNone")}</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </SelectField>
        </Field>
        <div className="flex items-start justify-between gap-3">
          <span className="min-w-0">
            <span className="block type-callout font-semibold text-label-1">{t("sso.users.invite.sendMail")}</span>
            <span className="block type-footnote text-label-2" id={`${groupName}-mail`} data-testid="invite-mail-hint">
              {/* while GET /invite-mail is pending the sheet does not claim "E-posta ayarlanmadı" (e2e 2026-10-18) */}
              {mail.isPending ? t("busy.checking") : mailReady ? (sendMail ? t("sso.users.invite.sendMailOn") : t("sso.users.invite.sendMailSkip")) : t("sso.users.invite.sendMailOff")}
            </span>
            {mail.isSuccess && !mailReady ? (
              <Link href="/admin/email" className="mt-1 inline-flex min-h-11 items-center type-footnote font-medium text-tint-text underline-offset-2 hover:underline sm:min-h-0" data-testid="invite-mail-setup">
                {t("sso.users.invite.mailSetup")}
              </Link>
            ) : null}
          </span>
          <Switch checked={sendMail} disabled={!mailReady} onCheckedChange={(v) => setSendChoice(!!v)} aria-label={t("sso.users.invite.sendMail")} aria-describedby={`${groupName}-mail`} data-testid="invite-send-mail" />
        </div>
        <Alert tone="info">{cleaned.valid ? t("sso.users.invite.bindNote", { email: cleaned.email }) : t("sso.users.invite.bindNotePlain")}</Alert>
        {error ? (
          <Alert
            tone="error"
            action={
              error.code === "invite_pending" ? (
                <Button className="pointer-coarse:h-11"
                  size="sm"
                  variant="secondary"
                  type="button"
                  onClick={async () => {
                    const list = await identity.invites().catch(() => []);
                    const pending = list.find((i) => i.email === cleaned.email);
                    if (pending)
                      renewPending.mutate(pending.id, {
                        onSuccess: () => {
                          toast.success(t("sso.users.renewed"));
                          onDone();
                        },
                      });
                  }}
                >
                  {t("sso.users.renew")}
                </Button>
              ) : null
            }
          >
            {error.text}
          </Alert>
        ) : null}
      </div>
      <SheetFooter className="mt-auto flex-row justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("crbs.common.cancel")}
        </Button>
        <BusyButton type="submit" busy={create.isPending} busyLabel={t("busy.working")} data-testid="invite-submit">
          <Mail aria-hidden />
          {t("sso.users.invite.submit")}
        </BusyButton>
      </SheetFooter>
    </form>
  );
}

/* ------------------------------------------------------------------------------- edit dialog sections */

/** Düzenle › Kimlikler: the Microsoft identity of the account, unlink / schedule a binding. */
export function IdentitiesSection({ user, s, invite, msEnabled, onBind }: { user: AdminUser; s: UserIdentityStatus | undefined; invite: Invite | undefined; msEnabled: boolean; onBind: () => void }) {
  const { t, locale } = useI18n();
  const [unlinking, setUnlinking] = useState(false);
  const [revoke, setRevoke] = useState<{ invite: Invite; kind: "invite" | "bind" } | null>(null);
  const unlink = useIdentityMutation(() => identity.unlinkUser(user.id), IDENTITY_KEYS);
  const m = methodView(s, user.auth_source);
  const linked = s?.auth_methods.includes("microsoft") ?? false;
  return (
    <section aria-labelledby={`ids-${user.id}`} className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3 edge-hairline" data-testid="user-identities">
      <h3 id={`ids-${user.id}`} className="type-headline text-label-1">
        {t("sso.users.identities")}
      </h3>
      {linked ? (
        <div className="flex flex-wrap items-center gap-3">
          <MicrosoftLogo size={16} />
          <span className="min-w-0 flex-1">
            <span className="block type-callout font-medium text-label-1">{t("sso.users.msAccount")}</span>
            <span className="block type-footnote text-label-2">{user.email ?? "—"}</span>
          </span>
          <Button className="pointer-coarse:h-11" type="button" size="sm" variant="destructive" onClick={() => setUnlinking(true)} data-testid="identity-unlink">
            <Unlink aria-hidden />
            {t("sso.users.unlink")}
          </Button>
        </div>
      ) : m === "binding" && invite ? (
        <div className="flex flex-wrap items-center gap-3">
          <Link2 className="size-4 text-label-2" aria-hidden />
          <span className="min-w-0 flex-1 type-callout text-label-1">{t("sso.users.bindingSub")}</span>
          <Button className="pointer-coarse:h-11" type="button" size="sm" variant="ghost" onClick={() => setRevoke({ invite, kind: "bind" })}>
            {t("sso.users.cancelBind")}
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="min-w-0 flex-1 type-callout text-label-2">{t(`sso.users.method.${m}`)}</span>
          {msEnabled && user.is_active && s?.status === "none" ? (
            <Button className="pointer-coarse:h-11" type="button" size="sm" variant="outline" onClick={onBind} data-testid="identity-bind">
              <Link2 aria-hidden />
              {t("sso.users.bindNext")}
            </Button>
          ) : null}
        </div>
      )}
      <InstructorLink user={user} s={s} />
      <ConfirmDialog
        open={unlinking}
        onOpenChange={setUnlinking}
        title={t("sso.users.unlinkTitle")}
        description={t("sso.users.unlinkBody")}
        confirmLabel={t("sso.users.unlink")}
        destructive
        busy={unlink.isPending}
        onConfirm={() =>
          unlink.mutate(undefined, {
            onSuccess: () => {
              toast.success(t("sso.users.unlinked"));
              setUnlinking(false);
            },
            onError: (e) => toast.error(apiProblem(e, locale).text ?? t("sso.users.failed")),
          })
        }
      />
      <RevokeDialog value={revoke} onClose={() => setRevoke(null)} />
    </section>
  );
}

/** Flow F-05: the account ↔ instructor record link (`PUT /auth/sso/admin/users/{id}/instructor`). */
function InstructorLink({ user, s }: { user: AdminUser; s: UserIdentityStatus | undefined }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);
  const canSearch = can("planning.view");
  const results = useInstructorSearch(query.trim(), editing && canSearch);
  // the backend has no "instructor by id": one page of 500 (cached) resolves the linked name
  const current = useInstructorSearch("", !!s?.instructor_id && canSearch, 500);
  const save = useIdentityMutation((id: number | null) => identity.setInstructor(user.id, id), IDENTITY_KEYS);
  const linkedId = s?.instructor_id ?? null;
  const linkedName = linkedId ? (current.data?.items.find((i) => i.id === linkedId)?.full_name ?? t("sso.users.instructorNumber", { id: linkedId })) : null;
  const listId = useId();
  const apply = (id: number | null) =>
    save.mutate(id, {
      onSuccess: () => {
        toast.success(id ? t("sso.users.instructorLinked") : t("sso.users.instructorCleared"));
        setEditing(false);
        setQuery("");
      },
      onError: (e) => toast.error(apiProblem(e, locale).text ?? t("sso.users.failed")),
    });
  return (
    <div className="flex flex-col gap-2 pt-2 hairline-t" data-testid="user-instructor">
      <div className="flex flex-wrap items-center gap-3">
        <UserCheck className="size-4 text-label-2" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block type-callout font-medium text-label-1">{t("sso.users.instructor")}</span>
          <span className="block type-footnote text-label-2">{linkedName ?? t("sso.users.instructorNone")}</span>
        </span>
        {!editing && canSearch ? (
          <Button className="pointer-coarse:h-11" type="button" size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="instructor-edit">
            {linkedId ? t("sso.users.instructorChange") : t("sso.users.instructorLink")}
          </Button>
        ) : null}
        {linkedId && !editing ? (
          <Button className="pointer-coarse:h-11" type="button" size="sm" variant="ghost" onClick={() => apply(null)} aria-label={t("sso.users.instructorClear")}>
            <Trash2 aria-hidden />
          </Button>
        ) : null}
      </div>
      {editing ? (
        <div className="flex flex-col gap-2">
          <Input type="search" aria-label={t("sso.users.instructorSearch")} placeholder={t("sso.users.instructorSearch")} value={query} onChange={(e) => setQuery(e.target.value)} aria-controls={listId} data-testid="instructor-search" />
          <ul id={listId} className="flex max-h-48 flex-col overflow-y-auto rounded-lg edge-hairline">
            {(results.data?.items ?? []).map((i) => (
              <li key={i.id}>
                <Button type="button" variant="ghost" shape="rect" className="w-full justify-start" onClick={() => apply(i.id)} data-testid={`instructor-pick-${i.id}`}>
                  {[i.title, i.full_name].filter(Boolean).join(" ")}
                </Button>
              </li>
            ))}
            {results.data && !results.data.items.length ? <li className="px-3 py-2 type-footnote text-label-3">{t("sso.users.instructorNoHits")}</li> : null}
          </ul>
          <Button type="button" size="sm" variant="ghost" className="self-start pointer-coarse:h-11" onClick={() => setEditing(false)}>
            {t("crbs.common.cancel")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
