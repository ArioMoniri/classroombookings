"use client";

import { CalendarRange } from "lucide-react";
import type { ReactNode } from "react";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { GlassPanel } from "@/components/ui/glass-panel";
import { useI18n } from "@/lib/i18n/provider";

/** Regular glass over the scene (rule G1). Left-aligned content (A5), one primary action (A6). */
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <GlassPanel material="regular" radius="2xl" className="w-full max-w-[400px] p-6 sm:p-8">
      <div className="mb-8 flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-[11px] bg-tint text-tint-foreground shadow-[inset_0_1px_0_0_rgba(255,255,255,0.28)]">
          <CalendarRange className="size-[18px] stroke-[1.75]" aria-hidden />
        </span>
        <div>
          <p className="type-headline text-label-1">{t("app.name")}</p>
          <p className="type-footnote text-label-3">{t("auth.subtitle")}</p>
        </div>
      </div>
      <h1 className="type-title-1 text-label-1">{title}</h1>
      {subtitle ? <p className="mt-1 text-[13px] text-label-2">{subtitle}</p> : null}
      <div className="mt-6">{children}</div>
      <div className="mt-8 flex items-center justify-between pt-4 text-[12px] text-label-3 hairline-t">
        <span>{t("app.version")}</span>
        <div className="flex items-center gap-1">
          <LocaleToggle />
          <ThemeToggle />
        </div>
      </div>
    </GlassPanel>
  );
}
