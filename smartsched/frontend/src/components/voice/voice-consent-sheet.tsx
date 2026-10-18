"use client";
/**
 * First use of the mic (research §3.2 step 1, §3.4 KVKK purpose `voice`): one sheet that says, in plain words,
 * where the voice goes (the provider and region the administrators chose), that no recording is kept, that the
 * text comes into the box for checking before anything is sent, and that the browser will ask for the microphone
 * next. "Kabul et ve başla" records the consent (`POST /me/consents/voice`) and starts the recording; "Şimdi değil"
 * closes it. Focus goes to the primary action and back to the mic afterwards.
 */
import { Mic } from "lucide-react";
import { useRef, type RefObject } from "react";
import { Alert } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useGrantVoiceConsent, type VoiceStatus } from "@/lib/api/voice";
import { useI18n } from "@/lib/i18n/provider";

export function VoiceConsentSheet({
  open,
  onOpenChange,
  status,
  onAccepted,
  returnFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  status: VoiceStatus | undefined;
  onAccepted: () => void;
  returnFocus?: RefObject<HTMLElement | null>;
}) {
  const { t, locale } = useI18n();
  const grant = useGrantVoiceConsent();
  const accept = useRef<HTMLButtonElement>(null);
  const provider = (locale === "en" ? status?.provider_label_en : null) || status?.provider_label || t("voice.consent.providerUnknown");
  const region = status?.region ? status.region.toUpperCase() : null;
  const where = region ? t("voice.consent.whereRegion", { provider, region }) : t("voice.consent.where", { provider });
  return (
    <Sheet open={open} onOpenChange={(o) => onOpenChange(o)}>
      <SheetContent side="bottom" className="mx-auto w-full max-w-lg" initialFocus={accept} finalFocus={returnFocus ?? true} data-testid="voice-consent">
        <SheetHeader className="pt-2">
          <SheetTitle className="flex items-center gap-2">
            <Mic aria-hidden className="size-5 text-label-2" />
            {t("voice.consent.title")}
          </SheetTitle>
          <SheetDescription>{where}</SheetDescription>
        </SheetHeader>
        <ul className="flex list-disc flex-col gap-1.5 px-4 ps-8 type-callout text-label-1">
          <li>{t("voice.consent.noKeep")}</li>
          <li>{t("voice.consent.review")}</li>
          <li>{t("voice.consent.browser")}</li>
        </ul>
        <p className="px-4 type-footnote text-label-2">{t("voice.consent.withdraw")}</p>
        {grant.isError ? (
          <div className="px-4">
            <Alert tone="error">{t("voice.consent.error")}</Alert>
          </div>
        ) : null}
        <SheetFooter className="flex-row flex-wrap justify-end gap-2 p-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="voice-consent-later">
            {t("voice.consent.later")}
          </Button>
          <Button
            ref={accept}
            {...busyProps(grant.isPending)}
            onClick={() =>
              grant.mutate(undefined, {
                onSuccess: () => {
                  onOpenChange(false);
                  onAccepted();
                },
              })
            }
            data-testid="voice-consent-accept"
          >
            <BusyLabel busy={grant.isPending} label={t("busy.saving")} icon={<Mic aria-hidden />}>
              {t("voice.consent.accept")}
            </BusyLabel>
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
