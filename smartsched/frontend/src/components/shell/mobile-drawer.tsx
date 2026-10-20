"use client";

import { XIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { LocaleToggle } from "./locale-toggle";
import { NavList } from "./sidebar";
import { TermSwitcher } from "./term-switcher";
import { ThemeToggle } from "./theme-toggle";
import { DrawerWelcomeRows } from "@/components/welcome";
import { AskHelperDrawerRow } from "./ask-helper";

/**
 * "More" on phones: every destination in a bottom sheet (inset, grabber), grouped like the sidebar.
 * Order (login-navbar-2026-10): title + close on one line, the term, the onboarding checklist card while it runs, the
 * destinations, then Yardım (help rows aligned with the navigation rows), then language and appearance.
 */
export function MobileDrawer() {
  const open = useUiStore((s) => s.drawerOpen);
  const setOpen = useUiStore((s) => s.setDrawerOpen);
  const pathname = usePathname();
  const { t } = useI18n();
  useEffect(() => setOpen(false), [pathname, setOpen]);
  const close = () => setOpen(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="bottom" className="gap-0 p-0" aria-label={t("nav.menu")} showCloseButton={false}>
        {/* the close button sits on the title's line (it floated 15 px below the title's centre) */}
        <SheetHeader className="flex-row items-center justify-between gap-2 px-4 pt-1 pb-2">
          <SheetTitle className="type-title-3 text-left">{t("glass.shell.more")}</SheetTitle>
          <SheetDescription className="sr-only">{t("app.tagline")}</SheetDescription>
          <SheetClose render={<Button variant="ghost" size="icon-sm" className="-mr-1.5 text-label-2" />}>
            <XIcon aria-hidden />
            <span className="sr-only">{t("common.close")}</span>
          </SheetClose>
        </SheetHeader>
        <div className="px-3 pb-2">
          <TermSwitcher collapsed={false} />
        </div>
        <div className="scrollbar-thin flex max-h-[55dvh] flex-col overflow-y-auto">
          {/* WG-06: the "Başlarken" card stays the first row while onboarding runs */}
          <DrawerWelcomeRows part="checklist" onNavigate={close} />
          <nav aria-label={t("glass.shell.primary")} className="flex flex-col gap-4 px-2 pb-1 [&_a]:h-11">
            <NavList collapsed={false} onNavigate={close} />
          </nav>
          <DrawerWelcomeRows part="help" onNavigate={close} assistant={<AskHelperDrawerRow onNavigate={close} />} />
        </div>
        <div className="flex items-center justify-between gap-2 px-4 py-3 hairline-t">
          <LocaleToggle />
          <ThemeToggle className="pointer-coarse:size-[50px]" />
        </div>
      </SheetContent>
    </Sheet>
  );
}
