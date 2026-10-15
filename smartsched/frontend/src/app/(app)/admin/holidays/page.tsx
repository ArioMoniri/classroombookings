import { HolidaysAdmin } from "@/components/admin/holidays-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminHolidays");

export default function Page() {
  return <HolidaysAdmin />;
}
