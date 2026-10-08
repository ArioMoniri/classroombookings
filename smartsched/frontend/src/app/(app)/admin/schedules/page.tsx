import type { Metadata } from "next";
import { SchedulesAdmin } from "@/components/admin/schedules-admin";

export const metadata: Metadata = { title: "Schedules" };

export default function Page() {
  return <SchedulesAdmin />;
}
