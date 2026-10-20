"use client";
/**
 * "Yardımcıya sor" (helper.md §2.2 "Help"): the first row of the user menu's Yardım group (above "Turu yeniden
 * başlat") and of the phone "Daha" › Yardım group. It opens the helper sheet; focus returns to the user menu / the
 * "Daha" tab when the sheet closes. Not offered when there is no signed-in person or an administrator switched the
 * helper off for them (`GET /helper/status` → `enabled: false`; the sheet would not mount, helper-root.tsx).
 */
import { MessageCircleQuestion } from "lucide-react";
import { BareButton } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useHelperStore } from "@/components/helper/helper-store";
import { useHelperStatus } from "@/lib/api/helper";
import { useMeFull } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";

function useAskAvailable(): boolean {
  const me = useMeFull();
  const status = useHelperStatus(!!me.data);
  return !!me.data && !!status.data && status.data.enabled !== false;
}

const opener = (testId: string) => (typeof document !== "undefined" ? document.querySelector<HTMLElement>(`[data-testid="${testId}"]`) : null);

/** User menu › Yardım. */
export function AskHelperMenuItem() {
  const { t } = useI18n();
  const available = useAskAvailable();
  if (!available) return null;
  return (
    <DropdownMenuItem
      // after the menu has closed and given focus back to its trigger, so the sheet's focus is not taken back
      onClick={() => window.setTimeout(() => useHelperStore.getState().openSheet({ opener: opener("user-menu") }), 0)}
      data-testid="help-ask-helper"
    >
      <MessageCircleQuestion /> {t("helper.askHelper")}
    </DropdownMenuItem>
  );
}

/** Phone "Daha" › Yardım (44 px row, like the other help rows). */
export function AskHelperDrawerRow({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const available = useAskAvailable();
  if (!available) return null;
  return (
    <BareButton
      onClick={() => {
        onNavigate?.();
        // after the drawer's close, so the full-screen sheet is not opened inside a closing one
        window.setTimeout(() => useHelperStore.getState().openSheet({ opener: opener("open-drawer") }), 180);
      }}
      className="flex min-h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left type-callout font-medium text-label-1 outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:stroke-[1.75] [&_svg]:text-label-2"
      data-testid="drawer-ask-helper"
    >
      <MessageCircleQuestion aria-hidden /> {t("helper.askHelper")}
    </BareButton>
  );
}
