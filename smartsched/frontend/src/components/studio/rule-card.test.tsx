import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { StudioMeta } from "@/lib/api/studio-schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { studioMeta } from "@/test/fixtures/studio-meta";
import { RuleCard, type RuleCardProps } from "./rule-card";
import { tokens } from "./rule-sentence";
import { StudioDataContext, fallbackSentence } from "./studio-data";

const meta = StudioMeta.parse(studioMeta());
const keep = meta.templates.find((t) => t.id === "keep_in_building");
if (!keep) throw new Error("template");
const sentence = { ...fallbackSentence, programs: ["Eczacılık", "Tıp"] };
const rooms = ["A", "B", "C"].map((b, i) => ({ id: i + 1, building_id: i + 1, building_code: b, code: `${b}101`, display_name: `${b} 101`, floor: 1, capacity: 60, exam_capacity: 30, tags: [], is_bookable: true }));

function wrap(ui: ReactNode) {
  return render(
    <I18nProvider initialLocale="en">
      <StudioDataContext.Provider value={{ rooms, classes: [], termWeeks: [], sentence, advanced: false }}>{ui}</StudioDataContext.Provider>
    </I18nProvider>,
  );
}

const base = (over: Partial<RuleCardProps> = {}): RuleCardProps => ({
  domId: "rule-1",
  tokens: tokens(keep, { building: "C", days: [1], programs: ["Eczacılık"] }, sentence),
  fallback: "fallback",
  source: "AI",
  hardness: "soft",
  weight: 5,
  onHardness: vi.fn(),
  onWeight: vi.fn(),
  onSlotChange: vi.fn(),
  affected: { count: 42, percent: 3.3, targeted: true },
  nlText: "eczacılık pazartesi C blokta kalsın",
  ...over,
});

describe("RuleCard", () => {
  it("renders the sentence with clickable slots and a source chip (icon + word)", () => {
    wrap(<RuleCard {...base()} />);
    const card = screen.getByRole("article");
    expect(card).toHaveAccessibleName("Keep Eczacılık in building C on Monday");
    expect(screen.getByRole("button", { name: "Change Applies to, currently Eczacılık" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change Building, currently C" })).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByText("eczacılık pazartesi C blokta kalsın").closest("q")).toHaveAttribute("lang", "tr");
  });

  it("Must / Try to is a radiogroup with a plain explanation", async () => {
    const onHardness = vi.fn();
    wrap(<RuleCard {...base({ onHardness })} />);
    const group = screen.getByTestId("rule-hardness");
    expect(group).toHaveAttribute("role", "radiogroup");
    expect(screen.getByRole("radio", { name: "Try to" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/follows this whenever it can/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Must" }));
    expect(onHardness).toHaveBeenCalledWith("hard");
  });

  it("disables the hardness a kind doesn't allow, with the reason", () => {
    wrap(<RuleCard {...base({ hardness: "hard", allowed: ["hard"] })} />);
    const tryTo = screen.getByRole("radio", { name: "Try to" });
    expect(tryTo).toBeDisabled();
    expect(tryTo).toHaveAttribute("title", "This kind of rule is always a Must.");
  });

  it("importance Low/Normal/High maps to 2/5/8; the 1–10 slider is advanced only", async () => {
    const onWeight = vi.fn();
    const { rerender } = wrap(<RuleCard {...base({ onWeight })} />);
    expect(screen.getByRole("radio", { name: "Normal" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: "High" }));
    expect(onWeight).toHaveBeenCalledWith(8);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    rerender(
      <I18nProvider initialLocale="en">
        <RuleCard {...base({ onWeight, weight: 7, advanced: true })} />
      </I18nProvider>,
    );
    expect(screen.getByText("Custom (7)")).toBeInTheDocument();
    expect(screen.getByRole("slider")).toBeInTheDocument();
  });

  it("hides importance for Must rules", () => {
    wrap(<RuleCard {...base({ hardness: "hard" })} />);
    expect(screen.queryByRole("radio", { name: "High" })).not.toBeInTheDocument();
  });

  it("shows 'applies to N classes' and warns when it matches nothing", async () => {
    const onShowClasses = vi.fn();
    const { unmount } = wrap(<RuleCard {...base({ onShowClasses })} />);
    await userEvent.click(screen.getByRole("button", { name: /applies to 42 classes/ }));
    expect(onShowClasses).toHaveBeenCalled();
    unmount();
    wrap(<RuleCard {...base({ affected: { count: 0, targeted: true } })} />);
    expect(screen.getByTestId("matches-none")).toHaveTextContent("matches no classes, check the name");
  });

  it("shows the clash line linked to the card, with Show both and fixes", async () => {
    const onShowBoth = vi.fn();
    const fix = vi.fn();
    wrap(<RuleCard {...base({ clash: { other: "Never use A 206 for MAT", onShowBoth, fixes: [{ label: "Make the second one a Try-to", run: fix }] } })} />);
    expect(screen.getByTestId("rule-clash")).toHaveTextContent("Clashes with “Never use A 206 for MAT”");
    expect(screen.getByRole("article")).toHaveAttribute("aria-describedby", "rule-1-clash");
    await userEvent.click(screen.getByRole("button", { name: "Show both" }));
    await userEvent.click(screen.getByRole("button", { name: "Make the second one a Try-to" }));
    expect(onShowBoth).toHaveBeenCalled();
    expect(fix).toHaveBeenCalled();
  });

  it("proposal cards are dashed and announce 'not yet added'", () => {
    wrap(<RuleCard {...base({ proposal: true })} />);
    expect(screen.getByText(/suggested, not yet added/)).toBeInTheDocument();
  });

  it("opens a slot picker and reports the new value", async () => {
    const onSlotChange = vi.fn();
    wrap(<RuleCard {...base({ onSlotChange })} />);
    await userEvent.click(screen.getByRole("button", { name: "Change Building, currently C" }));
    await userEvent.click(await screen.findByRole("button", { name: "B block" }));
    expect(onSlotChange).toHaveBeenCalledWith("building", "B");
  });
});
