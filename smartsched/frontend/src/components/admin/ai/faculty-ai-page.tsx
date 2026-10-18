"use client";
/**
 * HX-10: the faculty quota manager's page (`/ai/faculty`, nav "Fakültemin yapay zekâ kullanımı"). Holders of
 * `ai.usage_faculty` see their faculty and split its allowance; administrators reach the same view under
 * Yönetim › Yapay zekâ › Limitler. The backend checks the faculty scope again on every call.
 */
import { NoAccess } from "@/components/admin/kit";
import { FacultyUsageView } from "@/components/helper/admin/faculty-usage";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";

export const FACULTY_AI_PERMISSIONS = ["ai.usage_faculty", "planning.admin", "setup.settings"] as const;

export function FacultyAiPage() {
  const { t } = useI18n();
  const { can, loading } = usePermissions();
  if (loading) return null;
  if (!can([...FACULTY_AI_PERMISSIONS])) return <NoAccess title={t("crbs.admin.noAccessTitle")} body={t("crbs.admin.noAccessBody")} />;
  return (
    <div className="flex max-w-3xl flex-col" data-testid="faculty-ai-page">
      {/* the view carries the visible title (h2); the page's h1 is for screen readers only, so it is not said twice */}
      <h1 className="sr-only">{t("helper.facultyNav")}</h1>
      <FacultyUsageView />
    </div>
  );
}
