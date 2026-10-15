"use client";
import { BotMessageSquare, FileSpreadsheet } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOnboardingCopy } from "./copy";

/** Doğrudan / YZ: glyph + word (+ confidence for AI rows), never colour alone (G4, phase19-intake I4). */
export function MethodBadge({ method, confidence, className }: { method: "direct" | "ai"; confidence?: number | null; className?: string }) {
  const c = useOnboardingCopy();
  const ai = method === "ai";
  const Icon = ai ? BotMessageSquare : FileSpreadsheet;
  return (
    <span
      data-slot="method-badge"
      data-method={method}
      title={ai ? c.aiHint : c.directHint}
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 type-caption", ai ? "bg-status-locked text-status-locked-fg" : "bg-fill-2 text-label-1", className)}
    >
      <Icon aria-hidden className="size-3 stroke-[1.75]" />
      {ai ? c.ai : c.direct}
      {ai && confidence != null ? <span className="tnum">{Math.round(confidence * 100)} %</span> : null}
    </span>
  );
}
