import { localizedTitle } from "@/lib/i18n/server";
import { HydrationGate } from "@/components/common/hydration-gate";
import { RunsList } from "@/components/runs/runs-list";

export const generateMetadata = localizedTitle("titles.runs");

export default function RunsPage() {
  return <HydrationGate>
        <RunsList />
      </HydrationGate>;
}
