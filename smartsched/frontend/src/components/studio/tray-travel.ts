/** Review tray → rule list hand-off (motion audit T5, motion.md §3.4). */
import type { TrayItem } from "./studio-store";

/** Lists longer than this get no insert / remove animation (motion_designer §4). */
export const TRAY_ANIMATE_MAX = 40;
/** At most this many accepted cards travel into the rule list at once (motion.md §3.4). */
export const TRAVEL_MAX = 12;
/** The shared `layoutId` of a tray card and the rule it becomes. */
export const trayTravelId = (key: string) => `tray-travel-${key}`;

/**
 * Created rule id → the travel id of the tray card it came from. Only a one-to-one batch of at most
 * TRAVEL_MAX travels; otherwise (some rejected, "Accept all" of many) nothing travels and the count is announced.
 */
export function travelPairs(items: readonly TrayItem[], created: readonly number[]): Record<number, string> {
  const rules = items.filter((i) => i.type === "rule");
  if (rules.length === 0 || rules.length > TRAVEL_MAX || created.length !== rules.length) return {};
  return Object.fromEntries(rules.map((it, i) => [created[i], trayTravelId(it.key)]));
}
