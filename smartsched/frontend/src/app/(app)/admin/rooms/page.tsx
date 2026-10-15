import { Suspense } from "react";
import { RoomsAdmin } from "@/components/admin/rooms-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminRooms");

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <RoomsAdmin />
    </Suspense>
  );
}
