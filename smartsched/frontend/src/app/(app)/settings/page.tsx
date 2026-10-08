import type { Metadata } from "next";
import { HydrationGate } from "@/components/common/hydration-gate";
import { Suspense } from "react";
import { SettingsView } from "@/components/settings/settings-view";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <SettingsView />
      </HydrationGate>
    </Suspense>
  );
}
