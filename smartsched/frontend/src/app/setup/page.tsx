import { SetupWizard } from "@/components/admin/setup-wizard";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.setup");

export default function SetupPage() {
  return <SetupWizard />;
}
