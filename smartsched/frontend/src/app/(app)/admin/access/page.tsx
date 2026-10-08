import type { Metadata } from "next";
import { AccessChecker } from "@/components/admin/access-checker";

export const metadata: Metadata = { title: "Access" };

export default function Page() {
  return <AccessChecker />;
}
