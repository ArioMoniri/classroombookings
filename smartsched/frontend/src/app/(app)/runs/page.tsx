import type { Metadata } from "next";
import { HydrationGate } from "@/components/common/hydration-gate";
import { RunsList } from "@/components/runs/runs-list";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return <HydrationGate>
        <RunsList />
      </HydrationGate>;
}
