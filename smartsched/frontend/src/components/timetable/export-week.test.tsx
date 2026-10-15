/** Admin persona M-32: "Export to Excel" at week 4 exported all 14 weeks; the menu now offers this week or the term. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { I18nProvider } from "@/lib/i18n/provider";
import { CapsuleToolbar, type CapsuleToolbarProps } from "./capsule-toolbar";
import type { CalendarModel } from "./model/index-model";

const model = { rooms: [], events: [], index: { run: { id: 7 }, weeks: [] } } as unknown as CalendarModel;
const noop = () => undefined;

function renderToolbar(onExport: CapsuleToolbarProps["onExport"]) {
  const props = {
    model, lens: "week", onLens: noop, board: "run", onBoard: noop, weekLabel: "Hafta 4", weeks: [], week: 4, onWeek: noop, onPrev: noop, onNext: noop, onToday: noop,
    onToggleSidebar: noop, subject: null, onSubject: noop, conflicts: 0, warnings: 0, onIssues: noop, canUndo: false, canRedo: false, onUndo: noop, onRedo: noop,
    density: "standard", onDensity: noop, runs: [], compare: null, onCompare: noop, onExport, onShortcuts: noop, onSearch: noop, condensed: false, readOnly: false,
  } as unknown as CapsuleToolbarProps;
  render(
    <I18nProvider initialLocale="tr">
      <CapsuleToolbar {...props} />
    </I18nProvider>,
  );
}

describe("timetable Excel export (M-32)", () => {
  it("the URL carries the visible week; the whole term has no weeks parameter", () => {
    expect(api.runs.exportUrl(7, "xlsx", [4])).toBe("/api/v1/runs/7/export?format=xlsx&weeks=4");
    expect(api.runs.exportUrl(7, "xlsx")).toBe("/api/v1/runs/7/export?format=xlsx");
  });

  it("“Bu haftayı Excel'e aktar” asks for this week, “Tüm dönemi Excel'e aktar” for the term", async () => {
    const onExport = vi.fn();
    renderToolbar(onExport);
    await userEvent.click(screen.getByRole("button", { name: "Diğer" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Bu haftayı Excel'e aktar" }));
    expect(onExport).toHaveBeenLastCalledWith("week");
    await userEvent.click(screen.getByRole("button", { name: "Diğer" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Tüm dönemi Excel'e aktar" }));
    expect(onExport).toHaveBeenLastCalledWith("term");
    // calendar-view maps "week" to exportUrl(run, "xlsx", [liveWeek])
    expect(api.runs.exportUrl(7, "xlsx", [4])).toContain("weeks=4");
  });
});
