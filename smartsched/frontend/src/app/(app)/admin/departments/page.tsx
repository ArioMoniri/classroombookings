import { DepartmentsAdmin } from "@/components/admin/departments-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminDepartments");

export default function Page() {
  return <DepartmentsAdmin />;
}
