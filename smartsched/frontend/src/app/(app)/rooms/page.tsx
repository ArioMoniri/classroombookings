import { Suspense } from "react";
import { RoomsView } from "@/components/rooms/rooms-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.rooms");

export default function RoomsPage() {
  return (
    <Suspense fallback={null}>
      <RoomsView />
    </Suspense>
  );
}
