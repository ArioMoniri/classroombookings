"use client";
import { BotMessageSquare, BotOff, FileSpreadsheet } from "lucide-react";
import { useAiPolicy } from "@/lib/api/ai-policy";
import { cn } from "@/lib/utils";
import { useOnboardingCopy } from "./copy";

/** How a file / row is read: Doğrudan, YZ, or with the AI switched off "YZ kapalı" (before reading: only the tables
 * the server can read) / "YZ kapalı, okunmadı" (nothing could be read). Glyph + word (+ confidence for AI rows),
 * never colour alone (G4, phase19-intake I4; T-R1-23).
 *
 * T-R2-21: the badge shows the effective route, not the planned one. While the administrator's AI policy is off
 * (GET /ai/policy `intake_enabled: false`) a row or file planned for "YZ" is read directly (its tables) or, when
 * `whenOff` says so (a scan, a route the server marked ai-off), not at all: "Doğrudan" / "Okunmadı", never "YZ". */
export type ReadMethod = "direct" | "ai" | "off" | "unread";

export function MethodBadge({ method: planned, confidence, className, whenOff = "direct" }: { method: ReadMethod; confidence?: number | null; className?: string; whenOff?: "direct" | "unread" }) {
  const c = useOnboardingCopy();
  const policy = useAiPolicy();
  const method: ReadMethod = planned === "ai" && policy.data?.intake_enabled === false ? whenOff : planned;
  const ai = method === "ai";
  const off = method === "off" || method === "unread";
  const Icon = ai ? BotMessageSquare : off ? BotOff : FileSpreadsheet;
  const word = ai ? c.ai : method === "off" ? c.aiOff : method === "unread" ? c.aiOffUnread : c.direct;
  return (
    <span
      data-slot="method-badge"
      data-method={method}
      title={ai ? c.aiHint : off ? c.aiOffHint : c.directHint}
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 type-caption", ai ? "bg-status-locked text-status-locked-fg" : "bg-fill-2 text-label-1", className)}
    >
      <Icon aria-hidden className="size-3 stroke-[1.75]" />
      {word}
      {ai && confidence != null ? <span className="tnum">{c.pct(Math.round(confidence * 100))}</span> : null}
    </span>
  );
}
