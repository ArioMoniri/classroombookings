/**
 * Period facts derived from the one period grid (`@/lib/time`). Calendar, classes and rooms code reads the grid
 * only through here or `@/lib/time`. RF-16: the grid is the server's (`GET /period-grid`, applied by the app shell),
 * so every fact is computed at call time; nothing here is a module-level value computed from PERIODS.
 */
import { PERIODS, PERIODS_PER_DAY, isEveningPeriod, parseClock, type Period } from "@/lib/time";

const minutes = (clock: string) => parseClock(clock) ?? 0;

/** "08:30" by default: the start of the teaching day (P1). */
export function dayStart(): string {
  return PERIODS[0].start;
}

/** "22:50" by default: the end of the teaching day (P18). */
export function dayEnd(): string {
  return PERIODS[PERIODS.length - 1].end;
}

/** The short transition period between day and evening teaching (17:30–18:00, P12 by default): the shortest period. */
export function transitionPeriod(): number {
  return [...PERIODS].sort((a, b) => minutes(a.end) - minutes(a.start) - (minutes(b.end) - minutes(b.start)) || a.index - b.index)[0].index;
}

export function transition(): Period {
  return PERIODS[transitionPeriod() - 1];
}

/** First evening (İÖ) period. */
export function firstEveningPeriod(): number {
  return PERIODS.find((p) => isEveningPeriod(p.index))?.index ?? PERIODS_PER_DAY + 1;
}

/** The last daytime period before the transition. */
export function lastDaytimePeriod(): number {
  return transitionPeriod() - 1;
}
