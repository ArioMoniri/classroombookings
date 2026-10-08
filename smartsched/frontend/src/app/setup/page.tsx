import type { Metadata } from "next";
import { SetupWizard } from "@/components/admin/setup-wizard";

export const metadata: Metadata = { title: "Setup" };

export default function SetupPage() {
  return <SetupWizard />;
}
