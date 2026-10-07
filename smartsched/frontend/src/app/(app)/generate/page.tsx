import type { Metadata } from "next";
import { GenerateView } from "@/components/generate/generate-view";

export const metadata: Metadata = { title: "Generate" };

export default function GeneratePage() {
  return <GenerateView />;
}
