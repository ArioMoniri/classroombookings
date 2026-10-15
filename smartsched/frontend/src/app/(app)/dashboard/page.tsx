import { HydrationGate } from "@/components/common/hydration-gate";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.dashboard");

export default function DashboardPage() {
  return <HydrationGate>
        <DashboardView />
      </HydrationGate>;
}
