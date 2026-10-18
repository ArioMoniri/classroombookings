"use client";
/**
 * "Geçiş anahtarları" (docs/design/v3/auth.md §6.2, §6.4; AUX-07). A `<ul>` of rows: a key glyph, the name (from the
 * AAGUID when it was added here, else "{browser} · {os}"), "Eklendi {date} · Son kullanım {relative}" or "Hiç
 * kullanılmadı", the tag "Yalnızca bu cihazda" when not backed up, and a ⋯ menu ("{name} için işlemler": "Yeniden
 * adlandır" inline, Enter saves, Escape cancels, focus back on the ⋯; "Kaldır" after a dialog). Adding: re-auth (only
 * when the sign-in is older than 10 min) → `create()` → the new row with its name editable at once + toast; the
 * first factor also returns the recovery codes. Errors: NotAllowedError neutral, InvalidStateError "zaten var", limit
 * 10. Rows enter and leave with a short fade + 4 px (pattern 6; reduced motion: fade only).
 */
import { Ellipsis, KeyRound } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { createPasskey, passkeyErrorKey, passkeyErrorKind } from "@/components/auth/passkey";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { authSecurity, mfaErrorCode, mfaErrorText, type MfaStatus, type PasskeyRow } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { defaultPasskeyName } from "./aaguid";
import { relative, shortDate } from "./format";
import { SecurityRow } from "./mfa-row";
import { RecoveryCodes } from "./recovery-codes";
import { ReauthCancelled, useReauth } from "./reauth-dialog";
import "@/components/auth/auth.css";

export const MAX_PASSKEYS = 10;

