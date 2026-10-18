/** RF-11 deep links of the e-mails: `?booking=<id>` (and `?series=<id>`, the thread of a series' e-mails) open the
 *  booking's detail sheet on /my-bookings and /bookings; the backend's `/bookings/mine` links land on /my-bookings. */
import { describe, expect, it } from "vitest";
import { notificationHref } from "@/components/notifications/notification-model";
import { deepLinkedBookingId, myBookingsHref, withoutDeepLink } from "./deep-link-model";

describe("deep links from the e-mails", () => {
  it("reads a positive booking id and ignores anything else", () => {
    expect(deepLinkedBookingId(new URLSearchParams("series=8&booking=412"))).toBe(412);
    expect(deepLinkedBookingId(new URLSearchParams("booking=0"))).toBeNull();
    expect(deepLinkedBookingId(new URLSearchParams("booking=12abc"))).toBeNull();
    expect(deepLinkedBookingId(new URLSearchParams("series=8"))).toBeNull();
    expect(deepLinkedBookingId(new URLSearchParams(""))).toBeNull();
  });

  it("drops booking and series from the address once the sheet is open, keeping the rest", () => {
    expect(withoutDeepLink("/bookings", new URLSearchParams("date=2026-02-19&series=8&booking=412"))).toBe("/bookings?date=2026-02-19");
    expect(withoutDeepLink("/my-bookings", new URLSearchParams("booking=412"))).toBe("/my-bookings");
  });

  it("maps the backend's /bookings/mine links to /my-bookings with request, booking and series", () => {
    expect(myBookingsHref({ series: "8", booking: "412", utm: "x" })).toBe("/my-bookings?series=8&booking=412");
    expect(myBookingsHref({ request: ["7", "9"] })).toBe("/my-bookings?request=7");
    expect(myBookingsHref({})).toBe("/my-bookings");
  });

  it("keeps the booking of an in-app notice link", () => {
    expect(notificationHref("/bookings/mine?series=8&booking=412")).toBe("/my-bookings?series=8&booking=412");
    expect(notificationHref("/bookings/mine?request=7")).toBe("/my-bookings?request=7");
    expect(notificationHref("/bookings?series=8&booking=412")).toBe("/bookings?series=8&booking=412");
  });
});
