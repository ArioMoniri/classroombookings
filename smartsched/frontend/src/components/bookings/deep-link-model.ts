/**
 * RF-11: the e-mails' deep links, pure helpers (also used by the server redirect /bookings/mine). `?booking=<id>`
 * opens that booking's detail sheet on /my-bookings and /bookings; `?series=<id>` rides along (e-mail clients thread
 * a series' messages on it, backend app/services/mail.py thread_id). A `?series=<id>` without a booking opens the
 * series' earliest booking among the rows the page has loaded (:func:`firstOfSeries`). The hook is ./deep-link.ts.
 */
const DEEP = ["booking", "series"] as const;
const KEEP = ["request", "series", "booking"] as const;

export function deepLinkedBookingId(params: Pick<URLSearchParams, "get">): number | null {
  const raw = params.get("booking");
  if (!raw || !/^\d{1,10}$/.test(raw)) return null;
  const id = Number(raw);
  return id > 0 ? id : null;
}

export function deepLinkedSeriesId(params: Pick<URLSearchParams, "get">): number | null {
  const raw = params.get("series");
  if (!raw || !/^\d{1,10}$/.test(raw)) return null;
  const id = Number(raw);
  return id > 0 ? id : null;
}

export interface SeriesRow {
  id: number;
  series_id?: number | null;
  date: string;
  status?: string | null;
}

/** The series' earliest booking that is not cancelled (else its earliest one); `null` when none is loaded. */
export function firstOfSeries(rows: readonly SeriesRow[], seriesId: number): number | null {
  const mine = rows.filter((r) => r.series_id === seriesId);
  const order = (a: SeriesRow, b: SeriesRow) => a.date.localeCompare(b.date) || a.id - b.id;
  const active = mine.filter((r) => r.status !== "CANCELLED").sort(order);
  return (active[0] ?? [...mine].sort(order)[0])?.id ?? null;
}

export function withoutDeepLink(pathname: string, params: URLSearchParams): string {
  const rest = new URLSearchParams(params);
  for (const k of DEEP) rest.delete(k);
  const q = rest.toString();
  return q ? `${pathname}?${q}` : pathname;
}

/** `/bookings/mine?…` (the backend's link) as this frontend's `/my-bookings?…`: request, series and booking only. */
export function myBookingsHref(sp: Record<string, string | string[] | undefined>): string {
  const q = new URLSearchParams();
  for (const k of KEEP) {
    const v = sp[k];
    const one = Array.isArray(v) ? v[0] : v;
    if (one && /^\d{1,10}$/.test(one)) q.set(k, one);
  }
  const s = q.toString();
  return s ? `/my-bookings?${s}` : "/my-bookings";
}
