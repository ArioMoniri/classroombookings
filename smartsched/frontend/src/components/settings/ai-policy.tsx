"use client";
/**
 * Settings › AI › AI policy (KVKK, backend `app/ai/policy.py`): the two switches for sending uploaded content to
 * the Claude API, both off by default.
 * - Turning one on shows the full notice (TR/EN, from the backend) first and needs the administrator's KVKK
 *   acknowledgement; the backend writes the sign-off record and an `ai.policy` audit event.
 * - The record (who, when, what) is shown after; disabling is possible at any time and needs no acknowledgement.
 * - This is the only control: the council's `council_ai_enabled` setting is an alias of the same policy.
 */
import { ShieldCheck } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAiPolicy, useSetAiPolicy, type AiPolicy, type AiSignoff } from "@/lib/api/ai-policy";
import { HttpError } from "@/lib/api/client";
import { usePermissions } from "@/lib/api/shell-extra";
import { pairLang } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

type Feature = "intake" | "vision";

/** "AI on / off": on when intake (the base switch) is effective. */
export function AiStatusPill({ policy }: { policy: AiPolicy | undefined }) {
  const { t } = useI18n();
  if (!policy) return null;
  const on = policy.intake_enabled;
  return (
    <span data-testid="ai-status-pill">
      <StatusBadge kind={on ? "feasible" : "locked"} label={on ? (policy.vision_enabled ? t("settings.aiPolicy.onVision") : t("settings.aiPolicy.on")) : t("settings.aiPolicy.off")} />
    </span>
  );
}

function SignoffLine({ signoff }: { signoff: AiSignoff }) {
  const { t, locale } = useI18n();
  const when = new Date(signoff.at);
  const date = Number.isNaN(when.getTime()) ? signoff.at : when.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "long", timeStyle: "short" });
  const who = signoff.by_label || t("settings.aiPolicy.someone");
  const features = signoff.features.map((f) => t(f === "vision" ? "settings.aiPolicy.vision" : "settings.aiPolicy.intake")).join(", ");
  return (
    <p className="flex items-start gap-2 type-footnote text-label-2" data-testid="ai-signoff">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-label-3" aria-hidden />
      <span>
        {signoff.enabled ? t("settings.aiPolicy.signedOff", { who, date, features }) : t("settings.aiPolicy.turnedOff", { who, date })}
        {signoff.notice_version ? ` · ${t("settings.aiPolicy.noticeVersion", { v: signoff.notice_version })}` : null}
        {signoff.reason ? ` · ${signoff.reason}` : null}
      </span>
    </p>
  );
}

