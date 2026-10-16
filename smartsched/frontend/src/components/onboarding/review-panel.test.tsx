/** ReviewPanel renders whatever kinds the review payload holds (T-R1-21): the `ai_rows` item of model-read rows has
 * its own label and no accept button (rows are decided in the rows panel), an unknown future kind falls back to a
 * generic label instead of failing the schema, and "accept all blocking" never posts an `ai_rows` item. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReviewOut } from "@/lib/api/council";
import { I18nProvider } from "@/lib/i18n/provider";
import { ReviewPanel } from "./review-panel";

const payload = ReviewOut.parse({
  job_id: 8,
  status: "REVIEW",
  blocking: 2,
  threshold: 0.8,
  plan: null,
  content: true,
  items: [
    { id: "rows:0", kind: "ai_rows", title: "rules_memo.docx: 36 of 36 rows read by the AI model wait for a person", blocking: true, decision: null, file_index: 0, pending: 36, total: 36 },
    { id: "map:0:0:2", kind: "mapping", title: "notes.docx / Table 1: column 'Seats' -> capacity?", blocking: true, decision: null, file_index: 0, confidence: 0.62, current: { field: "capacity" }, options: ["", "capacity"] },
    { id: "x:1", kind: "future_kind", title: "Something new", blocking: false, decision: null },
  ],
});

function wrap(onDecide = vi.fn(), locale: "tr" | "en" = "tr") {
  render(
    <I18nProvider initialLocale={locale}>
      <ReviewPanel review={payload} busy={false} onDecide={onDecide} />
    </I18nProvider>,
  );
  return onDecide;
}

describe("ReviewPanel kinds", () => {
  it("parses and renders an ai_rows item and an unknown kind", () => {
    wrap();
    const card = screen.getByTestId("onboarding-review");
    expect(within(card).getByRole("region", { name: "YZ ile okunan satırlar" })).toBeInTheDocument();
    expect(within(card).getByRole("region", { name: "Diğer" })).toBeInTheDocument();
    const row = screen.getByTestId("review-rows:0");
    expect(within(row).queryByRole("button", { name: "Onayla" })).toBeNull();
    expect(row).toHaveTextContent("satırların kararı aşağıdaki listede");
    // Turkish percent (T-R1-23): "güven %62", never "62 %"
    expect(screen.getByTestId("review-map:0:0:2")).toHaveTextContent("güven %62");
  });

  it("accept-all leaves the ai_rows item to the rows panel", async () => {
    const onDecide = wrap();
    await userEvent.setup().click(screen.getByRole("button", { name: "Engelleyenlerin hepsini onayla" }));
    expect(onDecide).toHaveBeenCalledWith([{ id: "map:0:0:2", action: "accept" }]);
  });
});
