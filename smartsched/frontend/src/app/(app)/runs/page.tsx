import type { Metadata } from "next";
import { RunsList } from "@/components/runs/runs-list";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return <RunsList />;
}
