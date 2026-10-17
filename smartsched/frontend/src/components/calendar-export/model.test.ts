/** CAL-08 sheet model: scope cards with reasons, only the configured channels, the approval fields, the sample line. */
import { describe, expect, it } from "vitest";
import { ExportOptions, Subscription } from "@/lib/api/calendar-export";
import {
  approvalFields,
  channelChoices,
  fileName,
  findPushRow,
  legacyProviders,
  manageRows,
  nextFocus,
  notLinked,
  parseUtc,
  pushProgress,
  pushScope,
  readPending,
  relativeWhen,
  sampleLine,
  scopeChoices,
  subscribeLinks,
} from "./model";

const sample = { course_code: "PSY 262", section: "1", location: "A 308", starts_at: "2026-10-19T10:30:00Z", ends_at: "2026-10-19T12:50:00Z" };

const options = ExportOptions.parse({
  enabled: true,
  term: { id: 3, name: "2026 Bahar", slug: "2026-bahar" },
  linked: true,
  scopes: [
    { kind: "my_bookings", available: true, upcoming: 2 },
    { kind: "my_classes", available: true, upcoming: 28, hours: 42, sample },
    {
      kind: "department_classes",
      available: true,
      departments: [
        { id: 7, name: "Psikoloji", available: true, upcoming: 310 },
        { id: 9, name: "Sosyoloji", available: false, reason: "department_not_allowed" },
      ],
    },
    { kind: "room", available: true },
  ],
  channels: {
    link: true,
    file: true,
    push: [
      { provider: "google", configured: true, connected: false },
      { provider: "microsoft", configured: false, connected: false },
      { provider: "caldav", configured: true, connected: false },
    ],
  },
  consent: { purpose: "calendar_sync", required: true, granted: false },
});

describe("scopeChoices", () => {
  it("orders Derslerim, the departments, Rezervasyonlarım and drops unknown scopes", () => {
    const c = scopeChoices(options, "tr");
    expect(c.map((x) => x.key)).toEqual(["my_classes", "department_classes:7", "department_classes:9", "my_bookings"]);
    expect(c[0]).toMatchObject({ available: true, hours: 42, upcoming: 28 });
  });

  it("keeps a closed department as a disabled card with its reason", () => {
    const d = scopeChoices(options, "tr").find((x) => x.key === "department_classes:9");
    expect(d).toMatchObject({ available: false, reason: "department_not_allowed", departmentName: "Sosyoloji" });
  });

  it("shows the backend's own sentence for an unknown code, in the reader's language", () => {
    const o = ExportOptions.parse({ scopes: [{ kind: "my_classes", available: false, reason: "quota", reason_tr: "Kota doldu", reason_en: "Quota reached" }] });
    expect(scopeChoices(o, "tr")[0]).toMatchObject({ reason: "other", reasonText: "Kota doldu" });
    expect(scopeChoices(o, "en")[0]).toMatchObject({ reason: "other", reasonText: "Quota reached" });
  });

  it("flags an account that is not linked to an instructor", () => {
    expect(notLinked(options)).toBe(false);
    expect(notLinked(ExportOptions.parse({ scopes: [{ kind: "my_classes", available: false, reason: "not_linked" }] }))).toBe(true);
    expect(notLinked(ExportOptions.parse({ linked: false }))).toBe(true);
  });
});

describe("channelChoices", () => {
  it("lists only configured, known providers first, then the link and the file", () => {
    expect(channelChoices(options).map((c) => (c.kind === "push" ? `push:${c.provider}` : c.kind))).toEqual(["push:google", "link", "file"]);
  });

  it("never offers a channel the organisation turned off", () => {
    const o = ExportOptions.parse({ channels: { link: false, file: true, push: [] } });
    expect(channelChoices(o).map((c) => c.kind)).toEqual(["file"]);
  });

  it("treats a REAUTH connection as not connected", () => {
    const o = ExportOptions.parse({ channels: { push: [{ provider: "google", configured: true, connected: true, status: "REAUTH" }] } });
    expect(channelChoices(o)[0]).toMatchObject({ kind: "push", connected: false });
  });
});

describe("approvalFields", () => {
  it("follows the doc: code + section, room, day and time, department; co-instructors off by default", () => {
    expect(approvalFields({ kind: "my_classes", fields: null })).toEqual(["code", "room", "time", "department"]);
  });
  it("follows the admin's allow-list", () => {
    expect(approvalFields({ kind: "my_classes", fields: null }, { title: true, department: false, co_instructors: true, link: true })).toEqual(["code", "title", "room", "time", "co_instructors", "link"]);
  });
  it("prefers the backend's list for the scope and drops unknown keys", () => {
    expect(approvalFields({ kind: "my_classes", fields: ["code", "room", "student_names"] })).toEqual(["code", "room"]);
  });
  it("has its own list for bookings", () => {
    expect(approvalFields({ kind: "my_bookings", fields: null })).toEqual(["booking_title", "room", "time"]);
  });
});

