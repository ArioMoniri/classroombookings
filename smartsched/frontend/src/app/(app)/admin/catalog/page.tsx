import { redirect } from "next/navigation";

/** Yönetim › Katalog opens on the first list (RF-05). */
export default function Page() {
  redirect("/admin/catalog/instructors");
}
