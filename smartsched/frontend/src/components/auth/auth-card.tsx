"use client";

import { Logo } from "@/components/brand";
import type { ReactNode } from "react";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { GlassPanel } from "@/components/ui/glass-panel";
import { useAppVersion } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";

/** Regular glass over the scene (rule G1). Left-aligned content (A5), one primary action (A6). */
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { t } = useI18n();
  // the running version from the backend (GET /health, pyproject version), not a hard-coded label
  const version = useAppVersion();
  return (
    <GlassPanel material="regular" radius="2xl" className="w-full max-w-[400px] p-6 sm:p-8">
      <div className="mb-8 flex items-center gap-3">
        <Logo variant="tile" size={36} decorative />
        <div>
          <p className="type-headline text-label-1">{t("app.name")}</p>
          <p className="type-footnote text-label-3">{t("auth.subtitle")}</p>
        </div>
      </div>
      <h1 className="type-title-1 text-label-1">{title}</h1>
      {subtitle ? <p className="mt-1 text-[13px] text-label-2">{subtitle}</p> : null}
      <div className="mt-6">{children}</div>
      <div className="mt-8 flex items-center justify-between pt-4 text-[12px] text-label-3 hairline-t">
        <span className="tabular-nums" data-testid="app-version">{version.data ? t("admingaps.shell.version", { version: version.data }) : t("app.name")}</span>
        <div className="flex items-center gap-1">
          <LocaleToggle />
          <ThemeToggle />
        </div>
      </div>
    </GlassPanel>
  );
}
