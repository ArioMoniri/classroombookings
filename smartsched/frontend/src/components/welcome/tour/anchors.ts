/**
 * `data-tour` anchors (spec §13). The sidebar, the phone tab bar and the "Daha" list render `nav-*` anchors from one
 * generic attribute (`data-tour={tourAnchorFor(item.href)}`); other controls carry a literal `data-tour`.
 * Several elements may carry one anchor (sidebar + tab bar): the visible one wins.
 */

/** Set on <html> while a tour runs: the global shortcuts and ⌘K pause (use-global-shortcuts.ts reads it). */
export const TOUR_RUNNING_ATTR = "data-tour-running";

/** nav href → anchor name (`/moderation/me` → `nav-my-requests`, `/admin/welcome` → `nav-welcome-admin`). */
const NAV_ANCHORS: Readonly<Record<string, string>> = {
  "/reserve": "nav-reserve",
  "/bookings": "nav-bookings",
  "/my-bookings": "nav-my-bookings",
  "/find-room": "nav-find-room",
  "/moderation/me": "nav-my-requests",
  "/approvals": "nav-approvals",
  "/dashboard": "nav-dashboard",
  "/onboarding": "nav-onboarding",
  "/requests": "nav-requests",
  "/generate": "nav-generate",
  "/timetable": "nav-timetable",
  "/moderation": "nav-moderation",
  "/runs": "nav-runs",
  "/analytics/heatmap": "nav-heatmap",
  "/admin": "nav-admin",
  "/admin/integrations": "nav-integrations",
  "/admin/welcome": "nav-welcome-admin",
};

export function tourAnchorFor(href: string): string | undefined {
  return NAV_ANCHORS[href.split(/[?#]/)[0] ?? href];
}

export function visible(el: HTMLElement): boolean {
  if (!el.isConnected) return false;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const style = window.getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none";
}

/** The visible element for an anchor. On phones a nav anchor that lives under "Daha" points at the Daha tab. */
export function findAnchor(anchor: string): HTMLElement | null {
  const all = [...document.querySelectorAll<HTMLElement>(`[data-tour="${CSS.escape(anchor)}"]`)];
  const hit = all.find(visible);
  if (hit) return hit;
  if (anchor.startsWith("nav-")) {
    const more = document.querySelector<HTMLElement>('[data-testid="open-drawer"]');
    if (more && visible(more)) return more;
  }
  return null;
}

/** Wait (MutationObserver + a poll for layout changes) until the anchor is visible, at most `timeoutMs` (spec: 3 s). */
export function waitForAnchor(anchor: string, timeoutMs = 3000, signal?: AbortSignal): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const now = findAnchor(anchor);
    if (now) return resolve(now);
    let done = false;
    const finish = (el: HTMLElement | null) => {
      if (done) return;
      done = true;
      observer.disconnect();
      window.clearInterval(poll);
      window.clearTimeout(timer);
      resolve(el);
    };
    const check = () => {
      const el = findAnchor(anchor);
      if (el) finish(el);
    };
    const observer = new MutationObserver(check);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-tour", "class", "style", "hidden"] });
    const poll = window.setInterval(check, 150);
    const timer = window.setTimeout(() => finish(null), timeoutMs);
    signal?.addEventListener("abort", () => finish(null));
  });
}

export function isFocusable(el: HTMLElement | null): el is HTMLElement {
  if (!el || !el.isConnected) return false;
  if (el.matches("a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")) return true;
  return false;
}
