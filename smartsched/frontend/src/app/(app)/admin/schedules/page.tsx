import { SchedulesAdmin } from "@/components/admin/schedules-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminSchedules");

export default function Page() {
  return <SchedulesAdmin />;
}
