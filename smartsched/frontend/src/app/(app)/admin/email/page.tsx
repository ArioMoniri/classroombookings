import type { Metadata } from "next";
import { EmailSettingsView } from "@/components/admin/email-settings";

export const metadata: Metadata = { title: "Email" };

export default function Page() {
  return <EmailSettingsView />;
}
