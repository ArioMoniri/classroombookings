import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { MyBookingsView } from "@/components/bookings/my-bookings-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.myBookings");

/**
 * F-RF2-2 (fix-b-2026-10-18): an intermittent React #418 on /my-bookings?series=1 (after /bookings/mine?…). The view
 * reads queries the shell has often answered by the time this Suspense boundary hydrates (/me, the booking context,
 * the org date patterns), plus the deep link, so its first client render could differ from the server's loading
 * markup. HydrationGate renders the same placeholder on the server and in the hydration pass, then the view.
 */
export default function MyBookingsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <MyBookingsView />
      </HydrationGate>
    </Suspense>
  );
}