describe("sampleLine", () => {
  it("renders the doc's example in Istanbul time", () => {
    expect(sampleLine(sample, "tr", "Şube")).toBe("PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50");
    expect(sampleLine(sample, "en", "Section")).toBe("PSY 262 · Section 1 — A 308 — Mon 13:30–15:50");
  });
  it("falls back to the summary without a course code", () => {
    expect(sampleLine({ summary: "Toplantı", starts_at: "2026-10-19T10:30:00Z", ends_at: "2026-10-19T11:00:00Z" }, "tr", "Şube")).toBe("Toplantı — Pzt 13:30–14:00");
  });
});

describe("relativeWhen", () => {
  const now = new Date("2026-10-17T12:00:00Z"); // 15:00 in Istanbul
  const words = { today: "bugün", yesterday: "dün" };
  it("says today with the Turkish locative suffix", () => {
    expect(relativeWhen("2026-10-17T10:10:00", "tr", words, now)).toEqual({ label: "bugün 13:10", at: "13:10'da" });
    expect(relativeWhen("2026-10-17T11:05:00Z", "tr", words, now)).toEqual({ label: "bugün 14:05", at: "14:05'te" });
  });
  it("says yesterday and older dates", () => {
    expect(relativeWhen("2026-10-16T06:00:00Z", "tr", words, now)?.label).toBe("dün 09:00");
    expect(relativeWhen("2026-10-12T06:00:00Z", "en", { today: "today", yesterday: "yesterday" }, now)?.label).toBe("12 Oct 09:00");
  });
  it("is null without a timestamp", () => {
    expect(relativeWhen(null, "tr", words, now)).toBeNull();
    expect(parseUtc("nope")).toBeNull();
  });
});

describe("links and push", () => {
  it("builds the deep links from the https link when the backend sends none", () => {
    const l = subscribeLinks({ https: "https://plan.uni.edu.tr/api/v1/calendar/feeds/sst_x/classes.ics" }, "Derslerim");
    expect(l.webcal).toBe("webcal://plan.uni.edu.tr/api/v1/calendar/feeds/sst_x/classes.ics");
    expect(l.google).toContain("calendar.google.com/calendar/r?cid=webcal%3A%2F%2F");
    expect(l.outlook).toContain("outlook.office.com/calendar/0/addfromweb?url=https%3A%2F%2F");
    expect(subscribeLinks({ https: "https://a/x.ics", google: "https://g" }, "x").google).toBe("https://g");
  });

  it("reads push progress and finds the row of the scope", () => {
    const rows = [
      Subscription.parse({ id: 1, scope_kind: "my_classes", channel: "push", provider: "google", synced: 12, total: 28, pending_jobs: 1 }),
      Subscription.parse({ id: 2, scope_kind: "department_classes", scope_id: 7, channel: "push", provider: "google" }),
    ];
    expect(pushProgress(findPushRow(rows, "google", "my_classes", null))).toEqual({ n: 12, m: 28, done: false });
    expect(findPushRow(rows, "google", "department_classes", 7)?.id).toBe(2);
    expect(findPushRow(rows, "google", "department_classes", 8)).toBeUndefined();
    expect(pushProgress(Subscription.parse({ id: 3, scope_kind: "my_classes", channel: "push", last_synced_at: "2026-10-17T11:05:00Z", pending_jobs: 0 }))).toEqual({ n: 0, m: 0, done: true });
    expect(pushScope("department_classes", 7)).toBe("department_classes:7");
    expect(pushScope("my_classes", null)).toBe("my_classes");
  });

  it("flags old broad grants for a reconnect with fewer permissions", () => {
    const o = ExportOptions.parse({ channels: { push: [{ provider: "google", configured: true, connected: true, legacy_scope: true }] } });
    expect([...legacyProviders(o, [])]).toEqual(["google"]);
  });

  it("reads a pending OAuth round trip once and ignores stale ones", () => {
    const now = 1_000_000_000;
    expect(readPending(JSON.stringify({ provider: "google", kind: "my_classes", departmentId: null, at: now - 1000 }), now)).toMatchObject({ provider: "google", kind: "my_classes" });
    expect(readPending(JSON.stringify({ provider: "google", kind: "my_classes", at: now - 31 * 60_000 }), now)).toBeNull();
    expect(readPending("{bad", now)).toBeNull();
    expect(readPending(JSON.stringify({ provider: "yahoo", kind: "my_classes", at: now }), now)).toBeNull();
  });
});

describe("manage list", () => {
  const rows = manageRows([
    Subscription.parse({ id: 5, scope_kind: "my_bookings", channel: "link" }),
    Subscription.parse({ id: 3, scope_kind: "my_classes", channel: "link" }),
    Subscription.parse({ id: 4, scope_kind: "my_classes", channel: "push", provider: "google" }),
  ]);
  it("orders by scope, push before link", () => {
    expect(rows.map((r) => r.id)).toEqual([4, 3, 5]);
  });
  it("moves focus to the next row, else the previous, else nowhere", () => {
    expect(nextFocus(rows, 4)).toBe(3);
    expect(nextFocus(rows, 5)).toBe(3);
    expect(nextFocus(rows.slice(0, 1), 4)).toBeNull();
  });
  it("names the file like the backend", () => {
    expect(fileName("my_classes", "2026-bahar")).toBe("derslerim-2026-bahar.ics");
    expect(fileName("department_classes", "2026-bahar", "Psikoloji Bölümü")).toBe("bolum-psikoloji-bolumu-2026-bahar.ics");
  });
});
