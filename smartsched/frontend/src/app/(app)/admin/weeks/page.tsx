import { WeeksAdmin } from "@/components/admin/weeks-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminWeeks");

export default function Page() {
  return <WeeksAdmin />;
}
