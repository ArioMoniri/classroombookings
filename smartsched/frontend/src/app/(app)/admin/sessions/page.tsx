import type { Metadata } from "next";
import { SessionsAdmin } from "@/components/admin/sessions-admin";

export const metadata: Metadata = { title: "Sessions" };

export default function Page() {
  return <SessionsAdmin />;
}
