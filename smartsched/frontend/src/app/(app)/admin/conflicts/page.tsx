import type { Metadata } from "next";
import { ConflictsAdmin } from "@/components/admin/conflicts-admin";

export const metadata: Metadata = { title: "Booking conflicts" };

export default function Page() {
  return <ConflictsAdmin />;
}
