import { PeriodGridEditor } from "@/components/admin/period-grid-editor";
import { SchedulesAdmin } from "@/components/admin/schedules-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminSchedules");

export default function Page() {
  return (
    <div className="flex flex-col gap-8">
      <SchedulesAdmin />
      {/* RF-09: the clock times of P1-P18 (GET/PUT/DELETE /period-grid) */}
      <PeriodGridEditor />
    </div>
  );
}
