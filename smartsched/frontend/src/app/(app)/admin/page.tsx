import { AdminOverview } from "@/components/admin/admin-overview";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.admin");

export default function AdminPage() {
  return <AdminOverview />;
}
