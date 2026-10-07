import type { Metadata } from "next";
import { Suspense } from "react";
import { RoomsView } from "@/components/rooms/rooms-view";

export const metadata: Metadata = { title: "Rooms" };

export default function RoomsPage() {
  return (
    <Suspense fallback={null}>
      <RoomsView />
    </Suspense>
  );
}
