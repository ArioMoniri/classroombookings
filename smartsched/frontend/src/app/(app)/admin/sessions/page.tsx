import { SessionsAdmin } from "@/components/admin/sessions-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminSessions");

export default function Page() {
  return <SessionsAdmin />;
}
