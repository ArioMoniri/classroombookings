import type { Metadata } from "next";
import { HydrationGate } from "@/components/common/hydration-gate";
import { DashboardView } from "@/components/dashboard/dashboard-view";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return <HydrationGate>
        <DashboardView />
      </HydrationGate>;
}
