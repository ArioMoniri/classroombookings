import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { OpsPanel } from "@/components/admin/ops/ops-panel";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("ops.title");

/** W3-OPS operations panel: service status, errors, request chart, Grafana, log tail (admins). */
export default function OpsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <OpsPanel />
      </HydrationGate>
    </Suspense>
  );
}
