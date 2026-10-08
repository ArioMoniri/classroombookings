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
    <div role="group" aria-label={t("nav.language")} className={cn("inline-flex h-7 items-center gap-0.5 rounded-full bg-fill-2 p-[3px] text-xs shadow-[inset_0_0_0_1px_var(--hairline)]", className)} data-testid="locale-toggle">
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={locale === l}
          onClick={() => change(l)}
          lang={l}
          className={cn("h-full rounded-full px-2.5 font-medium uppercase outline-none transition-colors duration-(--dur-fast) focus-visible:outline-2 focus-visible:outline-(--focus)", locale === l ? "bg-(--mat-thick) text-label-1 shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline)]" : "text-label-2 hover:text-label-1")}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
