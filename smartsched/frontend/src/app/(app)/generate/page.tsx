import type { Metadata } from "next";
import { Suspense } from "react";
import { StudioView } from "@/components/studio/studio-view";

export const metadata: Metadata = { title: "Generator Studio" };

export default function GeneratePage() {
  return (
    <Suspense>
      <StudioView />
    </Suspense>
  );
}
