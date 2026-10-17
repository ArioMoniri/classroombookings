/**
 * The tour engine interface (spec §11): the runner (tour-runner.tsx) owns the steps, routing, waiting for anchors,
 * events, focus and the live region; an engine only draws one step over one target. The React Joyride 3.2 adapter
 * (joyride-adapter.tsx) implements it; a driver.js adapter could replace it in one file (the spike kept Joyride:
 * SVG overlay without backdrop-filter, focus trap, Escape, aria-modal, custom tooltip, React 19 peer).
 */
import type { ComponentType } from "react";

export interface EngineStep {
  /** stable id (the anchor) */
  id: string;
  target: HTMLElement;
  title: string;
  body: string;
  /** the target stays operable and Tab can reach it */
  interactive: boolean;
}

export interface TourControls {
  index: number;
  total: number;
  next: () => void;
  back: () => void;
  end: () => void;
}

export interface TourEngineProps {
  step: EngineStep;
  controls: TourControls;
  /** docked step sheet (phones) instead of a card anchored to the target */
  docked: boolean;
  reduceMotion: boolean;
}

export type TourEngine = ComponentType<TourEngineProps>;
