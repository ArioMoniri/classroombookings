/**
 * Utilisation colour scale (docs/design/tokens.md §2.5; dataviz skill "sequential": one hue, more is darker in
 * light mode, the anchor flips in dark mode). Five steps on the design-system ramp `--seq-1..5`:
 *
 *   step 0: 0 %   ·   step 1: 1–25 %   ·   step 2: 26–50 %   ·   step 3: 51–75 %   ·   step 4: 76–100 %
 *
 * Ink (heat.css): `label-1` on steps 0–2, white (light) / #0b1220 (dark) on steps 3–4; every pair ≥ 4.5:1
 * (light 15.5 / 11.8 / 6.6 / 5.2 / 10.4, dark 13.5 / 9.5 / 4.8 / 7.4 / 13.2). Colour is never the only cue:
 * every cell prints its number and names itself to assistive tech. A cell whose rooms are all pre-occupied
 * (blocked = capacity) is hatched and left out of the percentage ("—"); a partly blocked cell keeps its colour
 * and carries a corner hatch.
 */
export type HeatStep = 0 | 1 | 2 | 3 | 4;

export const STEP_BOUNDS: readonly { step: HeatStep; from: number; to: number }[] = [
  { step: 0, from: 0, to: 0 },
  { step: 1, from: 1, to: 25 },
  { step: 2, from: 26, to: 50 },
  { step: 3, from: 51, to: 75 },
  { step: 4, from: 76, to: 100 },
];

/** step of a percentage (0..100); anything above 0 but below 1 % is still step 1 (it is not empty) */
export function heatStep(pct: number): HeatStep {
  if (!(pct > 0)) return 0;
  if (pct <= 25) return 1;
  if (pct <= 50) return 2;
  if (pct <= 75) return 3;
  return 4;
}

export interface CountLike {
  occupied: number;
  blocked: number;
  capacity: number;
  pct: number;
  held?: number;
}

export type CellState = { kind: "blocked" } | { kind: "empty" } | { kind: "value"; pct: number; step: HeatStep; partlyBlocked: boolean };

/** what a heat cell shows: fully pre-occupied (hatched), no capacity at all, or a percentage */
export function cellState(c: CountLike | undefined | null): CellState {
  if (!c || c.capacity <= 0) return { kind: "empty" };
  if (c.blocked >= c.capacity) return { kind: "blocked" };
  return { kind: "value", pct: c.pct, step: heatStep(c.pct), partlyBlocked: c.blocked > 0 };
}

/** "12" for 12.4 %, "0,5" below 1 % (so a nearly empty cell never reads as 0), locale decimal mark */
export function pctText(pct: number, locale: string): string {
  const v = pct > 0 && pct < 1 ? Math.round(pct * 10) / 10 : Math.round(pct);
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(v);
}

/** signed delta with a real minus sign: +3, −2,5, 0 */
export function signed(v: number, locale: string, digits = 1): string {
  const f = new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(Math.abs(v));
  return v > 0 ? `+${f}` : v < 0 ? `−${f}` : f;
}
