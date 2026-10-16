"use client";
/**
 * "?" / the user menu: the keyboard shortcuts. The keycaps come from ui/kbd-hint, so the modifier reads ⌘ on Apple
 * platforms and Ctrl elsewhere (T-R1-06, R1-A-40: the sheet printed ⌘ on Linux and Windows), and the g-sequences
 * list every page this user may open, Taleplerim included (g t for an academician, nav-config).
 */
import { KbdHint } from "@/components/ui/kbd-hint";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { usePermissions } from "@/lib/api/shell-extra";
import { visibleNavGroups } from "./nav-config";

type Row = { id: string; keys: string[]; sequence?: boolean; label: string };

export function ShortcutsSheet() {
  const open = useUiStore((s) => s.shortcutsOpen);
  const setOpen = useUiStore((s) => s.setShortcutsOpen);
  const { t } = useI18n();
  const { can } = usePermissions();
  const rows: Row[] = [
    { id: "palette", keys: ["mod", "K"], label: t("shortcuts.palette") },
    { id: "sidebar", keys: ["mod", "B"], label: t("shortcuts.sidebar") },
    ...visibleNavGroups(can)
      .flatMap((g) => g.items)
      .filter((i) => i.key)
      .map((i): Row => ({ id: `goto-${i.href}`, keys: ["G", i.key!.toUpperCase()], sequence: true, label: t("shortcuts.goto", { page: t(i.labelKey) }) })),
    { id: "theme", keys: ["T"], label: t("shortcuts.theme") },
    { id: "lang", keys: ["L"], label: t("shortcuts.lang") },
    { id: "help", keys: ["?"], label: t("shortcuts.help") },
  ];
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-full sm:max-w-sm" data-testid="shortcuts-sheet">
        <SheetHeader>
          <SheetTitle>{t("shortcuts.title")}</SheetTitle>
          <SheetDescription className="sr-only">{t("shortcuts.title")}</SheetDescription>
        </SheetHeader>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 px-4 type-callout">
          {rows.map((r) => (
            <div key={r.id} className="contents">
              <dt>
                <KbdHint keys={r.keys} sequence={r.sequence} thenLabel={t("glass.shell.then")} size="md" />
              </dt>
              <dd className="text-label-2">{r.label}</dd>
            </div>
          ))}
        </dl>
      </SheetContent>
    </Sheet>
  );
}
