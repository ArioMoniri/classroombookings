import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ExamAdvisorView } from "@/components/exams/advisor-panel";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("adaptive.exams.title");

/** AS-17 Sınav yükü ve öneriler: exam day load, slot seats, holds; advice only, nothing changes by itself. */
export default function ExamAdvisorPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ExamAdvisorView />
      </HydrationGate>
    </Suspense>
  );
}
