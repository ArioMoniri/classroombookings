import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProposedConstraint } from "@/lib/api/schemas";
import { StudioMeta } from "@/lib/api/studio-schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { studioMeta } from "@/test/fixtures/studio-meta";
import { ReviewTray, resolveCandidate, unresolvedCandidates } from "./review-tray";
import type { TrayItem } from "./studio-store";
import { UploadReview, bucketOf, reviewCounts } from "./upload-review";

const meta = StudioMeta.parse(studioMeta());

const ok = ProposedConstraint.parse({ kind: "same_room_across_weeks", params: {}, hardness: "soft", weight: 5, nl_text: "Her hafta aynı derslik", confidence: 0.9, status: "ok" });
const tip = ProposedConstraint.parse({ kind: "room_tags", params: { forbidden_tags: ["TIP"], programs: ["Eczacılık"] }, hardness: "hard", weight: 5, nl_text: "TIP derslikleri sadece Tıp için", confidence: 0.93, status: "ok" });
const ambiguous = ProposedConstraint.parse({
  kind: "room_preference",
  params: { programs: ["Hemşirelik"] },
  hardness: "soft",
  weight: 5,
  nl_text: "Hemşirelik A 20'de olsun",
  confidence: 0.5,
  status: "needs_review",
  issues: ["room 'A 20' is ambiguous"],
  entities: [{ type: "room", text: "A 20", resolved_id: null, candidates: [{ id: 8, label: "A 205" }, { id: 9, label: "A 206" }] }],
});

const item = (key: string, proposal: ProposedConstraint, origin: TrayItem["origin"] = "nl"): TrayItem => ({ key, origin, ...(origin === "upload" ? { file: "Eczacilik.xlsx" } : {}), state: "pending", type: "rule", proposal });

function renderTray(items: TrayItem[]) {
  const props = { items, meta, onAccept: vi.fn(), onReject: vi.fn(), onUpdate: vi.fn() };
  render(
    <I18nProvider initialLocale="en">
      <ReviewTray {...props} />
    </I18nProvider>,
  );
  return props;
}

describe("ReviewTray", () => {
  it("lists pending suggestions and accepts only the ready ones in bulk", async () => {
    const p = renderTray([item("a", ok), item("b", ambiguous), item("c", tip)]);
    expect(screen.getByRole("heading", { name: "3 suggestions to review" })).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("tray-accept-all"));
    expect(p.onAccept).toHaveBeenCalledTimes(1);
    expect(p.onAccept.mock.calls[0][0].map((i: TrayItem) => i.key)).toEqual(["a", "c"]);
    expect(screen.getByTestId("tray-accept-all")).toHaveTextContent("Accept all ready (2)");
  });

  it("accepts or dismisses a single card", async () => {
    const p = renderTray([item("a", ok), item("c", tip)]);
    const cards = screen.getAllByTestId("tray-item");
    await userEvent.click(within(cards[1]).getByTestId("tray-accept"));
    expect(p.onAccept.mock.calls[0][0][0].key).toBe("c");
    await userEvent.click(within(cards[0]).getByTestId("tray-reject"));
    expect(p.onReject).toHaveBeenCalledWith(["a"]);
  });

  it("a needs_review card shows candidates; choosing one resolves it", async () => {
    const p = renderTray([item("b", ambiguous)]);
    expect(screen.getByText("Needs a look before it can be added")).toBeInTheDocument();
    expect(screen.getByTestId("tray-accept-all")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "A 206" }));
    const [key, next] = p.onUpdate.mock.calls[0] as [string, ProposedConstraint];
    expect(key).toBe("b");
    expect(next.params.room_ids).toEqual([9]);
    expect(next.status).toBe("ok");
  });

  it("keyboard: 'a' accepts the focused card", async () => {
    const p = renderTray([item("a", ok)]);
    const card = screen.getByTestId("tray-item");
    card.focus();
    await userEvent.keyboard("a");
    expect(p.onAccept).toHaveBeenCalled();
  });

  it("renders nothing when every suggestion is handled", () => {
    renderTray([{ ...item("a", ok), state: "accepted" }]);
    expect(screen.queryByTestId("review-tray")).not.toBeInTheDocument();
  });
});

describe("resolveCandidate", () => {
  it("writes the chosen room and clears the matching issue", () => {
    expect(unresolvedCandidates(ambiguous)).toEqual([{ index: 0, text: "A 20", options: [{ id: 8, label: "A 205" }, { id: 9, label: "A 206" }] }]);
    const r = resolveCandidate(ambiguous, 0, 8);
    expect(r.params).toEqual({ programs: ["Hemşirelik"], room_ids: [8] });
    expect(r.issues).toEqual([]);
    expect(unresolvedCandidates(r)).toEqual([]);
  });
});

describe("UploadReview", () => {
  const ref = (row: number) => ({ file: "Eczacilik.xlsx", sheet: "Sayfa1", row, excerpt: `row ${row}` });
  const items: TrayItem[] = [
    item("r1", { ...ok, source: "UPLOAD", source_ref: ref(2) }, "upload"),
    item("r2", { ...ambiguous, source: "UPLOAD", source_ref: ref(3) }, "upload"),
    { key: "u1", origin: "upload", file: "Eczacilik.xlsx", state: "pending", type: "unparsed", unparsed: { text: "Pazartesi sabah toplantı", reason: "no course code", source_ref: ref(4) } },
  ];

  it("counts tabs and shows 'from file · sheet · row N' provenance", async () => {
    expect(reviewCounts(items)).toEqual({ all: 3, ready: 1, look: 1, unread: 1 });
    expect(items.map(bucketOf)).toEqual(["ready", "look", "unread"]);
    const onAccept = vi.fn();
    const onRephrase = vi.fn();
    render(
      <I18nProvider initialLocale="en">
        <UploadReview items={items} meta={meta} onAccept={onAccept} onReject={vi.fn()} onUpdate={vi.fn()} onRephrase={onRephrase} />
      </I18nProvider>,
    );
    expect(screen.getByText("From 1 files we found 3 items: 1 ready, 1 need a look, 1 couldn't be read.")).toBeInTheDocument();
    expect(screen.getAllByTestId("review-from")[0]).toHaveTextContent("from Eczacilik.xlsx · Sayfa1 · row 2");
    await userEvent.click(screen.getByTestId("review-accept-all"));
    expect(onAccept.mock.calls[0][0].map((i: TrayItem) => i.key)).toEqual(["r1"]);
    await userEvent.click(screen.getByTestId("review-tab-unread"));
    await userEvent.click(screen.getByRole("button", { name: "Rephrase as text…" }));
    expect(onRephrase).toHaveBeenCalledWith("Pazartesi sabah toplantı", "u1");
  });
});
