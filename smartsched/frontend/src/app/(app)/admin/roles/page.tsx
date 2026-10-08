import type { Metadata } from "next";
import { RolesAdmin } from "@/components/admin/roles-admin";

export const metadata: Metadata = { title: "Roles" };

export default function Page() {
  return <RolesAdmin />;
}
