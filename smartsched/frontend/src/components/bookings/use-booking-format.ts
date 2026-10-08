"use client";
import { useMemo } from "react";
import { useBookingContext } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { dateFormatter, type DateFormatter } from "./date-format";

/** Dates in the organisation's patterns (`GET /bookings/context` → `date_patterns`) and the UI language. */
export function useBookingFormat(): DateFormatter {
  const { locale } = useI18n();
  const ctx = useBookingContext();
  const patterns = ctx.data?.date_patterns;
  return useMemo(() => dateFormatter(patterns, locale), [patterns, locale]);
}
