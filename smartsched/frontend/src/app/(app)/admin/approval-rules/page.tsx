import type { Metadata } from "next";
import { ApprovalRulesAdmin } from "@/components/approvals/rules-admin";

export const metadata: Metadata = { title: "Approval rules" };

export default function Page() {
  return <ApprovalRulesAdmin />;
}
