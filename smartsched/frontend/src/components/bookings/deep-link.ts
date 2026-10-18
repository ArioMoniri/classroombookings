"use client";
/** RF-11: open the e-mail's deep-linked booking (`?booking=<id>`) once, then drop booking / series from the address so
 *  closing the sheet does not open it again (pure helpers: ./deep-link-model.ts). */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { deepLinkedBookingId, withoutDeepLink } from "./deep-link-model";

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
