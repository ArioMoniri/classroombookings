"use client";
/**
 * "Başka bir yöntem" (docs/design/v3/auth.md §5.2; AUX-04): a disclosure under the verify button that opens in place
 * (free transitions.dev Panel reveal, auth.css). Rows only for the methods the account has: passkey, recovery code /
 * back to the app, and "Hiçbirine erişemiyor musunuz?" with the help text. Every row is a 44 px target.
 */
import { ChevronDown, KeyRound, LifeBuoy, Smartphone, Ticket } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import "./auth.css";

export type MfaView = "totp" | "recovery" | "passkey";

export function OtherMethods({ methods, view, onPick, contact }: { methods: readonly string[]; view: MfaView; onPick: (v: MfaView) => void; contact?: string | null }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const panel = useId();
  const helpId = useId();
  const rows: { key: MfaView; label: string; icon: typeof KeyRound }[] = [];
  if (methods.includes("passkey") && view !== "passkey") rows.push({ key: "passkey", label: t("auth.mfa.usePasskey"), icon: KeyRound });
  if (view !== "recovery") rows.push({ key: "recovery", label: t("auth.mfa.useRecovery"), icon: Ticket });
  if (view !== "totp" && methods.includes("totp")) rows.push({ key: "totp", label: t("auth.mfa.useApp"), icon: Smartphone });
  const row = "-mx-2 min-h-11 w-[calc(100%+16px)] justify-start gap-3 px-2 text-left whitespace-normal active:scale-100";
  return (
    <div className="mt-4" data-testid="mfa-other">
      <Button type="button" variant="ghost" shape="rect" size="lg" aria-expanded={open} aria-controls={panel} onClick={() => setOpen((o) => !o)} className={cn(row, "justify-between font-semibold")} data-testid="mfa-other-toggle">
        <span>{t("auth.mfa.otherMethod")}</span>
        <ChevronDown aria-hidden className={cn("size-4 transition-transform duration-(--dur-fast) motion-reduce:transition-none", open && "rotate-180")} />
      </Button>
      {open ? (
        <div id={panel} className="auth-panel-in flex flex-col pt-1">
          {rows.map((r) => (
            <Button
              key={r.key}
              type="button"
              variant="ghost"
              shape="rect"
              size="lg"
              className={row}
              onClick={() => {
                setOpen(false);
                onPick(r.key);
              }}
              data-testid={`mfa-use-${r.key}`}
            >
              <r.icon aria-hidden className="size-4 text-label-2" />
              {r.label}
            </Button>
          ))}
          <Button type="button" variant="ghost" shape="rect" size="lg" aria-expanded={help} aria-controls={helpId} className={row} onClick={() => setHelp((h) => !h)} data-testid="mfa-no-access">
            <LifeBuoy aria-hidden className="size-4 text-label-2" />
            {t("auth.mfa.noAccess")}
          </Button>
          {help ? (
            <div id={helpId} className="auth-panel-in rounded-xl bg-fill-3 p-3 type-footnote text-label-1" data-testid="mfa-no-access-text">
              <p>{t("auth.mfa.noAccessText")}</p>
              {contact ? <p className="mt-1.5 text-label-2">{contact}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
