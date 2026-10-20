"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n/provider";

const ORDER = ["system", "light", "dark"] as const;
type Mode = (typeof ORDER)[number];

export function useCycleTheme() {
  const { theme, setTheme } = useTheme();
  return () => {
    const current = (ORDER as readonly string[]).includes(theme ?? "") ? (theme as Mode) : "system";
    setTheme(ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]);
  };
}

/** The appearance switch (system → light → dark). A tooltip names the mode, so the bare glyph is never a guess. */
export function ThemeToggle({ className, tooltipSide = "top" }: { className?: string; tooltipSide?: "top" | "right" | "bottom" | "left" }) {
  const { theme } = useTheme();
  const { t } = useI18n();
  const cycle = useCycleTheme();
  const mounted = useSyncExternalStore(() => () => undefined, () => true, () => false);
  const mode: Mode = mounted && (ORDER as readonly string[]).includes(theme ?? "") ? (theme as Mode) : "system";
  const Icon = mode === "dark" ? Moon : mode === "light" ? Sun : Monitor;
  const label = `${t("nav.theme")}: ${t(`theme.${mode}`)}`;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button variant="ghost" size="icon-sm" className={className} onClick={cycle} aria-label={label} data-testid="theme-toggle">
            <Icon className="size-4" />
          </Button>
        }
      />
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}