export function PasskeysRow({ status, org, onChanged }: { status: MfaStatus; org?: string | null; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const { run, dialog } = useReauth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<number | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [removing, setRemoving] = useState<PasskeyRow | null>(null);
  const list = status.passkeys;
  const isLastFactor = list.length === 1 && !status.totp.enabled;

  if (!status.passkeys_available) {
    return <SecurityRow title={t("auth.security.passkeys")} status={status.policy.passkeys_enabled ? t("auth.passkey.unavailable") : t("auth.security.passkeysOff")} testId="security-passkeys" />;
  }

  const add = async () => {
    if (list.length >= MAX_PASSKEYS) return setError(t("auth.passkey.addLimit"));
    setBusy(true);
    setError(null);
    try {
      const o = await run((pw) => authSecurity.registerOptions(pw));
      const made = await createPasskey(o.options);
      const out = await authSecurity.registerVerify(o.challenge_token ?? "", made.credential, defaultPasskeyName(made.aaguid, locale));
      toast.success(t("auth.security.passkeyAdded"));
      setFresh(out.passkey.id);
      if (out.recovery_codes?.length) setCodes(out.recovery_codes);
      onChanged();
    } catch (e) {
      if (e instanceof ReauthCancelled) return;
      const code = mfaErrorCode(e);
      if (code === "passkey_limit") setError(t("auth.passkey.addLimit"));
      else if (code === "passkey_exists") setError(t("auth.passkey.addExists"));
      else if (code) setError(mfaErrorText(e, locale) ?? t("auth.passkey.addFailed"));
      else setError(t(passkeyErrorKey(passkeyErrorKind(e), "add")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SecurityRow
      title={t("auth.security.passkeys")}
      status={
        list.length ? null : (
          <div className="flex flex-col gap-1">
            <p>{t("auth.security.passkeysNone")}</p>
            <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-5 type-footnote">
              <li>{t("auth.security.passkeysBenefit1")}</li>
              <li>{t("auth.security.passkeysBenefit2")}</li>
            </ul>
          </div>
        )
      }
      action={
        <BusyButton type="button" variant="secondary" shape="rect" busy={busy} busyLabel={t("auth.passkey.busy")} icon={<KeyRound aria-hidden />} onClick={() => void add()} data-testid="passkey-add">
          {t("auth.security.addPasskey")}
        </BusyButton>
      }
      testId="security-passkeys"
    >
      {dialog}
      {error ? (
        <Alert tone="neutral" data-testid="passkey-add-error">
          {error}
        </Alert>
      ) : null}
      {list.length ? (
        <ul className="flex flex-col divide-y divide-(--hairline) rounded-xl bg-fill-3" data-testid="passkey-list">
          {list.map((p) => (
            <PasskeyItem key={p.id} p={p} fresh={fresh === p.id} onRenamed={() => (setFresh(null), onChanged())} onRemove={() => setRemoving(p)} />
          ))}
        </ul>
      ) : null}
      <RemoveDialog p={removing} lastFactor={isLastFactor} run={run} onClose={() => setRemoving(null)} onRemoved={onChanged} />
      <Dialog open={codes !== null} onOpenChange={(o) => (!o ? setCodes(null) : undefined)}>
        <DialogContent data-testid="passkey-codes-dialog">
          <DialogHeader>
            <DialogTitle>{t("auth.setup.step3")}</DialogTitle>
          </DialogHeader>
          {codes ? <RecoveryCodes codes={codes} org={org} account="" onFinish={() => setCodes(null)} /> : null}
        </DialogContent>
      </Dialog>
    </SecurityRow>
  );
}

function PasskeyItem({ p, fresh, onRenamed, onRemove }: { p: PasskeyRow; fresh: boolean; onRenamed: () => void; onRemove: () => void }) {
  const { t, locale } = useI18n();
  const [editing, setEditing] = useState(fresh);
  const [name, setName] = useState(p.name);
  const [saving, setSaving] = useState(false);
  const menuRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const labelId = useId();
  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const close = () => {
    setEditing(false);
    setName(p.name);
    requestAnimationFrame(() => menuRef.current?.focus());
  };
  const save = async () => {
    const v = name.trim();
    if (!v || v === p.name) return close();
    setSaving(true);
    try {
      await authSecurity.renamePasskey(p.id, v);
      setEditing(false);
      onRenamed();
      requestAnimationFrame(() => menuRef.current?.focus());
    } catch (e) {
      toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setSaving(false);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void save();
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  };
  const meta = p.last_used_at ? t("auth.security.passkeyMeta", { created: shortDate(p.created_at, locale), used: relative(p.last_used_at, locale) }) : t("auth.security.passkeyNeverUsed", { created: shortDate(p.created_at, locale) });

  return (
    <li className="auth-row-in flex items-center gap-3 px-3 py-2.5" data-testid="passkey-row">
      <KeyRound aria-hidden className="size-6 shrink-0 text-label-2" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {editing ? (
          <div className="flex flex-col gap-1">
            <label id={labelId} htmlFor={`pk-${p.id}`} className="type-footnote text-label-2">
              {fresh ? t("auth.security.renamePrompt") : t("auth.security.renameLabel")}
            </label>
            <div className="flex flex-wrap gap-2">
              <Input ref={inputRef} id={`pk-${p.id}`} value={name} maxLength={64} enterKeyHint="done" autoComplete="off" onChange={(e) => setName(e.target.value)} onKeyDown={onKey} className="min-w-0 flex-1" data-testid="passkey-rename-input" />
              <BusyButton type="button" size="md" shape="rect" busy={saving} busyLabel={t("busy.saving")} onClick={() => void save()} data-testid="passkey-rename-save">
                {t("auth.security.save")}
              </BusyButton>
              <Button type="button" variant="ghost" size="md" shape="rect" onClick={close}>
                {t("auth.security.cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <span className="truncate type-callout font-semibold text-label-1" data-testid="passkey-name">
            {p.name}
          </span>
        )}
        <span className="type-footnote text-label-2" data-testid="passkey-meta">
          {meta}
          {!p.backed_up ? (
            <Badge variant="secondary" className="ml-2 align-middle">
              {t("auth.security.thisDeviceOnly")}
            </Badge>
          ) : null}
        </span>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger render={<IconButton ref={menuRef} label={t("auth.security.actionsFor", { name: p.name })} className="size-11" data-testid="passkey-menu" />}>
          <Ellipsis aria-hidden className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setEditing(true)} data-testid="passkey-rename">
            {t("auth.security.rename")}
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onClick={onRemove} data-testid="passkey-remove">
            {t("auth.security.remove")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}

function RemoveDialog({ p, lastFactor, run, onClose, onRemoved }: { p: PasskeyRow | null; lastFactor: boolean; run: ReturnType<typeof useReauth>["run"]; onClose: () => void; onRemoved: () => void }) {
  const { t, locale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    if (!p) return;
    setBusy(true);
    setError(null);
    try {
      await run((pw) => authSecurity.removePasskey(p.id, pw));
      toast.success(t("auth.security.removed"));
      onClose();
      onRemoved();
    } catch (e) {
      if (!(e instanceof ReauthCancelled)) setError(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={p !== null} onOpenChange={(o) => (!o ? (onClose(), setError(null)) : undefined)}>
      <DialogContent role="alertdialog" data-testid="passkey-remove-dialog">
        <DialogHeader>
          <DialogTitle>{t("auth.security.removeTitle", { name: p?.name ?? "" })}</DialogTitle>
          <DialogDescription>
            {t("auth.security.removeBody")}
            {lastFactor ? ` ${t("auth.security.removeLast")}` : ""}
          </DialogDescription>
        </DialogHeader>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <DialogFooter>
          <Button type="button" variant="secondary" shape="rect" onClick={onClose}>
            {t("auth.security.cancel")}
          </Button>
          <BusyButton type="button" variant="destructive" shape="rect" busy={busy} busyLabel={t("busy.deleting")} onClick={() => void remove()} data-testid="passkey-remove-confirm">
            {t("auth.security.remove")}
          </BusyButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
