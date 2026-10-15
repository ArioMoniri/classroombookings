import { Suspense } from "react";
import { BookingsView } from "@/components/bookings/bookings-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.bookings");

export default function BookingsPage() {
  return (
    <Suspense fallback={null}>
      <BookingsView />
    </Suspense>
  );
}
