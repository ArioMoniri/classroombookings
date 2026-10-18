"use client";
/**
 * RF-11: the e-mails' deep links. `?booking=<id>` opens that booking's detail sheet on /my-bookings and /bookings;
 * `?series=<id>` rides along (the e-mail client threads a series' messages on it, backend app/services/mail.py
 * thread_id) and names the series the booking belongs to. Once the sheet is open both leave the address, so closing
 * the sheet does not open it again and the back button returns to the plain page.
 */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

const DEEP = ["booking", "series"] as const;
const KEEP = ["request", "series", "booking"] as const;

export function deepLinkedBookingId(params: Pick<URLSearchParams, "get">): number | null {
  const raw = params.get("booking");
  if (!raw || !/^\d{1,10}$/.test(raw)) return null;
  const id = Number(raw);
  return id > 0 ? id : null;
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

/** Open the deep-linked booking once (``open``: the page's detail-sheet setter), then tidy the address. */
export function useDeepLinkedBooking(open: (id: number) => void): void {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const id = deepLinkedBookingId(params);
  useEffect(() => {
    if (id === null) return;
    open(id);
    router.replace(withoutDeepLink(pathname, new URLSearchParams(params.toString())), { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per linked id; `open` is a state setter
  }, [id]);
}
