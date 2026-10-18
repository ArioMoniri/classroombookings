"use client";
/**
 * "Kimliğinizi doğrulayın" (docs/design/v3/auth.md §6.7, D7; AUX-06). AU-B's protected routes take `password`, and
 * within 10 minutes of signing in the password may be left out (API.md §4 ⓡ). So `run(fn)` first calls `fn()`
 * without a password; only a `reauth_failed` refusal opens this dialog, and the action is retried with the password.
 * A wrong password keeps the dialog open with the error; Escape / "Vazgeç" rejects with `ReauthCancelled`.
 */
import { useCallback, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { mfaErrorCode } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";

export class ReauthCancelled extends Error {
  constructor() {
    super("reauth cancelled");
    this.name = "ReauthCancelled";
  }
}

type Pending = { attempt: (pw: string) => Promise<void>; reject: (e: unknown) => void };

export function useReauth(): { run: <T>(fn: (password?: string) => Promise<T>) => Promise<T>; dialog: ReactNode } {
  const { t } = useI18n();
  const [pending, setPending] = useState<Pending | null>(null);
  const [pw, setPw] = useState("");
  const [wrong, setWrong] = useState(false);
  const [busy, setBusy] = useState(false);
  const ids = { pw: useId(), err: useId(), lead: useId() };
  const inputRef = useRef<HTMLInputElement>(null);

  const run = useCallback(<T,>(fn: (password?: string) => Promise<T>): Promise<T> => {
    return (async () => {
      try {
        return await fn();
      } catch (e) {
        if (mfaErrorCode(e) !== "reauth_failed") throw e;
      }
      return await new Promise<T>((resolve, reject) => {
        setPw("");
        setWrong(false);
        setPending({
          attempt: async (password) => {
            try {
              const out = await fn(password);
              setPending(null);
              resolve(out);
            } catch (e) {
              if (mfaErrorCode(e) === "reauth_failed") {
                setWrong(true);
                setPw("");
                inputRef.current?.focus();
                return;
              }
              setPending(null);
              reject(e);
            }
          },
          reject,
        });
      });
    })();
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pending || !pw || busy) return;
    setBusy(true);
    try {
      await pending.attempt(pw);
    } finally {
      setBusy(false);
    }
  };

  const cancel = () => {
    pending?.reject(new ReauthCancelled());
    setPending(null);
  };

  const dialog = (
    <Dialog open={pending !== null} onOpenChange={(open) => (!open ? cancel() : undefined)}>
      <DialogContent initialFocus={inputRef} data-testid="reauth-dialog">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("auth.reauth.title")}</DialogTitle>
            <DialogDescription id={ids.lead}>{t("auth.reauth.lead")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.pw} className="type-callout font-semibold text-label-1">
              {t("auth.reauth.password")}
            </label>
            <Input ref={inputRef} id={ids.pw} type="password" autoComplete="current-password" fieldSize="lg" value={pw} onChange={(e) => (setPw(e.target.value), setWrong(false))} aria-invalid={wrong || undefined} aria-describedby={wrong ? ids.err : ids.lead} data-testid="reauth-password" />
            {wrong ? (
              <p id={ids.err} className="type-footnote text-status-infeasible-fg" data-testid="reauth-wrong">
                {t("auth.reauth.wrong")}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" shape="rect" onClick={cancel}>
              {t("auth.security.cancel")}
            </Button>
            <BusyButton type="submit" shape="rect" busy={busy} busyLabel={t("auth.mfa.verifying")} disabled={!pw} data-testid="reauth-submit">
              {t("auth.reauth.submit")}
            </BusyButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );

  return { run, dialog };
}
