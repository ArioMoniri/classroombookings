import type { Metadata } from "next";
import { HolidaysAdmin } from "@/components/admin/holidays-admin";

export const metadata: Metadata = { title: "Holidays" };

export default function Page() {
  return <HolidaysAdmin />;
}
