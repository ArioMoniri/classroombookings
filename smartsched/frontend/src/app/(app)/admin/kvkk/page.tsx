import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { KvkkAdmin } from "@/components/kvkk/kvkk-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("kvkk.title");

/** A4 KVKK administration: requests (setup.users), notice, retention, inventory (setup.settings). */
export default function KvkkPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <KvkkAdmin />
      </HydrationGate>
    </Suspense>
  );
}
