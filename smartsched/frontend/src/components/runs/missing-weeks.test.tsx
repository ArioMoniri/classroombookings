import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { MissingWeeks, missingOnlyWeek } from "./missing-weeks";

describe("week bottleneck (Phase 9: events missing only one week)", () => {
  it("reads stats.missing_only_week, biggest first, ignoring junk", () => {
    expect(missingOnlyWeek({ missing_only_week: { "1": 2, "7": 5, x: 3, "4": 0 } })).toEqual([{ week: 7, count: 5 }, { week: 1, count: 2 }]);
    expect(missingOnlyWeek({})).toEqual([]);
  });

  it("names the week and links to it in the timetable", () => {
    render(
      <I18nProvider initialLocale="tr">
        <MissingWeeks runId={9} stats={{ missing_only_week: { "1": 2 } }} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("missing-weeks")).toHaveTextContent("2 ders 1. hafta dışında her hafta yerleşti");
    expect(screen.getByRole("link", { name: "1. haftayı aç" })).toHaveAttribute("href", "/timetable?run=9&week=1");
  });

  it("renders nothing when every placed class has all its weeks", () => {
    const { container } = render(
      <I18nProvider initialLocale="en">
        <MissingWeeks runId={9} stats={{}} />
      </I18nProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
