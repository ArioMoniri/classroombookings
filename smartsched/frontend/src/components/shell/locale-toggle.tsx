"use client";

import { ChevronDown, Languages } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { LOCALE_INFO, coverage, isLocale, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

/**
 * Language picker (shell, login card, settings). It offers the languages the organisation enabled (CRBS
 * setup/Language; `GET /org/i18n` `languages`): two of them stay a segmented toggle, more open a menu with the
 * language names in themselves. The CRBS languages translate only part of SmartSched (the rest is English, per
 * key), so each of them carries a "partial translation" note with its share.
 */
export function LocaleToggle({ className }: { className?: string }) {
  const { locale, setLocale, languages, t, n } = useI18n();
  const router = useRouter();
  const change = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    router.refresh();
  };
  const pct = (l: Locale) => n(Math.max(coverage(l).ratio, 0.01), { style: "percent", maximumFractionDigits: 0 });

  if (languages.length <= 2) {
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
            className={cn("h-full rounded-full px-2.5 font-medium uppercase outline-none transition-colors duration-(--dur-fast) focus-visible:outline-2 focus-visible:outline-(--focus)", locale === l ? "bg-(--mat-thick) text-label-1 shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline)]" : "text-label-2 hover:text-label-1")}
          >
            {l}
          </button>
        ))}
      </div>
    );
  }

  const current = coverage(locale);
  return (
    <div className={cn("inline-flex", className)} data-testid="locale-toggle">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 rounded-full px-2.5 text-xs"
              aria-label={`${t("nav.language")}: ${LOCALE_INFO[locale].name}${current.partial ? ` (${t("nav.languagePartial", { pct: pct(locale) })})` : ""}`}
              data-testid="locale-picker"
            />
          }
        >
          <Languages aria-hidden className="size-3.5" />
          <span className="font-medium uppercase" lang={locale}>
            {locale}
          </span>
          <ChevronDown aria-hidden className="size-3 text-label-3" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-80 w-auto min-w-56">
          <DropdownMenuRadioGroup value={locale} onValueChange={(v) => (isLocale(String(v)) ? change(String(v) as Locale) : undefined)}>
            {languages.map((l) => {
              const cov = coverage(l);
              return (
                <DropdownMenuRadioItem key={l} value={l} lang={l} data-testid={`locale-option-${l}`} className="items-start py-1.5">
                  <span className="flex min-w-0 flex-col">
                    <span className="flex items-baseline gap-1.5">
                      <span className="text-label-1">{LOCALE_INFO[l].name}</span>
                      <span className="text-[11px] text-label-3 uppercase">{l}</span>
                    </span>
                    {cov.partial ? (
                      <span className="text-[11px] text-label-3" lang={locale} data-testid={`locale-partial-${l}`}>
                        {t("nav.languagePartial", { pct: pct(l) })}
                      </span>
                    ) : null}
                  </span>
                </DropdownMenuRadioItem>
              );
            })}
          </DropdownMenuRadioGroup>
          {languages.some((l) => coverage(l).partial) ? <p className="max-w-56 px-1.5 pt-1 pb-0.5 text-[11px] text-label-3">{t("nav.languagePartialHint")}</p> : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
