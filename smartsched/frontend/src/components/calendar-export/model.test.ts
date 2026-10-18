/** CAL-08 sheet model: scope cards with reasons, only the configured channels, the approval fields, the sample line. */
import { describe, expect, it } from "vitest";
import { ExportOptions, Subscription, connectScopes, filePath } from "@/lib/api/calendar-export";
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
  it("CAL-13: a duty has its own bullet (code, exam time, room), never the class 'code and section' one", () => {
    expect(approvalFields({ kind: "my_duties", fields: null })).toEqual(["duty", "department"]);
    expect(approvalFields({ kind: "my_duties", fields: ["code", "room", "time", "department", "co_instructors", "link"] })).toEqual(["duty", "department", "link"]);
    expect(approvalFields({ kind: "my_duties", fields: null }, { department: false, co_instructors: true })).toEqual(["duty"]);
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

describe("CAL-B contract adapters", () => {
  it("turns {links, push} into one row per link and per push scope, plus the connections", async () => {
    const { SubscriptionsOut, parseScope } = await import("@/lib/api/calendar-export");
    const out = SubscriptionsOut.parse({
      links: [{ id: 3, scope_kind: "my_classes", scope_label: "Derslerim", last_used_at: "2026-10-17T10:10:00" }],
      push: [{ provider: "google", status: "ACTIVE", export_scopes: ["my_bookings", "department_classes:7", { kind: "my_classes" }], least_privilege: false, account_email: "a@uni.edu.tr", last_synced_at: null }],
    });
    expect(out.rows.map((r) => `${r.channel}:${r.id}`)).toEqual(["link:3", "push:push:google:my_bookings", "push:push:google:department_classes:7", "push:push:google:my_classes"]);
    expect(out.rows[2]).toMatchObject({ scope_kind: "department_classes", scope_id: 7, provider: "google", legacy_scope: true });
    expect(out.connections[0]).toMatchObject({ provider: "google", connected: true, legacy_scope: true, account_email: "a@uni.edu.tr" });
    expect(parseScope("department_classes:12")).toEqual({ kind: "department_classes", id: 12 });
    expect(parseScope(42)).toBeNull();
  });

  it("reads the options' reason object, preview and provider map", async () => {
    const { ExportOptionsIn } = await import("@/lib/api/calendar-export");
    const o = ExportOptionsIn.parse({
      enabled: true,
      scopes: [
        { kind: "department_classes", available: true, reason: null, departments: [{ id: 7, name: "Psikoloji" }, { id: 8, name: "Felsefe" }], default_department_id: 7, preview: { upcoming_count: 310, sample: { summary: "PSY 101", location: "A 1", start: "2026-10-19T09:00:00", end: "2026-10-19T10:00:00", text_tr: "PSY 101 — A 1 — Pzt 09:00–10:00" }, fields: [{ key: "course_code" }, { key: "section" }, { key: "room" }] } },
        { kind: "my_classes", available: false, reason: { code: "not_linked", message_tr: "bağlı değil", message_en: "not linked" } },
      ],
      channels: { push: { google: { label: "Google", configured: true }, freshness_tr: "x" }, link: { available: false }, file: { available: true } },
    });
    expect(o.channels).toEqual({ link: false, file: true, push: [{ provider: "google", configured: true, connected: false, scopes: [] }] });
    const c = scopeChoices(o, "tr");
    expect(c.map((x) => x.key)).toEqual(["my_classes", "department_classes:7", "department_classes:8"]);
    expect(c[0]).toMatchObject({ available: false, reason: "not_linked" });
    expect(c[1]).toMatchObject({ upcoming: 310, fields: ["code", "room"] });
    expect(c[1]!.sample?.text_tr).toBe("PSY 101 — A 1 — Pzt 09:00–10:00");
    expect(c[2]!.sample).toBeNull();
    expect(sampleLine(c[1]!.sample!, "tr", "Şube")).toBe("PSY 101 — A 1 — Pzt 09:00–10:00");
  });
});

describe("POST /calendar/subscriptions answer (API.md)", () => {
  it("parses the contract's create answer, preview included", async () => {
    const { SubscriptionCreated } = await import("@/lib/api/calendar-export");
    const made = SubscriptionCreated.parse({
      id: 41, label: "iPhone", hint: "x9Qa", channel: "link", scope_kind: "my_classes", scope_id: null, url_known: true, token: "sst_x",
      url: "https://r.uni.edu.tr/api/v1/calendar/feeds/sst_x/classes.ics",
      urls: { https: "https://r.uni.edu.tr/api/v1/calendar/feeds/sst_x/classes.ics", webcal: "webcal://r.uni.edu.tr/api/v1/calendar/feeds/sst_x/classes.ics", google: "https://calendar.google.com/calendar/r?cid=x", outlook: "https://outlook.office.com/calendar/0/addfromweb?url=x" },
      preview: { scope_kind: "my_classes", upcoming_count: 13, sample: { summary: "PSY 262 · Şube 1", location: "C 504", start: "2026-02-23T13:30:00", end: "2026-02-23T15:50:00" }, fields: [{ key: "course_code", label_tr: "Ders kodu", label_en: "Course code" }] },
    });
    expect(made.urls.webcal).toMatch(/^webcal:/);
  });
});

describe("connectScopes (API.md: the new sheet always sends scopes on connect)", () => {
  it("keeps the given scopes once each, in order", () => {
    expect(connectScopes(["my_classes", "department_classes:28", "my_classes"])).toEqual(["my_classes", "department_classes:28"]);
  });
  it("never sends an empty or missing list: a bookings-only legacy connection reconnects with my_bookings", () => {
    expect(connectScopes([])).toEqual(["my_bookings"]);
    expect(connectScopes(null)).toEqual(["my_bookings"]);
    expect(connectScopes([" ", ""])).toEqual(["my_bookings"]);
  });
});

describe("CAL-13 Sınav görevlerim", () => {
  const withDuties = ExportOptions.parse({
    scopes: [
      { kind: "my_duties", available: true, upcoming: 7 },
      { kind: "my_bookings", available: true, upcoming: 2 },
      { kind: "my_classes", available: true, upcoming: 28 },
    ],
  });

  it("is the last card, after Rezervasyonlarım", () => {
    expect(scopeChoices(withDuties, "tr").map((x) => x.key)).toEqual(["my_classes", "my_bookings", "my_duties"]);
    expect(scopeChoices(withDuties, "tr").at(-1)).toMatchObject({ kind: "my_duties", available: true, upcoming: 7 });
  });

  it("has its own file, push scope and file name", () => {
    expect(filePath("my_duties")).toBe("/calendar/export/duties.ics");
    expect(pushScope("my_duties", null)).toBe("my_duties");
    expect(fileName("my_duties", "2026-FİNAL")).toBe("sinav-gorevlerim-2026-final.ics");
  });

  it("never sends the other invigilators' names", () => {
    expect(approvalFields({ kind: "my_duties", fields: null }, { co_instructors: true })).not.toContain("co_instructors");
  });
});
