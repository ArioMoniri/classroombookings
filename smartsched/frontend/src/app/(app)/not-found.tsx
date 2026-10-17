import { NotFoundView } from "@/components/shell/not-found-view";

/** UI/UX review §3: the 404 inside the shell (sidebar, top bar), left-aligned, with a role-aware home link. */
export default function AppNotFound() {
  return <NotFoundView inShell />;
}
