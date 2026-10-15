import { notFound } from "next/navigation";

/** Unknown URLs under the app render the 404 inside the shell ((app)/not-found.tsx), not the bare root page. */
export default function Missing() {
  notFound();
}
