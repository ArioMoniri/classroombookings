"use client";
/**
 * HX-03 (helper.md §5.2, A6): the status chip — **Yerel model** / **Bulut · {sağlayıcı}** / **Bulut · yedek** /
 * **Yapay zekâ kapalı** / **Sınıra ulaşıldı**. Never inferred on the client: the mode, the reason and the provider
 * come from `GET /helper/status`, the limit from `GET /ai/me/usage`, the fallback from the last turn's
 * `run_finished`. The popover says why AI is off and **who can turn it on** (the person for consent, an
 * administrator for routing / the provider), with a link for the person who can.
 */
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useMyAiUsage } from "@/lib/api/ai-admin";
import { useHelperStatus, type HelperStatus } from "@/lib/api/helper";
import { usePermissions } from "@/lib/api/shell-extra";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { pickText } from "./cards/context";
import { useHelperStore } from "./helper-store";

export type ChipState = "local" | "cloud" | "fallback" | "off" | "limit";

export interface HelperMode {
  /** the helper answers with AI (else: Rehber modu) */
  ai: boolean;
  state: ChipState;
  status: HelperStatus | undefined;
  /** the composer is blocked by a limit (user, department, faculty) */
  blocked: boolean;
  loading: boolean;
}

/** Turn codes that mean "a limit", not "the provider failed" (HB-B `run_finished.fallback`). */
const LIMIT_CODES = new Set([
  "ai_limit_reached", "ai_budget_exceeded", "ai_faculty_limit_reached", "ai_department_limit_reached", "ai_feature_limit_reached",
  "ai_unit_limit_reached", "rate_limited", "too_many_concurrent",
]);

export function chipState(status: HelperStatus | undefined, usageState: string | undefined, fallback: string | null): ChipState {
  if (!status || status.mode !== "ai") return "off";
  if (usageState === "hard" || (fallback && LIMIT_CODES.has(fallback))) return "limit";
  if (fallback) return "fallback";
  return status.provider_kind === "local" ? "local" : "cloud";
}

export function useHelperMode(): HelperMode {
  const status = useHelperStatus();
  const ai = status.data?.mode === "ai";
  const usage = useMyAiUsage(ai);
  const fallback = useHelperStore((s) => s.turn.fallback);
  const state = chipState(status.data, usage.data?.state, fallback);
  return { ai, state, status: status.data, blocked: state === "limit", loading: status.isLoading };
}

const DOT: Record<ChipState, string> = {
  local: "bg-status-feasible-fg",
  cloud: "bg-tint",
  fallback: "bg-status-warning-fg",
  off: "bg-label-3",
  limit: "bg-status-infeasible-fg",
};

const BODY: Record<ChipState, MessageKey> = {
  local: "helper.status.localBody",
  cloud: "helper.status.cloudBody",
  fallback: "helper.status.fallbackBody",
  off: "helper.status.offBody",
  limit: "helper.status.limitBody",
};

/** Who can switch AI on for this reason: the person (consent) or an administrator. */
const WHO: Record<string, MessageKey> = {
  not_routed: "helper.status.who.admin",
  provider_unusable: "helper.status.who.admin",
  consent_missing: "helper.status.who.you",
  turn_unavailable: "helper.status.who.server",
  index_mode: "helper.status.who.admin",
  disabled: "helper.status.who.disabled",
  audience_off: "helper.status.who.disabled",
};

export function useChipWord(mode: HelperMode): string {
  const { t, locale } = useI18n();
  const provider = pickText(mode.status?.provider_label, locale);
  switch (mode.state) {
    case "local":
      return t("helper.status.local");
    case "cloud":
      return provider ? t("helper.status.cloud", { provider }) : t("helper.status.cloudPlain");
    case "fallback":
      return t("helper.status.fallback");
    case "limit":
      return t("helper.status.limit");
    default:
      return t("helper.status.off");
  }
}

/** The word + dot, for places where the chip is not a control (the palette's ask row). */
export function StatusWordChip({ mode, className }: { mode: HelperMode; className?: string }) {
  const word = useChipWord(mode);
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full bg-fill-2 px-2 type-caption text-label-1", className)} data-state={mode.state}>
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full forced-colors:outline forced-colors:outline-1", DOT[mode.state])} />
      {word}
    </span>
  );
}

export function StatusChip({ mode }: { mode: HelperMode }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { can } = usePermissions();
  const word = useChipWord(mode);
  const reason = mode.status?.reason ?? null;
  const admin = can(["setup.settings", "planning.admin"]);
  const provider = pickText(mode.status?.provider_label, locale);
  const go = (href: string) => {
    useHelperStore.getState().closeSheet();
    router.push(href);
  };
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="sm" aria-haspopup="dialog" data-testid="helper-status" data-state={mode.state} className="h-6 gap-1.5 rounded-full bg-fill-2 px-2 type-caption font-medium">
            <span aria-hidden className={cn("size-2 shrink-0 rounded-full forced-colors:outline forced-colors:outline-1", DOT[mode.state])} />
            {word}
          </Button>
        }
      />
      <PopoverContent align="end" className="w-80 p-4">
        <div className="flex flex-col gap-2 type-callout text-label-1" data-testid="helper-status-body">
          <p className="font-semibold">{word}</p>
          <p className="text-label-2">{t(BODY[mode.state], { provider: provider || "—" })}</p>
          {mode.state === "off" && mode.status?.message ? <p>{pickText(mode.status.message, locale)}</p> : null}
          {mode.state === "off" && reason && WHO[reason] ? <p className="text-label-2" data-testid="helper-status-who">{t(WHO[reason])}</p> : null}
          {mode.state === "off" && reason === "consent_missing" ? (
            <Button size="sm" variant="secondary" className="self-start" onClick={() => go("/profile#privacy")}>
              {t("helper.status.openPrivacy")}
            </Button>
          ) : null}
          {mode.state === "off" && admin && (reason === "not_routed" || reason === "provider_unusable" || reason === "index_mode") ? (
            <Button size="sm" variant="secondary" className="self-start" onClick={() => go("/admin/ai")} data-testid="helper-status-admin">
              {t("helper.status.openAdmin")}
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
