import type { Metadata } from "next";
import { Suspense } from "react";
import { MyBookingsView } from "@/components/bookings/my-bookings-view";

export const metadata: Metadata = { title: "My bookings" };

export default function MyBookingsPage() {
  return (
    <Suspense fallback={null}>
      <MyBookingsView />
    </Suspense>
  );
}
