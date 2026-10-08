import type { Metadata } from "next";
import { Suspense } from "react";
import { RoomsAdmin } from "@/components/admin/rooms-admin";

export const metadata: Metadata = { title: "Rooms" };

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <RoomsAdmin />
    </Suspense>
  );
}
