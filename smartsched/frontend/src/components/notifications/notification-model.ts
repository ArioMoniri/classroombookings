/**
 * In-app notifications (GET /me/notifications): where a notification opens and how the unread count reads.
 * Pure functions, unit-tested.
 */

/**
 * The backend links approvers to `/approvals?request=<id>` and requesters to `/bookings/mine?request=<id>`
 * (docs/product/wave1-api.md §4). This frontend's "My bookings" is /my-bookings, and the requester timeline
 * lives on /approvals (tab "My requests") until My bookings mounts it, so requester links go there.
 * Anything that is not a same-origin path is dropped (no open redirects from stored text).
 */
export function notificationHref(link: string | null | undefined, requestId?: number | null): string | null {
  if (!link) return requestId ? `/approvals?tab=mine&request=${requestId}` : null;
  if (!link.startsWith("/") || link.startsWith("//")) return null;
  const [path = "", query = ""] = link.split("?");
  const params = new URLSearchParams(query);
  if (path === "/bookings/mine" || path === "/my-bookings") {
    const req = params.get("request") ?? (requestId ? String(requestId) : null);
    return req ? `/approvals?tab=mine&request=${encodeURIComponent(req)}` : "/my-bookings";
  }
  return link;
}

/** "3", "99+" (plain numerals, A7); `null` hides the badge. */
export function unreadLabel(count: number): string | null {
  if (count <= 0) return null;
  return count > 99 ? "99+" : String(count);
}

/** Minutes/hours/days ago, in the user's language (Intl, so every CRBS language works). */
export function relativeTime(when: Date, now: Date, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const mins = Math.round((when.getTime() - now.getTime()) / 60_000);
  if (Math.abs(mins) < 60) return rtf.format(mins, "minute");
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  return rtf.format(Math.round(hours / 24), "day");
}