export function AiPolicyCard() {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const admin = can("planning.admin");
  const q = useAiPolicy();
  const save = useSetAiPolicy();
  const [pending, setPending] = useState<Feature | null>(null);
  const [ack, setAck] = useState(false);
  const [reason, setReason] = useState("");
  const ackId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);
  const p = q.data;

  const errorText = (e: unknown) => (e instanceof HttpError && e.status === 403 ? t("settings.aiPolicy.adminOnly") : t("settings.aiPolicy.failed"));

  const toggle = (feature: Feature, on: boolean) => {
    if (!p) return;
    if (on) {
      // turning on: the full notice and the KVKK acknowledgement first
      setAck(false);
      setReason("");
      setPending(feature);
      return;
    }
    // turning off needs no acknowledgement; intake off takes vision with it (backend rule)
    save.mutate(feature === "intake" ? { intake_enabled: false } : { vision_enabled: false }, {
      onSuccess: () => toast.success(t("settings.aiPolicy.savedOff")),
      onError: (e) => toast.error(errorText(e)),
    });
  };

  const confirm = () => {
    if (!pending || !ack) return;
    const body = pending === "vision" ? { intake_enabled: true, vision_enabled: true } : { intake_enabled: true };
    save.mutate(
      { ...body, kvkk_ack: true, ...(reason.trim() ? { reason: reason.trim() } : {}) },
      {
        onSuccess: () => {
          setPending(null);
          toast.success(t("settings.aiPolicy.savedOn"));
        },
        onError: (e) => toast.error(errorText(e)),
      },
    );
  };

  return (
    <Card data-testid="ai-policy">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("settings.aiPolicy.title")}</CardTitle>
          <AiStatusPill policy={p} />
        </div>
        <CardDescription>{t("settings.aiPolicy.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        {q.isError ? <p role="alert" className="type-footnote text-status-infeasible-fg">{t("settings.aiPolicy.loadFailed")}</p> : null}
        {(["intake", "vision"] as const).map((f) => {
          const checked = f === "intake" ? !!p?.intake_enabled : !!p?.vision_enabled;
          const disabled = !p || !admin || save.isPending || (f === "vision" && !p.intake_enabled);
          return (
            <div key={f} className="flex items-center justify-between gap-4 py-2.5 [&:not(:last-child)]:hairline-b">
              <div className="min-w-0">
                <Label htmlFor={`ai-${f}`} className="text-[13px] font-medium text-label-1">{t(f === "intake" ? "settings.aiPolicy.intake" : "settings.aiPolicy.vision")}</Label>
                <p className="text-[12px] leading-4 text-label-2">{t(f === "intake" ? "settings.aiPolicy.intakeHint" : "settings.aiPolicy.visionHint")}</p>
              </div>
              <Switch id={`ai-${f}`} checked={checked} disabled={disabled} onCheckedChange={(on) => toggle(f, on)} data-testid={`ai-policy-${f}`} />
            </div>
          );
        })}
        {!admin ? <p className="pt-1 type-footnote text-label-3">{t("settings.aiPolicy.adminOnly")}</p> : null}
        {p?.signoff ? <div className="pt-2"><SignoffLine signoff={p.signoff} /></div> : <p className="pt-2 type-footnote text-label-3">{t("settings.aiPolicy.noSignoff")}</p>}
      </CardContent>

      <Dialog open={pending !== null} onOpenChange={(o) => !o && !save.isPending && setPending(null)}>
        <DialogContent className="sm:max-w-lg" initialFocus={confirmRef} data-testid="ai-policy-notice">
          <DialogHeader>
            <DialogTitle>{t(pending === "vision" ? "settings.aiPolicy.confirmVision" : "settings.aiPolicy.confirmIntake")}</DialogTitle>
            <DialogDescription>{t("settings.aiPolicy.readFirst")}</DialogDescription>
          </DialogHeader>
          {p ? (
            <div className="space-y-3">
              <p className="rounded-xl bg-fill-3 p-3 text-[13px] leading-5 text-label-1" lang={pairLang(locale)} data-testid="ai-policy-notice-text">
                {p.notice[pairLang(locale)]}
              </p>
              <p className="type-footnote text-label-3">{t("settings.aiPolicy.legal", { basis: p.legal_basis, v: p.notice_version })}</p>
              <label htmlFor={ackId} className="flex cursor-pointer items-start gap-2.5 text-[13px] text-label-1">
                <input id={ackId} type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 size-4 accent-(--accent)" data-testid="ai-policy-ack" />
                <span>{t("settings.aiPolicy.ack")}</span>
              </label>
              <div className="grid gap-1">
                <Label htmlFor="ai-policy-reason" className="text-[12.5px] text-label-2">{t("settings.aiPolicy.reason")}</Label>
                <Textarea id="ai-policy-reason" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("settings.aiPolicy.reasonHint")} />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPending(null)} disabled={save.isPending}>{t("common.cancel")}</Button>
            <Button ref={confirmRef} onClick={confirm} {...busyProps(save.isPending, !ack)} data-testid="ai-policy-confirm">
              <BusyLabel busy={save.isPending} label={t("settings.aiPolicy.saving")}>{t("settings.aiPolicy.enable")}</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
