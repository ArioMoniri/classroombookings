import { describe, expect, it } from "vitest";
import { notificationHref, unreadLabel } from "./notification-model";

describe("notification links", () => {
  it("sends approvers to the inbox and requesters to My bookings", () => {
    expect(notificationHref("/approvals?request=4")).toBe("/approvals?request=4");
    expect(notificationHref("/bookings/mine?request=4")).toBe("/my-bookings?request=4");
    expect(notificationHref(null, 9)).toBe("/my-bookings?request=9");
  });
  it("drops links that leave the site", () => {
    expect(notificationHref("https://evil.example/x")).toBeNull();
    expect(notificationHref("//evil.example")).toBeNull();
  });
  it("caps the badge", () => {
    expect(unreadLabel(0)).toBeNull();
    expect(unreadLabel(120)).toBe("99+");
  });
});
