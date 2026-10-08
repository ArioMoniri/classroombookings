import { describe, expect, it } from "vitest";
import { HttpError } from "@/lib/api/client";
import { crbsError } from "@/lib/api/crbs";
import { translate } from "@/lib/i18n";
import { bookingErrorMessage } from "./booking-errors";

const tr = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("tr", k, v);
const en = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("en", k, v);

/* the body POST /bookings returns for A 101, Monday 16 Feb 2026, P4 (recorded from the real backend) */
const timetable = new HttpError(409, "409 Conflict", {
  detail: {
    code: "conflict",
    message: "A 101 on 16.02.2026 P4-P5 is held by the published timetable (FZT 132)",
    conflict: { kind: "timetable", room_id: 1, date: "2026-02-16", start_period: 4, end_period: 5, label: "FZT 132", id: 1340, run_id: 1, series_id: null },
  },
});

describe("booking refusals are explained in the user's language", () => {
  const ctx = { roomName: (id: number) => (id === 1 ? "A 101" : undefined), formatDate: (d: string) => d.split("-").reverse().join(".") };
  it("a slot held by the published timetable", () => {
    const e = crbsError(timetable);
    expect(e).toMatchObject({ status: 409, code: "conflict" });
    expect(e.conflict?.label).toBe("FZT 132");
    expect(bookingErrorMessage(e, tr, ctx)).toBe("A 101, 16.02.2026 P4–P5: yayımlanmış ders programında FZT 132 dersi var; bu saat rezerve edilemez.");
    expect(bookingErrorMessage(e, en, ctx)).toBe("A 101 on 16.02.2026 P4–P5 is held by FZT 132 in the published timetable, so it cannot be booked.");
  });
  it("limits, holidays, maintenance and validation", () => {
    const limit = crbsError(new HttpError(409, "", { detail: { code: "max_active_bookings", message: "…", limit: 3 } }));
    expect(bookingErrorMessage(limit, tr)).toContain("3 etkin rezervasyonunuz var");
    const hol = crbsError(new HttpError(409, "", { detail: { code: "holiday", message: "23.04.2026 is a holiday" } }));
    expect(bookingErrorMessage(hol, tr)).toBe("O tarih tatil.");
    const maint = crbsError(new HttpError(503, "Sistem bakımda", "Sistem bakımda"));
    expect(maint.code).toBe("maintenance");
    expect(bookingErrorMessage(maint, tr)).toBe("Rezervasyonlar bakımda: Sistem bakımda");
    const val = crbsError(new HttpError(422, "x", [{ msg: "notes are limited to 255 characters" }]));
    expect(bookingErrorMessage(val, en)).toBe("Please check the form: notes are limited to 255 characters");
    expect(bookingErrorMessage(crbsError(new HttpError(0, "Failed to fetch")), tr)).toContain("Sunucuya ulaşılamıyor");
    expect(bookingErrorMessage(crbsError(new HttpError(409, "", { detail: { code: "edit_room_id", message: "" } })), tr)).toBe("Rezervasyonun bu kısmını değiştiremezsiniz.");
  });
});
