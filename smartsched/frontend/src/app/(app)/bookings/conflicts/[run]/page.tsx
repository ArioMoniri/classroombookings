import { ResolverView } from "@/components/conflicts/resolver-view";
import { HydrationGate } from "@/components/common/hydration-gate";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("resolver.title");

/** P2: the conflict resolver of one published run (planning.edit; keeping a clash needs planning.admin). */
export default async function ResolverPage({ params }: { params: Promise<{ run: string }> }) {
  const { run } = await params;
  return (
    <HydrationGate>
      <ResolverView runId={Number(run)} />
    </HydrationGate>
  );
}
