import { redirect } from "next/navigation";

const AREAS = ["identity", "email", "calendar", "channels", "automation", "ai"];

/** Deep link `/admin/integrations/<card key>` (docs/design/v3/integrations.md §3): the gallery with that card's
 *  setup sheet open (`?area=<area>&setup=<key>`). */
export default async function IntegrationDeepLink({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const card = decodeURIComponent(key);
  if (!/^[a-z0-9_.-]{1,64}$/.test(card)) redirect("/admin/integrations");
  const area = card.split(".")[0];
  const q = new URLSearchParams();
  if (AREAS.includes(area)) q.set("area", area);
  q.set("setup", card);
  redirect(`/admin/integrations?${q.toString()}`);
}
