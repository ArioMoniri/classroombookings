"use client";
/**
 * HX-02 (helper.md §2.2, §12): the top-bar trigger, a field-like button "Ara veya sor… ⌘K" (min 260 px, 36 px in the
 * capsule, 44 px hit area on touch). It opens the ⌘K palette (search first; "Yardımcıya sor" is a row there). Its
 * accessible name is "Ara veya sor (Ctrl+K)" / "(Cmd+K)"; the keycaps are decorative.
 */
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { KbdHint, modKeyLabel, usePlatformMod } from "@/components/ui/kbd-hint";
import { useI18n } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";

export function HelperTrigger() {
  const { t } = useI18n();
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const apple = usePlatformMod();
  return (
    <Button
      variant="bare"
      onClick={() => setPaletteOpen(true)}
      data-testid="helper-trigger"
      aria-label={`${t("helper.trigger.name")} (${modKeyLabel(apple)}+K)`}
      className="relative flex h-9 min-w-[260px] items-center gap-2 rounded-full bg-fill-2 px-3 text-left type-callout text-label-2 transition-colors duration-(--dur-fast) hover:bg-fill-1 hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus) pointer-coarse:min-h-11"
    >
      <Search aria-hidden className="size-4 shrink-0" />
      <span className="flex-1 truncate" aria-hidden>
        {t("helper.trigger.label")}
      </span>
      <KbdHint keys={["mod", "K"]} aria-hidden />
    </Button>
  );
}
