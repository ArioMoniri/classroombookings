import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { FacultyAiPage } from "@/components/admin/ai/faculty-ai-page";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("helper.facultyNav");

/** HX-10: "Fakültemin yapay zekâ kullanımı" for a faculty's quota managers (`ai.usage_faculty`). */
export default function FacultyAiUsagePage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <FacultyAiPage />
      </HydrationGate>
    </Suspense>
  );
}
