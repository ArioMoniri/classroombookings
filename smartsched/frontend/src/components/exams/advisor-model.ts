/**
 * AS-17 exam advisor cards from `GET /analytics/forecast/exams` (pure; advice only, nothing is moved). The ranked
 * date / slot moves of AS-12 belong to the solver lane's advisor endpoint; until it exists the cards name the
 * pressure: the peak day against the weekday mean, slots whose seats exceed the exam rooms, invigilators short.
 */
import type { ExamForecast } from "@/lib/api/adaptive";

export type AdviceKind = "peak_day" | "seats" | "invigilators";
export interface Advice {
  kind: AdviceKind;
  date: string;
  period?: number;
  /** numbers for the sentence */
  vars: Record<string, number | string>;
}

/** a peak day counts once it carries at least this many times the weekday mean (and 3 exams) */
export const PEAK_RATIO = 1.5;
/** a slot is tight above this share of the exam seats */
export const SEAT_LIMIT = 90;

export function examAdvice(f: ExamForecast, lang: "tr" | "en"): Advice[] {
  const out: Advice[] = [];
  const peakExams = f.peak_exams ?? 0;
  if (f.peak_day && peakExams >= 3 && (f.peak_to_mean ?? 0) >= PEAK_RATIO) {
    out.push({ kind: "peak_day", date: f.peak_day, vars: { day: f.peak_label?.[lang] || f.peak_day, exams: peakExams, mean: Math.round((f.weekday_mean ?? 0) * 10) / 10 } });
  }
  const tight = f.slots.filter((s) => (s.seat_pct ?? 0) > SEAT_LIMIT).sort((a, b) => (b.seat_pct ?? 0) - (a.seat_pct ?? 0));
  for (const s of tight.slice(0, 5)) {
    out.push({ kind: "seats", date: s.date, period: s.period, vars: { seats: s.seats, capacity: s.exam_capacity ?? 0, pct: Math.round(s.seat_pct ?? 0), period: s.period } });
  }
  const short = f.slots.filter((s) => (s.invigilators_short ?? 0) > 0).sort((a, b) => (b.invigilators_short ?? 0) - (a.invigilators_short ?? 0));
  for (const s of short.slice(0, 3)) {
    out.push({ kind: "invigilators", date: s.date, period: s.period, vars: { short: s.invigilators_short ?? 0, need: s.invigilators ?? 0, pool: s.pool ?? 0, period: s.period } });
  }
  return out;
}
