import { EmailSettingsView } from "@/components/admin/email-settings";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminEmail");

export default function Page() {
  return <EmailSettingsView />;
}
