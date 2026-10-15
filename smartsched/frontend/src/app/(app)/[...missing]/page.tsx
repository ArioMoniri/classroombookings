import { notFound } from "next/navigation";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.notFound");

/** Unknown URLs under the app render the 404 inside the shell ((app)/not-found.tsx), not the bare root page. */
export default function Missing() {
  notFound();
}
