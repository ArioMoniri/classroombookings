import { ConflictsIndex } from "@/components/conflicts/conflicts-index";
import { HydrationGate } from "@/components/common/hydration-gate";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("resolver.title");

/** P2: the published runs with open booking conflicts (planning.edit). */
export default function ConflictsPage() {
  return (
    <HydrationGate>
      <ConflictsIndex />
    </HydrationGate>
  );
}
