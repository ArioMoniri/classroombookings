import { CatalogAdmin } from "@/components/admin/catalog/catalog-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminCatalog");

export default function Page() {
  return <CatalogAdmin tab="faculties" />;
}
