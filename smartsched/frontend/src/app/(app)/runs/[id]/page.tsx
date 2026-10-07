import type { Metadata } from "next";
import { Suspense } from "react";
import { RunView } from "@/components/runs/run-view";

export const metadata: Metadata = { title: "Run" };

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <RunView id={Number(id)} />
    </Suspense>
  );
}
