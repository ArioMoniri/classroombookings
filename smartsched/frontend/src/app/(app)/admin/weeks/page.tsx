import type { Metadata } from "next";
import { WeeksAdmin } from "@/components/admin/weeks-admin";

export const metadata: Metadata = { title: "Weeks" };

export default function Page() {
  return <WeeksAdmin />;
}
