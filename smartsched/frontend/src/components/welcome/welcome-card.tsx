"use client";
/** One welcome card: an informational button (activating it opens that part, spec §4.1). */
import { ChevronRight } from "lucide-react";
import { BareButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ResolvedCard } from "./model";

export function WelcomeCard({ card, title, body, alsoLabel, onOpen, className }: { card: ResolvedCard; title: string; body: string; alsoLabel: string; onOpen: (card: ResolvedCard) => void; className?: string }) {
  return (
    <BareButton
      onClick={() => onOpen(card)}
      data-testid={`welcome-card-${card.key}`}
      data-audience={card.audience}
      className={cn(
        "group/card flex min-h-[116px] w-full items-start gap-3 rounded-2xl bg-card p-4 text-left edge-hairline outline-hidden transition-colors duration-(--dur-fast) hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
        className,
      )}
    >
      <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-fill-2 text-tint-text [&_svg]:size-[18px]">
        <card.icon />
      </span>
      <span className="min-w-0 flex-1">
        {card.also ? <span className="mb-0.5 block type-overline text-label-3">{alsoLabel}</span> : null}
        <span className="block type-headline text-label-1">{title}</span>
        <span className="mt-0.5 block type-callout text-label-2">{body}</span>
      </span>
      <ChevronRight aria-hidden className="mt-1 size-4 shrink-0 text-label-3" />
    </BareButton>
  );
}
