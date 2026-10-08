import type { Metadata } from "next";
import { OrgSettingsView } from "@/components/admin/org-settings";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return <OrgSettingsView />;
}
