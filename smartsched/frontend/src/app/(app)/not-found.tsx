import { NotFoundView } from "@/components/shell/not-found-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.notFound");

export default function AppNotFound() {
  return <NotFoundView inShell />;
}
