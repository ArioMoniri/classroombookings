import { OrgSettingsView } from "@/components/admin/org-settings";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminSettings");

export default function Page() {
  return <OrgSettingsView />;
}
