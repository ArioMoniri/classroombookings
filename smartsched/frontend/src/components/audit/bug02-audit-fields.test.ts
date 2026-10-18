/**
 * BUG-02 (launch video, 2026-10-18): the audit diff table showed raw field names (`room_id`) and raw ids (14 → 17).
 * The field column reads a label in the UI language ("Derslik" / "Room"); an id the backend named for this viewer
 * (`refs`, app/services/audit_refs.py) reads as the name, an id it did not name stays a number.
 */
import { describe, expect, it } from "vitest";
import { AUDIT_FIELD_KEYS, diffRows, diffValueText, fieldLabel } from "./audit-model";
import { translate, type MessageKey } from "@/lib/i18n";

const tr = (k: MessageKey, v?: Record<string, string | number>) => translate("tr", k, v);
const en = (k: MessageKey, v?: Record<string, string | number>) => translate("en", k, v);
const RAW = /^[a-z]+(_[a-z]+)+$|_id\b/;

describe("BUG-02 audit diff labels", () => {
  it("names the booking fields in Turkish and English", () => {
    expect(fieldLabel("room_id", tr)).toBe("Derslik");
    expect(fieldLabel("room_id", en)).toBe("Room");
    expect(fieldLabel("user_id", tr)).toBe("Kişi");
    expect(fieldLabel("period_id", tr)).toBe("Ders saati");
    expect(fieldLabel("start_period", tr)).toBe("İlk ders saati");
    expect(fieldLabel("cancel_reason", en)).toBe("Cancellation reason");
  });
  it("never shows a snake_case key, not even for a field without a label", () => {
    for (const f of Object.keys(AUDIT_FIELD_KEYS)) {
      expect(fieldLabel(f, tr), f).not.toMatch(RAW);
      expect(fieldLabel(f, en), f).not.toMatch(RAW);
    }
    expect(fieldLabel("max_active_bookings", tr)).toBe("Max active bookings");
    expect(fieldLabel("legacy_crbs_room_id", en)).toBe("Legacy crbs room");
  });
  it("shows the names the backend resolved for this viewer, and the number otherwise", () => {
    const e = { diff: { room_id: [14, 17], user_id: [5, 9] }, before: null, after: null, refs: { room_id: { "14": "A 101", "17": "A 106" }, user_id: { "9": "Ayşe Yılmaz" } } };
    const [room, user] = diffRows(e);
    expect(diffValueText(room!.field, room!.before, e.refs)).toBe("A 101");
    expect(diffValueText(room!.field, room!.after, e.refs)).toBe("A 106");
    expect(diffValueText(user!.field, user!.after, e.refs)).toBe("Ayşe Yılmaz");
    expect(diffValueText(user!.field, user!.before, e.refs)).toBe("5"); // not visible to this viewer: the id only
    expect(diffValueText("notes", null, e.refs)).toBe("—");
    expect(diffValueText("is_bookable", true, undefined, { yes: "evet", no: "hayır" })).toBe("evet");
  });
});
