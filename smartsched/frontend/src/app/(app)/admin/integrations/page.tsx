import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { IntegrationsGallery } from "@/components/admin/integrations/integrations-gallery";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("integrations.title");

/** W3-HUB integrations gallery: identity, e-mail, calendar, channels, webhooks / automation, AI (admins). */
export default function IntegrationsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <IntegrationsGallery />
      </HydrationGate>
    </Suspense>
  );
}
