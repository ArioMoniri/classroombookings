"use client";

import { CalendarRange } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { LocaleToggle } from "./locale-toggle";
import { NavList } from "./sidebar";
import { TermSwitcher } from "./term-switcher";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

export function MobileDrawer() {
  const open = useUiStore((s) => s.drawerOpen);
  const setOpen = useUiStore((s) => s.setDrawerOpen);
  const pathname = usePathname();
  const { t } = useI18n();
  useEffect(() => setOpen(false), [pathname, setOpen]);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="left" className="w-[280px] p-0 sm:max-w-[280px]" aria-label={t("nav.menu")}>
        <SheetHeader className="border-b px-4 py-3">
          <SheetTitle className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <CalendarRange className="size-4" aria-hidden />
            </span>
            {t("app.name")}
          </SheetTitle>
          <SheetDescription className="sr-only">{t("app.tagline")}</SheetDescription>
        </SheetHeader>
        <div className="px-2 pt-2">
          <TermSwitcher collapsed={false} />
        </div>
        <NavList collapsed={false} onNavigate={() => setOpen(false)} />
        <div className="space-y-2 border-t p-2">
          <UserMenu />
          <div className="flex items-center justify-between">
            <LocaleToggle />
            <ThemeToggle />
            <span className="text-xs text-muted-foreground">{t("app.version")}</span>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
