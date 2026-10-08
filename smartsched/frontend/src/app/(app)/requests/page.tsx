import { redirect } from "next/navigation";

/**
 * /requests is now a saved view of All classes (docs/design/v2/all-classes.md §2): "Gözden geçir"
 * (review) shows the planner's request rows. Old links and bookmarks keep working, including
 * ?kind=exams and ?id=<request id>.
 */
export default async function RequestsRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const one = (k: string) => (Array.isArray(sp[k]) ? sp[k]?.[0] : sp[k]);
  const q = new URLSearchParams({ view: "review" });
  const kind = one("kind");
  if (kind === "exams" || kind === "exam") q.set("kind", "exams");
  const id = one("id") ?? one("request");
  if (id) q.set("id", id);
  const term = one("term");
  if (term) q.set("term", term);
  redirect(`/classes?${q.toString()}`);
}
