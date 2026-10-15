import { HydrationGate } from "@/components/common/hydration-gate";
import { Suspense } from "react";
import { ImportWizard } from "@/components/import/import-wizard";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.import");

export default function ImportPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ImportWizard />
      </HydrationGate>
    </Suspense>
  );
}
