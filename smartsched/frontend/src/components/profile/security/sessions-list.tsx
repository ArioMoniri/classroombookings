"use client";
/**
 * "Oturumlar ve cihazlar" (docs/design/v3/auth.md §6.5; AUX-07, AU-B API.md §11 / AU-15). Up to 5 open sessions,
 * then "Tümünü göster ({n})"; each row: a device glyph, "{browser} · {os}" with "Bu cihaz" on the current one, and
 * "Son etkinlik {relative}". Other sessions: "Oturumu kapat"; the current one has no action ("Çıkış yap" stays in the
 * account menu). Then the remembered devices, and the footer "Diğer tüm oturumları kapat", which confirms first
 * ("Bu cihaz dışındaki tüm oturumlar kapatılır ve hatırlanan cihazlar unutulur.") and also forgets the remembered
 * devices. No IP address or network is shown (KVKK, Simplicity), though the API carries a /24.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Monitor, Smartphone } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { authSecurity, authSecurityKeys, mfaErrorText, useSessions, type SessionRow, type TrustedDevice } from "@/lib/api/auth-security";
import { useI18n } from "@/lib/i18n/provider";
import { relative } from "./format";
import { SecurityRow } from "./mfa-row";
import { RememberedDevices } from "./trusted-devices";
import "@/components/auth/auth.css";

export const SESSIONS_VISIBLE = 5;

const isPhone = (device: string | null | undefined) => /iPhone|iPad|Android|iOS/i.test(device ?? "");

/** "{browser} · {os}" in the viewer's language (FIX-I): unknown parts are worded here, never taken from the stored
 * label (older rows were stored in Turkish); a token used only by a script reads "Betik ya da API istemcisi". */
export function sessionLabel(s: Pick<SessionRow, "device" | "browser" | "os" | "client">, t: ReturnType<typeof useI18n>["t"]): string {
  if (s.client === "api") return t("auth.security.apiClient");
  if (s.client === undefined || s.client === null) return s.device || t("auth.security.unknownDevice");
  if (!s.browser && !s.os) return t("auth.security.unknownDevice");
  return t("auth.security.deviceLabel", { browser: s.browser || t("auth.security.unknownBrowser"), os: s.os || t("auth.security.unknownSystem") });
}

/** The current session first, then the newest activity. */
export function orderSessions(list: readonly SessionRow[]): SessionRow[] {
  return [...list].sort((a, b) => Number(b.current) - Number(a.current) || String(b.last_seen_at ?? b.created_at).localeCompare(String(a.last_seen_at ?? a.created_at)));
}

export function SessionsRow({ devices, onChanged }: { devices: TrustedDevice[]; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const q = useSessions();
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState<number | "others" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const footerRef = useRef<HTMLButtonElement>(null);
  const list = orderSessions(q.data ?? []);
  const shown = all ? list : list.slice(0, SESSIONS_VISIBLE);
  const others = list.filter((s) => !s.current).length;
  const refresh = () => void qc.invalidateQueries({ queryKey: authSecurityKeys.sessions });

  const end = async (s: SessionRow) => {
    setBusy(s.id);
    try {
      await authSecurity.endSession(s.id);
      toast.success(t("auth.security.sessionEnded"));
      refresh();
      // the row leaves: keep focus in the block, never on <body>
      requestAnimationFrame(() => footerRef.current?.focus());
    } catch (e) {
      toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setBusy(null);
    }
  };

  const endOthers = async () => {
    setBusy("others");
    try {
      const out = await authSecurity.endOtherSessions();
      if (devices.length) await authSecurity.forgetAllDevices().catch(() => undefined);
      toast.success(t("auth.security.endOthersDone", { n: out.revoked }));
      setConfirm(false);
      refresh();
      onChanged();
    } catch (e) {
      toast.error(mfaErrorText(e, locale) ?? t("auth.admin.errGeneric"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <SecurityRow title={t("auth.security.sessions")} status={q.isLoading || list.length ? null : t("auth.security.sessionsNone")} testId="security-sessions">
      {q.isLoading ? <Skeleton className="h-16 w-full" /> : null}
      {shown.length ? (
        <ul className="flex flex-col divide-y divide-(--hairline) rounded-xl bg-fill-3" aria-label={t("auth.security.sessions")} data-testid="session-list">
          {shown.map((s) => {
            const Glyph = isPhone(s.os ?? s.device) ? Smartphone : Monitor;
            return (
              <li key={s.id} className="auth-row-in flex flex-wrap items-center gap-3 px-3 py-2.5" data-testid="session-row">
                <Glyph aria-hidden className="size-5 shrink-0 text-label-2" />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="flex min-w-0 flex-wrap items-center gap-2 type-callout font-semibold text-label-1">
                    <span className="truncate" data-testid="session-device">{sessionLabel(s, t)}</span>
                    {s.current ? (
                      <Badge variant="secondary" data-testid="session-current">
                        {t("auth.security.thisDevice")}
                      </Badge>
                    ) : null}
                  </span>
                  <span className="type-footnote text-label-2">{t("auth.security.lastActive", { when: relative(s.last_seen_at ?? s.created_at, locale) })}</span>
                </div>
                {s.current ? null : (
                  <BusyButton type="button" variant="ghost" shape="rect" busy={busy === s.id} busyLabel={t("busy.working")} onClick={() => void end(s)} data-testid="session-end">
                    {t("auth.security.endSession")}
                  </BusyButton>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
      {!all && list.length > SESSIONS_VISIBLE ? (
        <Button type="button" variant="ghost" shape="rect" className="self-start" onClick={() => setAll(true)} data-testid="sessions-show-all">
          {t("auth.security.showAll", { n: list.length })}
        </Button>
      ) : null}
      <RememberedDevices devices={devices} onChanged={onChanged} />
      {others > 0 || devices.length > 0 ? (
        <Button ref={footerRef} type="button" variant="secondary" shape="rect" className="self-start text-status-infeasible-fg max-sm:w-full" onClick={() => setConfirm(true)} data-testid="sessions-end-others">
          {t("auth.security.endOthers")}
        </Button>
      ) : null}
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent role="alertdialog" data-testid="sessions-end-others-dialog">
          <DialogHeader>
            <DialogTitle>{t("auth.security.endOthersTitle")}</DialogTitle>
            <DialogDescription>{t("auth.security.endOthersBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" shape="rect" onClick={() => setConfirm(false)}>
              {t("auth.security.cancel")}
            </Button>
            <BusyButton type="button" variant="destructive" shape="rect" busy={busy === "others"} busyLabel={t("busy.working")} onClick={() => void endOthers()} data-testid="sessions-end-others-confirm">
              {t("auth.security.endOthers")}
            </BusyButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SecurityRow>
  );
}
