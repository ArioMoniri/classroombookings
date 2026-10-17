import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicRoomDay, type PublicItem } from "@/lib/api/public-schedule";
import { I18nProvider } from "@/lib/i18n/provider";
import { ItemList } from "./kiosk";

const PHY: PublicItem = { kind: "class", start_period: 3, end_period: 5, start: "10:10", end: "12:50", label: { tr: "PHY 102", en: "PHY 102" } };
const ONE: PublicItem = { kind: "booked", start_period: 13, end_period: 13, start: "18:00", end: "18:40", label: { tr: "Rezerve", en: "Booked" } };

function list(sd?: { label: "both" | "period" | "time"; period_name: "schedule" | "ordinal"; time_format: "range" | "start" }) {
  render(
    <I18nProvider initialLocale="tr">
      <ItemList items={[PHY, ONE]} live={false} hhmm="09:00" emptyText="-" slotDisplay={sd} />
    </I18nProvider>,
  );
  return screen.getAllByRole("listitem").map((li) => li.querySelector("[data-slot=kiosk-when]")?.textContent);
}

describe("kiosk labels follow the administrator's slot display (W3-SLOT follow-up)", () => {
  it("keeps the time range by default and when the payload has no slot_display (an older backend)", () => {
    expect(list()).toEqual(["10:10–12:50", "18:00–18:40"]);
    expect(PublicRoomDay.parse({ date: "2026-02-18", room: { code: "A204", name: "A 204" }, items: [] }).slot_display).toBeUndefined();
  });
  it("start times only", () => {
    expect(list({ label: "time", period_name: "schedule", time_format: "start" })).toEqual(["10:10", "18:00"]);
  });
  it("periods only, as ordinals", () => {
    expect(list({ label: "period", period_name: "ordinal", time_format: "range" })).toEqual(["3.–5. ders", "13. ders"]);
  });
});
