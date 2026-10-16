"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LOCALE_INFO, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

/**
 * Language picker (shell, login card, settings): a segmented toggle of the languages the organisation enabled
 * (CRBS setup/Language; `GET /org/i18n` `languages`). Only Turkish and English are offered (product-owner
 * decision 2026-10-15, ROADMAP P18-LANG): they are the two fully translated languages. Each option shows its
 * code (the tooltip names the language in itself) and has a 44 px hit area on touch screens.
 */
export function LocaleToggle({ className }: { className?: string }) {
  const { locale, setLocale, languages, t } = useI18n();
  const router = useRouter();
  const change = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    router.refresh();
  };

  return (
    <div role="group" aria-label={t("nav.language")} className={cn("inline-flex h-7 items-center gap-0.5 rounded-full bg-fill-2 p-[3px] edge-hairline pointer-coarse:h-9", className)} data-testid="locale-toggle">
      {languages.map((l) => (
        <Button
          key={l}
          variant="ghost"
          size="xs"
          aria-pressed={locale === l}
          onClick={() => change(l)}
          lang={l}
          title={LOCALE_INFO[l].name}
          data-testid={`locale-option-${l}`}
          className={cn(
            // the Button keeps a 44 px hit area on coarse pointers without changing the drawn pill (skill §8)
            "h-full px-2.5 uppercase",
            locale === l ? "bg-(--mat-thick) text-label-1 glass-edge hover:bg-(--mat-thick)" : "text-label-2 hover:bg-transparent hover:text-label-1",
          )}
        >
          {l}
        </Button>
      ))}
    </div>
  );
}
