"use client";
/** RF-11: open the e-mail's deep-linked booking (`?booking=<id>`, or the earliest booking of `?series=<id>` among
 *  ``seriesRows``) once, then drop booking / series from the address so closing the sheet does not open it again
 *  (pure helpers: ./deep-link-model.ts). */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { deepLinkedBookingId, deepLinkedSeriesId, firstOfSeries, type SeriesRow, withoutDeepLink } from "./deep-link-model";

/** Open the deep-linked booking once (``open``: the page's detail-sheet setter), then tidy the address. A series-only
 *  link waits for ``seriesRows`` (the page's loaded bookings); a series not among them opens nothing. */
export function useDeepLinkedBooking(open: (id: number) => void, seriesRows?: readonly SeriesRow[] | null): void {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const id = deepLinkedBookingId(params);
  const sid = id === null ? deepLinkedSeriesId(params) : null;
  const ready = id !== null || (sid !== null && seriesRows != null);
  const target = id ?? (sid !== null && seriesRows ? firstOfSeries(seriesRows, sid) : null);
  useEffect(() => {
    if (!ready) return;
    if (target !== null) {
      // a sheet opened from the address has no trigger: the sheet returns focus to what was focused when it opened,
      // which is <body> on a fresh load. Park it on the page's <main> (tabIndex -1) first (e2e 2026-10-18).
      if (!document.activeElement || document.activeElement === document.body) document.getElementById("main")?.focus({ preventScroll: true });
      open(target);
    }
    router.replace(withoutDeepLink(pathname, new URLSearchParams(params.toString())), { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per linked booking; `open` is a state setter
  }, [ready, target]);
}
