import { ConflictsAdmin } from "@/components/admin/conflicts-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminConflicts");

export default function Page() {
  return <ConflictsAdmin />;
}
