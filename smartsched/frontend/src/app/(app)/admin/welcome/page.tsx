import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { WelcomeAdmin } from "@/components/welcome/admin/welcome-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("welcome.admin.title");

/** WG-08: Yönetim › Karşılama rehberi (setup.settings / planning.admin). */
export default function WelcomeAdminPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <WelcomeAdmin />
      </HydrationGate>
    </Suspense>
  );
}
