"use client";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { ALL_NAV_ITEMS } from "./nav-config";

export function ShortcutsSheet() {
  const open = useUiStore((s) => s.shortcutsOpen);
  const setOpen = useUiStore((s) => s.setShortcutsOpen);
  const { t } = useI18n();
  const rows: [string, string][] = [
    ["⌘K", t("shortcuts.palette")],
    ["⌘B", t("shortcuts.sidebar")],
    ...ALL_NAV_ITEMS.filter((i) => i.key).map((i): [string, string] => [`g ${i.key}`, t("shortcuts.goto", { page: t(i.labelKey) })]),
    ["t", t("shortcuts.theme")],
    ["l", t("shortcuts.lang")],
    ["?", t("shortcuts.help")],
  ];
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-full sm:max-w-sm">
        <SheetHeader>
          <SheetTitle>{t("shortcuts.title")}</SheetTitle>
          <SheetDescription className="sr-only">{t("shortcuts.title")}</SheetDescription>
        </SheetHeader>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-4 text-sm">
          {rows.map(([k, label]) => (
            <div key={k} className="contents">
              <dt><kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">{k}</kbd></dt>
              <dd className="text-muted-foreground">{label}</dd>
            </div>
          ))}
        </dl>
      </SheetContent>
    </Sheet>
  );
}
