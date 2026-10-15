import { Suspense } from "react";
import { FindRoomView } from "@/components/findroom/find-room-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.findRoom");

// reads ?date= / ?text= / ?headcount= (links from bookings and suggestions), so it renders under Suspense
export default function FindRoomPage() {
  return (
    <Suspense fallback={null}>
      <FindRoomView />
    </Suspense>
  );
}
