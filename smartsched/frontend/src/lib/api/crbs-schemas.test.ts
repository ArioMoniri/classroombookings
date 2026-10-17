import { describe, expect, it } from "vitest";
import { AdminRoom, ImportResult } from "./crbs";

describe("crbs.ts response schemas keep the backend's additive fields (round-1 sweeper)", () => {
  it("ImportResult: bilingual row texts and the summary (services/bookings_users.py, T-R1-33) survive parsing", () => {
    const out = ImportResult.parse({
      created: 1,
      results: [
        { line: 1, username: "ayse", status: "success", error: null, warning: "Parola sıfırlanacak", warning_tr: "Parola sıfırlanacak", warning_en: "Password will be reset" },
        { line: 2, username: "fatih", status: "password_empty", error: "Parola yok", error_tr: "Parola yok", error_en: "Password missing" },
      ],
      summary: { rows: 2, created: 1, password_empty: 1 },
      summary_tr: "2 satır: 1 oluşturuldu, 1 parola yok",
      summary_en: "2 rows: 1 created, 1 password missing",
      summary_text: "2 satır: 1 oluşturuldu, 1 parola yok",
    });
    expect(out.results[0]?.warning).toBe("Parola sıfırlanacak");
    expect(out.results[1]?.error_tr).toBe("Parola yok");
    expect(out.results[1]?.error_en).toBe("Password missing");
    expect(out.summary).toEqual({ rows: 2, created: 1, password_empty: 1 });
    expect(out.summary_tr).toContain("1 oluşturuldu");
    expect(out.summary_en).toContain("1 created");
    expect(out.summary_text).toBe("2 satır: 1 oluşturuldu, 1 parola yok");
    // an older backend without them still parses
    expect(ImportResult.parse({ created: 0, results: [{ line: 1, status: "invalid" }] }).summary_tr).toBeUndefined();
  });

  it("AdminRoom: code_label and building_code (T-R1-34) are kept, and missing ones are allowed", () => {
    const base = { id: 7, code: "T101", display_name: "T101 Derslik", capacity: 40, is_bookable: true, room_group_id: null, room_group: null, owner_user_id: null, owner_name: null, location: null, icon: null, notes: null, photo_url: null, pos: 1, fields: {} };
    const room = AdminRoom.parse({ ...base, code_label: "T 101", building_code: "T" });
    expect(room.code_label).toBe("T 101");
    expect(room.building_code).toBe("T");
    const bare = AdminRoom.parse(base);
    expect(bare.code_label).toBeUndefined();
    expect(bare.building_code).toBeUndefined();
  });
});
