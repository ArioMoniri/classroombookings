import { AuditView } from "@/components/audit/audit-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminAudit");

export default function Page() {
  return <AuditView />;
}
