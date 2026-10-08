"use client";
/** Calendar keyboard map (calendar.md §12), opened with "?". Browser-safe keys only (no ⌘1–6). */
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";

const GROUPS: { title: MessageKey; rows: [string, MessageKey][] }[] = [
  { title: "calendar.keys.lenses", rows: [["B W D M Y A", "calendar.keys.lens"], ["⇧B", "calendar.keys.toggleStrip"], ["S", "calendar.keys.subject"], ["/", "calendar.keys.search"]] },
  { title: "calendar.keys.navigate", rows: [["T", "calendar.keys.today"], ["J K  [ ]", "calendar.keys.prevNext"], ["⇧[ ⇧]", "calendar.keys.fourWeeks"], ["← → ↑ ↓ · PgUp PgDn · Home End", "calendar.keys.cells"], ["+ − 0", "calendar.keys.zoomKeys"]] },
  { title: "calendar.keys.edit", rows: [["Enter", "calendar.keys.open"], ["N", "calendar.keys.newHere"], ["Space", "calendar.keys.pickUp"], ["⇧↑↓ · ⌥↑↓", "calendar.keys.resize"], ["L", "calendar.keys.lockKey"], ["E", "calendar.keys.explainKey"], ["⌘Z · ⌘⇧Z", "calendar.keys.undoRedo"]] },
  { title: "calendar.keys.select", rows: [["X", "calendar.keys.toggleSel"], ["⌘A", "calendar.keys.selectAll"], ["C", "calendar.keys.compareKey"], ["I", "calendar.keys.inspector"], ["Esc", "calendar.keys.escape"], ["?", "calendar.keys.help"]] },
];

export function ShortcutsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{t("calendar.shortcuts")}</SheetTitle>
          <SheetDescription>{t("calendar.lassoHint")}</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-5 overflow-y-auto px-4 pb-6">
          {GROUPS.map((g) => (
            <section key={g.title}>
              <h3 className="mb-1.5 text-[11px] font-semibold text-label-3">{t(g.title)}</h3>
              <dl className="flex flex-col gap-1.5">
                {g.rows.map(([k, label]) => (
                  <div key={label} className="flex items-center justify-between gap-4 text-[13px]">
                    <dt>{t(label)}</dt>
                    <dd><kbd className="rounded-md bg-fill-2 px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap text-label-1">{k}</kbd></dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
