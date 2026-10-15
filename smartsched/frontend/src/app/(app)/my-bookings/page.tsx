import { Suspense } from "react";
import { MyBookingsView } from "@/components/bookings/my-bookings-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.myBookings");

export default function MyBookingsPage() {
  return (
    <Suspense fallback={null}>
      <MyBookingsView />
    </Suspense>
  );
}
