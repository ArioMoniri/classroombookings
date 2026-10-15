import { LdapSettingsView } from "@/components/admin/ldap-settings";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminAuthentication");

export default function Page() {
  return <LdapSettingsView />;
}
