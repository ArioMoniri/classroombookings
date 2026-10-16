"use client";
/**
 * The first-sign-in privacy notice (A4 KVKK, Art. 10 aydınlatma): when `GET /me/privacy` says `needs_ack` (a notice is
 * published and this user has not acknowledged its version), a sheet with the notice and "Okudum" opens over the app
 * and stays until acknowledged. It never locks administrators out of the screens that publish a notice: holders of
 * `setup.settings` may postpone it ("Daha sonra", for this browser tab), and it never opens on /admin/kvkk.
 *
 * Motion: the design system's sheet / dialog transitions (springs.sheet, reduced-motion zeroed globally).
 */
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAckNotice, useMyPrivacy } from "@/lib/api/kvkk";
import { usePermissions } from "@/lib/api/shell-extra";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { Markdown } from "./markdown";

/** Routes the notice never covers: the screen where administrators write and publish it. */
export const GATE_EXEMPT = ["/admin/kvkk"];

export function shouldGate(opts: { needsAck: boolean; hasNotice: boolean; pathname: string; admin: boolean; postponed: boolean }): boolean {
  if (!opts.needsAck || !opts.hasNotice) return false;
  if (GATE_EXEMPT.some((p) => opts.pathname === p || opts.pathname.startsWith(`${p}/`))) return false;
  if (opts.admin && opts.postponed) return false;
  return true;
}

export function PrivacyNoticeGate() {
  const { t, locale } = useI18n();
  const hydrated = useHydrated();
  const pathname = usePathname();
  const { me, can } = usePermissions();
  const q = useMyPrivacy(hydrated && !!me && !me.force_password_reset);
  const ack = useAckNotice();
  const phone = useIsPhone();
  const admin = can("setup.settings");
  const [postponed, setPostponed] = useState(false);
  const okRef = useRef<HTMLButtonElement>(null);
  const notice = q.data?.notice ?? null;
  const open = shouldGate({ needsAck: !!q.data?.needs_ack, hasNotice: !!notice, pathname, admin, postponed });
  if (!open || !notice) return null;

  const confirm = () => ack.mutate(notice.id, { onSuccess: () => toast.success(t("privacy.notice.acked")), onError: (e) => toast.error(errorText(wave1Error(e), locale)) });
  const actions = (
    <>
      {admin ? (
        <Button variant="ghost" onClick={() => setPostponed(true)} data-testid="notice-gate-later">
          {t("privacy.gate.later")}
        </Button>
      ) : null}
      <Button ref={okRef} onClick={confirm} {...busyProps(ack.isPending)} data-testid="notice-gate-ack">
        <BusyLabel busy={ack.isPending} label={t("busy.saving")}>
          {t("privacy.notice.ack")}
        </BusyLabel>
      </Button>
    </>
  );
  const body = <Markdown source={notice.body_md} className="type-callout text-label-1" />;
  // blocking: closing (Escape, outside press) is ignored; only "Okudum" (or an admin's "Daha sonra") ends it
  const keep = () => undefined;
  if (phone)
    return (
      <Sheet open onOpenChange={keep}>
        <SheetContent side="bottom" showCloseButton={false} initialFocus={okRef} className="inset-x-0! bottom-0! max-h-[calc(100dvh-1rem)]! gap-0 rounded-b-none!" data-testid="notice-gate">
          <SheetHeader className="px-5 pt-3 pb-2">
            <SheetTitle>{notice.title}</SheetTitle>
            <SheetDescription>{t("privacy.gate.lead", { v: notice.version })}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-4">{body}</div>
          <SheetFooter className="flex-col-reverse gap-2 px-5 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))] [&>button]:w-full">{actions}</SheetFooter>
        </SheetContent>
      </Sheet>
    );
  return (
    <Dialog open onOpenChange={keep}>
      <DialogContent showCloseButton={false} initialFocus={okRef} className="flex max-h-[85dvh] flex-col sm:max-w-2xl" data-testid="notice-gate">
        <DialogHeader>
          <DialogTitle>{notice.title}</DialogTitle>
          <DialogDescription>{t("privacy.gate.lead", { v: notice.version })}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg bg-fill-3 p-3">{body}</div>
        <DialogFooter>{actions}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
