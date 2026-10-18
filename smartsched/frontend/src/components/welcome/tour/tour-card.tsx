"use client";
/**
 * The tour's step card (spec §4.2, wireframes welcome-tour-{1440,390}.svg), rendered by the engine as its tooltip.
 * Title (≤ 4 words), body (≤ 2 sentences), "Adım n / N", dots, Geri, İleri / Bitir and an always-visible "Turu bitir".
 * Opaque `--surface-raised`-like solid material (no glass over the scrim, spec §8.3). Desktop: 360 px, anchored to the
 * target; phones: a docked sheet (min 200 px, max 45 % of the viewport) with 48 px Geri / İleri.
 * Keys: Tab stays in the card (the engine's trap), Enter on the card = İleri, ← / → = Geri / İleri, Esc = Turu bitir
 * (the runner listens for Esc globally).
 * Motion (WG-09, spec §8.1 "Step card in"): the engine fades the floater in (120 ms); the card adds scale .98 → 1 in
 * the same 120 ms from its first style (`@starting-style`, toward the bottom edge when docked). Text inside the card
 * never animates between steps. Reduced motion: the global rules zero the transition, so only the 100 ms fade stays.
 */
import { createContext, useContext, useId, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { EngineStep, TourControls } from "./engine";

export interface TourCardContextValue {
  step: EngineStep;
  controls: TourControls;
  docked: boolean;
  bodyId: string;
}
export const TourCardContext = createContext<TourCardContextValue | null>(null);

export function TourCard(props: { tooltipProps?: { "aria-modal"?: boolean; role?: string } }) {
  const ctx = useContext(TourCardContext);
  const { t } = useI18n();
  const titleId = useId();
  if (!ctx) return null;
  const { step, controls, docked, bodyId } = ctx;
  const last = controls.index + 1 >= controls.total;
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      controls.next();
    } else if (e.key === "ArrowLeft" && controls.index > 0) {
      e.preventDefault();
      controls.back();
    } else if (e.key === "Enter" && e.target === e.currentTarget) {
      e.preventDefault();
      controls.next();
    }
  };
  return (
    <div
      {...props.tooltipProps}
      role="dialog"
      aria-modal={step.interactive ? "false" : "true"}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      data-welcome=""
      data-testid="tour-card"
      data-step={step.id}
      className={cn(
        "flex flex-col gap-3 bg-(--mat-thick-solid) p-5 text-left text-label-1 shadow-elev-3 outline-hidden transition-[scale] duration-(--dur-fast) ease-(--ease-out) starting:scale-[.98] motion-reduce:transition-none motion-reduce:starting:scale-100",
        docked ? "origin-bottom" : "origin-center",
        docked ? "max-h-[45dvh] min-h-[200px] w-full overflow-y-auto rounded-3xl" : "w-[360px] max-w-[calc(100vw-2rem)] rounded-3xl",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="type-footnote text-label-3 tabular-nums" data-testid="tour-counter">
          {t("welcome.tour.counter", { n: controls.index + 1, total: controls.total })}
        </span>
        <Button variant="ghost" size="sm" className="-mr-2 text-label-2 pointer-coarse:min-h-11" onClick={controls.end} data-testid="tour-end" data-action="close">
          {t("welcome.tour.end")}
        </Button>
      </div>
      <div>
        <h2 id={titleId} className="type-headline text-label-1">
          {step.title}
        </h2>
        <p id={bodyId} className="mt-1 type-callout text-label-2">
          {step.body}
        </p>
      </div>
      <div className="mt-auto flex items-center gap-2">
        <span aria-hidden className="mr-auto flex items-center gap-1.5">
          {Array.from({ length: controls.total }, (_, i) => (
            <span key={i} className={cn("h-1.5 rounded-full", i === controls.index ? "w-4 bg-tint" : "w-1.5 bg-fill-1")} />
          ))}
        </span>
        {controls.index > 0 ? (
          <Button variant="secondary" className={cn(docked && "h-12 min-w-24")} onClick={controls.back} data-testid="tour-back" data-action="back">
            {t("welcome.tour.back")}
          </Button>
        ) : null}
        <Button className={cn(docked && "h-12 min-w-24")} onClick={controls.next} data-testid="tour-next" data-action="primary">
          {last ? t("welcome.tour.finish") : t("welcome.tour.next")}
        </Button>
      </div>
    </div>
  );
}
