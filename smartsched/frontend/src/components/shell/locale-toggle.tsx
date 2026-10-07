"use client";

import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { LOCALES, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

export function LocaleToggle({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  const router = useRouter();
  const change = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    router.refresh();
  };
  return (
    <div role="group" aria-label={t("nav.language")} className={cn("inline-flex h-7 items-center rounded-md border bg-background p-0.5 text-xs", className)} data-testid="locale-toggle">
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={locale === l}
          onClick={() => change(l)}
          className={cn("rounded-sm px-2 py-0.5 font-medium uppercase transition-colors", locale === l ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
