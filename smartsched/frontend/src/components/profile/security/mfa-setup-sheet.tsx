"use client";
/**
 * The 2FA setup sheet (docs/design/v3/auth.md §6.3; AUX-06): right side 480 px at ≥ 600 px, full screen below; header
 * "İki aşamalı doğrulamayı açın" + "Adım 1–2 / 3" or "Adım 3 / 3". Closing at step 3 without "Bitir" asks first
 * ("Kodları kaydetmeden kapatılsın mı?"); 2FA stays on either way (it was switched on when the code verified).
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { TotpSetup, type SetupStep, type TotpTransport } from "./totp-setup";

export function MfaSetupSheet({ open, onOpenChange, transport, org, onDone }: { open: boolean; onOpenChange: (open: boolean) => void; transport: TotpTransport; org?: string | null; onDone: () => void }) {
  const { t } = useI18n();
  const [step, setStep] = useState<SetupStep>("connect");
  const [confirmClose, setConfirmClose] = useState(false);
  const request = (next: boolean) => {
    if (next) return onOpenChange(true);
    if (step === "codes") return setConfirmClose(true);
    onOpenChange(false);
  };
  return (
    <>
      <Sheet open={open} onOpenChange={request}>
        <SheetContent side="right" className="data-[side=right]:sm:max-w-[480px] max-[599px]:inset-0 max-[599px]:h-full max-[599px]:w-full max-[599px]:rounded-none" data-testid="mfa-setup-sheet">
          <SheetHeader className="sticky top-0 z-10 pr-12">
            <SheetTitle>{t("auth.setup.title")}</SheetTitle>
            <SheetDescription data-testid="mfa-setup-step">{step === "codes" ? t("auth.setup.step", { n: 3 }) : t("auth.setup.steps12")}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
            {open ? (
              <TotpSetup
                transport={transport}
                org={org}
                onStep={setStep}
                onDone={() => {
                  setStep("connect");
                  onOpenChange(false);
                  onDone();
                }}
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
      <Dialog open={confirmClose} onOpenChange={setConfirmClose}>
        <DialogContent role="alertdialog" data-testid="mfa-setup-close-confirm">
          <DialogHeader>
            <DialogTitle>{t("auth.setup.closeTitle")}</DialogTitle>
            <DialogDescription>{t("auth.setup.closeBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" shape="rect" onClick={() => setConfirmClose(false)} data-testid="mfa-setup-back">
              {t("auth.setup.backToCodes")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              shape="rect"
              onClick={() => {
                setConfirmClose(false);
                setStep("connect");
                onOpenChange(false);
                onDone();
              }}
              data-testid="mfa-setup-close-anyway"
            >
              {t("auth.security.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
