import { WeekEditors } from "@/components/admin/week-editors";
import { SeasonProfiles } from "@/components/seasons/season-profiles";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminWeeks");

export default function Page() {
  return (
    <div className="flex flex-col gap-8">
      {/* the week editors (setup.timetable_weeks); a planner reaches this page for the profile drafts only */}
      <WeekEditors />
      {/* AS-15 season profiles: planners draft, admins approve (AS20-F09); hidden on 403 */}
      <SeasonProfiles />
    </div>
  );
}
