import { ApprovalRulesAdmin } from "@/components/approvals/rules-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminApprovalRules");

export default function Page() {
  return <ApprovalRulesAdmin />;
}
