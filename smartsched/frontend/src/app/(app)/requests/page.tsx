import { redirect } from "next/navigation";

/**
 * /requests is now a saved view of All classes (docs/design/v2/all-classes.md §2). Old links and
 * bookmarks keep working:
 * - /requests, /requests?status=NEEDS_REVIEW → the "İnceleme bekleyen" (review) view
 * - /requests?q=<text> (⌘K course result) → all classes, searched for <text>
 * - /requests?program_id=<id> (⌘K programme result) → all classes of that programme
 * - kind=exams, id=<request id> and term=<id> are carried over.
 */
export default async function RequestsRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const one = (k: string) => {
    const v = sp[k];
    return Array.isArray(v) ? v[0] : v;
  };
  const q = one("q");
  const program = one("program_id") ?? one("program");
  const status = one("status");
  const search = !!(q || program);
  const out = new URLSearchParams({ view: status === "NEEDS_REVIEW" || !search ? "review" : "all" });
  if (q) out.set("q", q);
  if (program) out.set("program_id", program);
  const kind = one("kind");
  if (kind === "exams" || kind === "exam") out.set("kind", "exams");
  const id = one("id") ?? one("request");
  if (id) out.set("id", id);
  const term = one("term");
  if (term) out.set("term", term);
  redirect(`/classes?${out.toString()}`);
}
