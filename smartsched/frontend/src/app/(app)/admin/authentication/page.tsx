import type { Metadata } from "next";
import { LdapSettingsView } from "@/components/admin/ldap-settings";

export const metadata: Metadata = { title: "Authentication" };

export default function Page() {
  return <LdapSettingsView />;
}
