"use client";

import { useRouter } from "next/navigation";
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
    <div role="group" aria-label={t("nav.language")} className={cn("inline-flex h-7 items-center gap-0.5 rounded-full bg-fill-2 p-[3px] text-xs shadow-[inset_0_0_0_1px_var(--hairline)]", className)} data-testid="locale-toggle">
      {languages.map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={locale === l}
          onClick={() => change(l)}
          lang={l}
          title={LOCALE_INFO[l].name}
          data-testid={`locale-option-${l}`}
          className={cn(
            "relative h-full rounded-full px-2.5 font-medium uppercase outline-hidden transition-colors duration-(--dur-fast) focus-visible:outline-2 focus-visible:outline-(--focus)",
            // 44 px hit area on coarse pointers without changing the drawn pill (skill §8)
            "pointer-coarse:after:absolute pointer-coarse:after:-inset-x-1 pointer-coarse:after:top-1/2 pointer-coarse:after:h-11 pointer-coarse:after:-translate-y-1/2 pointer-coarse:after:content-['']",
            locale === l ? "bg-(--mat-thick) text-label-1 shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline)]" : "text-label-2 hover:text-label-1",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
