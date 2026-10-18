"use client";
/**
 * "Son girişler" (docs/design/v3/auth.md §6.6; AUX-07), behind a disclosure: the last 20 security events from
 * `GET /auth/sign-ins` (time, result, method). The result is an icon AND a word (never colour alone); no address.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, Info, XCircle } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { authSecurity } from "@/lib/api/auth-security";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { dateTime } from "./format";
import { SecurityRow } from "./mfa-row";
import "@/components/auth/auth.css";

const KIND: Record<string, "ok" | "fail" | "warn" | "info"> = {
  "auth.login": "ok",
  "auth.mfa_verified": "ok",
  "auth.trusted_device_used": "ok",
  "auth.mfa_failed": "fail",
  "auth.login_refused": "warn",
  "auth.mfa_locked": "warn",
  "auth.mfa_reset_by_admin": "warn",
  "auth.mfa_recovery_used": "warn",
};
const ICON = { ok: CheckCircle2, fail: XCircle, warn: AlertTriangle, info: Info } as const;
const TONE = { ok: "text-status-feasible-fg", fail: "text-status-infeasible-fg", warn: "text-status-warning-fg", info: "text-label-2" } as const;
const KNOWN = new Set(["login", "login_refused", "mfa_verified", "mfa_failed", "mfa_locked", "mfa_enabled", "mfa_disabled", "mfa_reset_by_admin", "mfa_recovery_used", "mfa_recovery_regenerated", "passkey_added", "passkey_removed", "trusted_device_used", "trusted_device_added", "trusted_device_revoked", "reset_link_by_admin", "reset_code"]);
const METHODS = new Set(["local", "ldap", "passkey", "totp", "recovery", "disable"]);

export function actionKey(action: string): MessageKey {
  const k = action.replace(/^(auth|user)\./, "");
  return (KNOWN.has(k) ? `auth.history.a_${k}` : "auth.history.a_other") as MessageKey;
}

export function HistoryRow() {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const panel = useId();
  const q = useQuery({ queryKey: ["auth-security", "history"], queryFn: authSecurity.history, enabled: open, staleTime: 30_000, retry: false });
  const events = (q.data?.events ?? []).slice(0, 20);
  return (
    <SecurityRow
      title={t("auth.history.title")}
      status={null}
      action={
        <Button type="button" variant="ghost" shape="rect" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)} data-testid="history-toggle">
          {open ? t("auth.history.hide") : t("auth.history.show")}
          <ChevronDown aria-hidden className={cn("transition-transform duration-(--dur-fast) motion-reduce:transition-none", open && "rotate-180")} />
        </Button>
      }
      testId="security-history"
    >
      {open ? (
        <div id={panel} className="auth-panel-in flex flex-col gap-2">
          {q.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : events.length ? (
            <ul className="flex flex-col divide-y divide-(--hairline) rounded-xl bg-fill-3" data-testid="history-list">
              {events.map((e, i) => {
                const kind = KIND[e.action] ?? "info";
                const Icon = ICON[kind];
                return (
                  <li key={`${e.at}-${i}`} className="flex items-start gap-3 px-3 py-2">
                    <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", TONE[kind])} />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="type-callout text-label-1">
                        {t(actionKey(e.action))}
                        {e.method && METHODS.has(e.method) ? <span className="text-label-2"> · {t(`auth.history.m_${e.method}` as MessageKey)}</span> : null}
                        {e.by_admin ? <span className="text-label-2"> · {t("auth.history.byAdmin")}</span> : null}
                      </span>
                      <span className="type-footnote tabular-nums text-label-2">{dateTime(e.at, locale)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="type-callout text-label-2">{t("auth.history.empty")}</p>
          )}
          <p className="type-footnote text-label-3">{t("auth.history.footer")}</p>
        </div>
      ) : null}
    </SecurityRow>
  );
}
