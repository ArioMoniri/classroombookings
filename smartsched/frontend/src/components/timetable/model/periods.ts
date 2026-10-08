/**
 * Period facts derived from the one period grid (`@/lib/time`). Calendar, classes and rooms code reads the grid
 * only through here or `@/lib/time`, so serving the grid from the backend later changes a single source.
 */
import { PERIODS, PERIODS_PER_DAY, isEveningPeriod, parseClock } from "@/lib/time";

const minutes = (clock: string) => parseClock(clock) ?? 0;

/** "08:30" and "22:50": the teaching day. */
export const DAY_START = PERIODS[0].start;
export const DAY_END = PERIODS[PERIODS.length - 1].end;

/** The short transition period between day and evening teaching (17:30–18:00, P12): the shortest period. */
export const TRANSITION_PERIOD = [...PERIODS].sort((a, b) => minutes(a.end) - minutes(a.start) - (minutes(b.end) - minutes(b.start)) || a.index - b.index)[0].index;
export const TRANSITION = PERIODS[TRANSITION_PERIOD - 1];

/** First evening (İÖ) period and the last daytime period before the transition. */
export const FIRST_EVENING_PERIOD = PERIODS.find((p) => isEveningPeriod(p.index))?.index ?? PERIODS_PER_DAY + 1;
export const LAST_DAYTIME_PERIOD = TRANSITION_PERIOD - 1;
