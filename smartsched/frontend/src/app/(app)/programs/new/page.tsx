import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ProgramWizard } from "@/components/program-wizard/program-wizard";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("programWizard.title");

/** Yeni program (Phase 19): the landing with Taslaklarım and Oluşturulanlar; a draft opens at /programs/new/<id> */
export default function NewProgramPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ProgramWizard />
      </HydrationGate>
    </Suspense>
  );
}
