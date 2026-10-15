import { RolesAdmin } from "@/components/admin/roles-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminRoles");

export default function Page() {
  return <RolesAdmin />;
}
