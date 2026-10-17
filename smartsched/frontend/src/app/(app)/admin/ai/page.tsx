import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { AiAdmin } from "@/components/admin/ai/ai-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("aiAdmin.title");

/** W3-AI: AI providers, models per feature, usage, limits and guardrails (planning.admin / setup.settings). */
export default function AiAdminPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <AiAdmin />
      </HydrationGate>
    </Suspense>
  );
}
