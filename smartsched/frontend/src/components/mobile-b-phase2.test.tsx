/**
 * Mobile optimiser B, phase 2 (mobile-b-2026-10-17): fixes from docs/testing/mobile/2026-10-17-mobile-b.md §5 on the
 * planning and admin screens. jsdom has no layout, so the size and position rules are source contracts (as in
 * admin/loop-r3-laneF.test.tsx); behaviour (focus, one sheet, labels) is rendered. The stack re-measure with the
 * audit scripts (scratchpad/mobile-b/ev/scripts) is the layout check.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ScheduleRun } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { PublishRunButton } from "./runs/publish-run";

const ROOT = join(process.cwd(), "src/components");
const read = (rel: string) => readFileSync(join(ROOT, rel), "utf8");
/** the source line that carries a data-testid */
const lineOf = (rel: string, testid: string) => read(rel).split("\n").find((l) => l.includes(`data-testid="${testid}"`)) ?? "";

const run = (over: Record<string, unknown> = {}) =>
  ScheduleRun.parse({ id: 12, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3, 4] }, status: "FEASIBLE_PARTIAL", params: {}, stats: { placed: 660, events_total: 683 }, diagnosis: [], is_active: false, created_at: "2026-10-17T10:00:00Z", ...over });

describe("fix 4 · the run report's publish action is a thumb-reach capsule on touch tablets too", () => {
  it("run-publish-row is fixed above the tab bar below lg on a coarse pointer, not only below sm", () => {
    const row = lineOf("runs/run-view.tsx", "run-publish-row");
    expect(row).toContain("max-sm:fixed");
    expect(row).toContain("max-lg:pointer-coarse:fixed");
    expect(row).toContain("max-lg:pointer-coarse:bottom-[calc(5.25rem+env(safe-area-inset-bottom))]");
  });
});

describe("fix 8 · publish dialog: the footer stays in view and focus returns to the trigger", () => {
  it("the footer sticks to the bottom of the scrolling body at every width (landscape 844×390 is not max-sm)", () => {
    const src = read("runs/publish-run.tsx");
    expect(src).toMatch(/<DialogFooter className="[^"]*\bsticky\b[^"]*\bbottom-0\b/);
  });

  it("Escape returns focus to 'Yayınla', not to a checkbox inside the closed dialog", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="en">
          <PublishRunButton run={run()} published={7} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const trigger = screen.getByTestId("run-publish");
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByTestId("publish-partial-ack"));
    await userEvent.keyboard("{Escape}");
    await new Promise((r) => setTimeout(r, 50));
    expect(document.activeElement).toBe(trigger);
  });
});
