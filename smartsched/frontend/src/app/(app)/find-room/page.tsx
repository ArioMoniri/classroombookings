import type { Metadata } from "next";
import { Suspense } from "react";
import { FindRoomView } from "@/components/findroom/find-room-view";

export const metadata: Metadata = { title: "Find a room" };

// reads ?date= / ?text= / ?headcount= (links from bookings and suggestions), so it renders under Suspense
export default function FindRoomPage() {
  return (
    <Suspense fallback={null}>
      <FindRoomView />
    </Suspense>
  );
}
