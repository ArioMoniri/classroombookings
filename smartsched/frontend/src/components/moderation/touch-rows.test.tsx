/** MOBILE.md M-02 on the lane-B phone routes (loop-r1-laneB2): stacked controls get 44 px tap zones on coarse
 *  pointers so a neighbour's hit area never cuts another's; the term is named, not coded. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { SIBLING_CHIP_CLASS } from "@/components/approvals/approvals-view";
import { BOOKING_ROW_CLASS, BOOKING_ROW_CONTROL_CLASS } from "@/components/bookings/my-bookings-view";
import { TermGroup } from "./request-timeline";

const term = { term_id: 1, term_code: "2026-BAHAR", term_name: "Bahar 2026", run: null, source: "planner" as const, counts: {}, match_rate: null, items: [], bookings: [], learned: null };

describe("touch rows (M-02)", () => {
  it("the term group names the term and its collapse button is 44 px on touch", () => {
    render(
      <I18nProvider initialLocale="tr">
        <TermGroup g={term} canEdit={false} />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Bahar 2026");
    const btn = screen.getByRole("button", { name: "Bahar 2026 daralt" });
    expect(btn.className).toContain("pointer-coarse:size-11");
  });
  it("the approvals sibling chips and the My bookings row controls are 44 px on touch", () => {
    expect(SIBLING_CHIP_CLASS).toContain("pointer-coarse:h-11");
    expect(BOOKING_ROW_CONTROL_CLASS).toContain("pointer-coarse:min-h-11");
    expect(BOOKING_ROW_CLASS).toContain("pointer-coarse:gap-5");
  });
});
