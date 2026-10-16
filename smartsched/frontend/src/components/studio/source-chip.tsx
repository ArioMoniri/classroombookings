"use client";

import { BotMessageSquare, FileSpreadsheet, FileUp, LayoutTemplate, Shield, UserRound, type LucideIcon } from "lucide-react";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

/** `TEMPLATE` is display-only: the API stores such rules as ADMIN with `params._via === "template"` (T-R1-46). */
export type SourceKind = "FILE" | "ADMIN" | "AI" | "UPLOAD" | "BUILTIN" | "TEMPLATE";

const ICON: Record<SourceKind, LucideIcon> = { FILE: FileSpreadsheet, ADMIN: UserRound, AI: BotMessageSquare, UPLOAD: FileUp, BUILTIN: Shield, TEMPLATE: LayoutTemplate };
const KEY: Record<SourceKind, MessageKey> = {
  FILE: "studio.source.FILE",
  ADMIN: "studio.source.ADMIN",
  AI: "studio.source.AI",
  UPLOAD: "studio.source.UPLOAD",
  BUILTIN: "studio.source.BUILTIN",
  TEMPLATE: "studio.source.TEMPLATE",
};

/** The chip to show: a rule the planner built from a template says "Şablon", not "Yönetici" (round-1 R1-S-08). */
export function asSource(s: string | null | undefined, params?: Record<string, unknown> | null): SourceKind {
  if (s === "ADMIN" && params?._via === "template") return "TEMPLATE";
  return s === "FILE" || s === "ADMIN" || s === "AI" || s === "UPLOAD" || s === "BUILTIN" ? s : "ADMIN";
}

/** Provenance chip: icon + word (never colour alone). Dashed while still a proposal. */
export function SourceChip({ source, proposal, className }: { source: SourceKind; proposal?: boolean; className?: string }) {
  const { t } = useI18n();
  const Icon = ICON[source];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-xs)] border px-1.5 py-0.5 type-caption font-medium leading-none",
        source === "AI" || source === "UPLOAD" ? "border-primary/40 bg-tint-soft text-tint-text" : source === "BUILTIN" ? "bg-fill-2 text-label-2" : "bg-background text-foreground",
        proposal && "border-dashed",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {t(KEY[source])}
      {proposal ? <span className="sr-only">, {t("studio.tray.notAdded")}</span> : null}
    </span>
  );
}
