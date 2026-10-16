import { describe, expect, it } from "vitest";
import { dueTone, effectSentences, erasureCounts, Inventory, inventoryCsv, Notice, noticeVersions, retentionErrors, Withdrawal } from "@/lib/api/kvkk";
import { parseMarkdown } from "@/components/privacy/markdown";
import { shouldGate } from "@/components/privacy/notice-gate";

describe("KVKK helpers", () => {
  it("withdrawal effects: the server's sentences in the reader's language, capitalised the Turkish way", () => {
    const res = Withdrawal.parse({ removed_photo: 1, effects: [{ code: "photo_deleted", count: 1, message_en: "your profile photo was deleted", message_tr: "profil fotoğrafınız silindi" }, { code: "x", count: null, message_en: "ok.", message_tr: "işlem tamam." }] });
    expect(res.removed_channels).toBe(0);
    expect(res.ai_excluded).toBe(false);
    expect(effectSentences(res.effects, "tr")).toEqual(["Profil fotoğrafınız silindi.", "İşlem tamam."]);
    expect(effectSentences(res.effects, "en")).toEqual(["Your profile photo was deleted.", "Ok."]);
    expect(effectSentences(res.effects, "de")).toEqual(["Your profile photo was deleted.", "Ok."]);
    expect(Withdrawal.parse({}).effects).toEqual([]);
  });

  it("retention 422: errors[] by field (first per field), the numbers kept; non-field details → nothing", () => {
    const by = retentionErrors({
      code: "retain_days",
      field: "retain_days",
      errors: [
        { code: "retain_days", field: "retain_days", message: "x", message_en: "x", message_tr: "y", floor_days: 365, max_days: 36500 },
        { code: "below_floor", field: "retain_days", message_en: "second", message_tr: "ikinci" },
        { code: "action", field: "action", message_en: "a", message_tr: "b", allowed: ["anonymise"] },
        { code: "weird", field: "nope", message_en: "?", message_tr: "?" },
      ],
    });
    expect(by.retain_days).toEqual({ code: "retain_days", field: "retain_days", message_en: "x", message_tr: "y", floor_days: 365, max_days: 36500 });
    expect(by.action?.allowed).toEqual(["anonymise"]);
    expect(Object.keys(by).sort()).toEqual(["action", "retain_days"]);
    expect(retentionErrors({ code: "legal_hold", field: "legal_hold", message: "legal_hold: true or false", message_tr: "yasal saklama: evet ya da hayır" }).legal_hold?.message_en).toBe("legal_hold: true or false");
    expect(retentionErrors({ code: "forbidden", message: "no" })).toEqual({});
    expect(retentionErrors(null)).toEqual({});
  });

  it("colours the deadline: overdue, the last week, the rest; closed requests have none", () => {
    expect(dueTone({ status: "OPEN", overdue: true, days_left: -2 })).toBe("overdue");
    expect(dueTone({ status: "OPEN", overdue: false, days_left: 5 })).toBe("soon");
    expect(dueTone({ status: "IN_PROGRESS", overdue: false, days_left: 20 })).toBe("ok");
    expect(dueTone({ status: "DONE", overdue: false, days_left: null })).toBe("closed");
  });

  it("lists erasure counts, largest first", () => {
    expect(erasureCounts({ counts: { consents: 1, bookings_anonymised: 12, user_channels: 0 }, partial: true })).toEqual([
      { key: "bookings_anonymised", n: 12 },
      { key: "consents", n: 1 },
      { key: "user_channels", n: 0 },
    ]);
    expect(erasureCounts(null)).toEqual([]);
  });

  it("writes the inventory CSV with a BOM, quoted cells and the retention state", () => {
    const inv = Inventory.parse({
      generated_at: "2026-10-16T06:00:00Z",
      classes: [
        { code: "audit", label_tr: "Denetim kaydı: kim, ne", label_en: "Audit log", tables: ["audit_events"], rows: { audit_events: 40 }, legal_basis: "KVKK m.5/2(ç)", retention: { data_class: "audit", retain_days: 730, floor_days: 365, action: "delete", enabled: false, legal_hold: false } },
        { code: "checkin", label_tr: "Yoklama", label_en: "Check-ins", tables: [], rows: {}, legal_basis: "-", retention: null, kept: "tutulmaz" },
      ],
    });
    const csv = inventoryCsv(inv, "tr");
    expect(csv.startsWith("﻿Kod,Veri,")).toBe(true);
    expect(csv).toContain('audit,"Denetim kaydı: kim, ne",audit_events,40,KVKK m.5/2(ç),730,delete,0,0');
    expect(csv).toContain("checkin,Yoklama,,0,-,tutulmaz,,,");
  });

  it("groups notices by version, TR and EN side by side", () => {
    const n = (id: number, version: number, language: string, published: boolean) => Notice.parse({ id, version, language, title: "t", body_md: "b", published_at: published ? "2026-10-16T06:00:00" : null });
    const v = noticeVersions([n(1, 1, "tr", true), n(2, 2, "tr", false), n(3, 1, "en", true)]);
    expect(v.map((x) => [x.version, x.tr?.id, x.en?.id ?? null, x.published])).toEqual([
      [2, 2, null, false],
      [1, 1, 3, true],
    ]);
  });

  it("renders the notice's markdown blocks without HTML", () => {
    expect(parseMarkdown("# Başlık\n\nBir **paragraf**\ndevamı\n\n- bir\n- iki\n1. ilk\n<script>x</script>")).toEqual([
      { kind: "h1", text: "Başlık" },
      { kind: "p", text: "Bir **paragraf** devamı" },
      { kind: "ul", items: ["bir", "iki"] },
      { kind: "ol", items: ["ilk"] },
      { kind: "p", text: "<script>x</script>" },
    ]);
  });

  it("the first-login sheet blocks until read, but never on /admin/kvkk and an admin may postpone it", () => {
    const base = { needsAck: true, hasNotice: true, pathname: "/bookings", admin: false, postponed: false };
    expect(shouldGate(base)).toBe(true);
    expect(shouldGate({ ...base, needsAck: false })).toBe(false);
    expect(shouldGate({ ...base, pathname: "/admin/kvkk" })).toBe(false);
    expect(shouldGate({ ...base, admin: true, postponed: true })).toBe(false);
    expect(shouldGate({ ...base, postponed: true })).toBe(true);
  });
});
