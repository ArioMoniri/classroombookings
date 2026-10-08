"use client";

import { FileSpreadsheet, FileUp, Shield, Sparkles, UserRound, type LucideIcon } from "lucide-react";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

export type SourceKind = "FILE" | "ADMIN" | "AI" | "UPLOAD" | "BUILTIN";

const ICON: Record<SourceKind, LucideIcon> = { FILE: FileSpreadsheet, ADMIN: UserRound, AI: Sparkles, UPLOAD: FileUp, BUILTIN: Shield };
const KEY: Record<SourceKind, MessageKey> = {
  FILE: "studio.source.FILE",
  ADMIN: "studio.source.ADMIN",
  AI: "studio.source.AI",
  UPLOAD: "studio.source.UPLOAD",
  BUILTIN: "studio.source.BUILTIN",
};

export function asSource(s: string | null | undefined): SourceKind {
  return s === "FILE" || s === "ADMIN" || s === "AI" || s === "UPLOAD" || s === "BUILTIN" ? s : "ADMIN";
}

/** Provenance chip: icon + word (never colour alone). Dashed while still a proposal. */
export function SourceChip({ source, proposal, className }: { source: SourceKind; proposal?: boolean; className?: string }) {
  const { t } = useI18n();
  const Icon = ICON[source];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-xs)] border px-1.5 py-0.5 text-[11px] font-medium leading-none",
        source === "AI" || source === "UPLOAD" ? "border-primary/40 bg-primary-tint text-primary" : source === "BUILTIN" ? "bg-muted text-muted-foreground" : "bg-background text-foreground",
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
