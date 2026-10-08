"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { LocaleToggle } from "./locale-toggle";
import { NavList } from "./sidebar";
import { TermSwitcher } from "./term-switcher";
import { ThemeToggle } from "./theme-toggle";

/** "More" on phones: every destination in a bottom sheet (inset, grabber), grouped like the sidebar. */
export function MobileDrawer() {
  const open = useUiStore((s) => s.drawerOpen);
  const setOpen = useUiStore((s) => s.setDrawerOpen);
  const pathname = usePathname();
  const { t } = useI18n();
  useEffect(() => setOpen(false), [pathname, setOpen]);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="bottom" className="gap-0 p-0" aria-label={t("nav.menu")}>
        <SheetHeader className="px-4 pt-1 pb-2">
          <SheetTitle className="type-title-3 text-left">{t("glass.shell.more")}</SheetTitle>
          <SheetDescription className="sr-only">{t("app.tagline")}</SheetDescription>
        </SheetHeader>
        <div className="px-3 pb-2">
          <TermSwitcher collapsed={false} />
        </div>
        <nav aria-label={t("glass.shell.primary")} className="scrollbar-thin flex max-h-[55dvh] flex-col gap-4 overflow-y-auto px-2 pb-3 [&_a]:h-11">
          <NavList collapsed={false} onNavigate={() => setOpen(false)} />
        </nav>
        <div className="flex items-center justify-between gap-2 px-4 py-3 hairline-t">
          <LocaleToggle />
          <ThemeToggle />
        </div>
      </SheetContent>
    </Sheet>
  );
}
