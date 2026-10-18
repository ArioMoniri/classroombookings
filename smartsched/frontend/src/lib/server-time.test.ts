/**
 * FIX-D / HB18-F01: the server sends UTC; older payloads send it naive ("2026-10-18T13:11:22"). `Date.parse` reads a
 * naive ISO date-time as *local* time, so in Europe/Istanbul (UTC+3) every helper token looked ~3 h old.
 * This file runs under TZ=Europe/Istanbul (set below, before any Date is read).
 */
process.env.TZ = "Europe/Istanbul";

import { describe, expect, it } from "vitest";
import { parseServerTime } from "./server-time";

describe("parseServerTime (TZ=Europe/Istanbul)", () => {
  it("really runs in Istanbul", () => {
    expect(new Date(Date.UTC(2026, 9, 18, 12, 0)).getHours()).toBe(15);
    // the bug this guards against: a naive string is local time for Date.parse
    expect(Date.parse("2026-10-18T13:11:22")).toBe(Date.UTC(2026, 9, 18, 10, 11, 22));
  });

  it("reads a naive server time as UTC", () => {
    expect(parseServerTime("2026-10-18T13:11:22")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22));
    expect(parseServerTime("2026-10-18T13:11:22.830")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22, 830));
    expect(parseServerTime("2026-10-18T13:11:22.572159")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22, 572));
  });

  it("keeps an explicit Z or offset", () => {
    expect(parseServerTime("2026-10-18T13:11:22Z")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22));
    expect(parseServerTime("2026-10-18T16:11:22+03:00")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22));
    expect(parseServerTime("2026-10-18T16:11:22+0300")).toBe(Date.UTC(2026, 9, 18, 13, 11, 22));
  });

  it("answers NaN for nothing or garbage", () => {
    expect(parseServerTime(null)).toBeNaN();
    expect(parseServerTime(undefined)).toBeNaN();
    expect(parseServerTime("")).toBeNaN();
    expect(parseServerTime("yarın")).toBeNaN();
  });
});
