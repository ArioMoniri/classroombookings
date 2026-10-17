import { Suspense } from "react";
import { QuickReserveView } from "@/components/quick-reserve/quick-reserve-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("quickReserve.title");

// W3-SLOT: reads ?date= (links from /bookings), so it renders under Suspense
export default function ReservePage() {
  return (
    <Suspense fallback={null}>
      <QuickReserveView />
    </Suspense>
  );
}
