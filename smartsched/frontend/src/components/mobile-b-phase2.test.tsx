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
import { describe, expect, it, vi } from "vitest";
import { ScheduleRun } from "@/lib/api/schemas";
import { api } from "@/lib/api/endpoints";
import { I18nProvider } from "@/lib/i18n/provider";
import { PublishRunButton } from "./runs/publish-run";
import { focusClassChip } from "./timetable/focus-chip";
import { SortableList } from "./admin/sortable-list";

const ROOT = join(process.cwd(), "src/components");
const read = (rel: string) => readFileSync(join(ROOT, rel), "utf8");
/** the source line that carries a data-testid */
const lineOf = (rel: string, testid: string) => read(rel).split("\n").find((l) => l.includes(`data-testid="${testid}"`)) ?? "";

const run = (over: Record<string, unknown> = {}) =>
  ScheduleRun.parse({ id: 12, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3, 4] }, status: "FEASIBLE_PARTIAL", params: {}, objective_value: null, soft_score: 80, hard_score: 100, stats: { placed: 660, events_total: 683 }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: "2026-10-15T10:00:00Z", finished_at: "2026-10-15T10:01:00Z", ...over });

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
  }, 20000);
});

describe("fix 5 + 7 · Studio classes step on touch: cards, and the filters as a bottom sheet with an apply action", () => {
  const src = read("studio/classes-step.tsx");
  it("the card layout (and the filter trigger) covers touch tablets below 1024, not only < 768", () => {
    expect(src).toContain('window.matchMedia("(max-width: 767px), (pointer: coarse) and (max-width: 1023px)")');
  });
  it("the filters sheet opens from the bottom and ends in one 'N dersi göster' action", () => {
    expect(lineOf("studio/classes-step.tsx", "filters-sheet")).toContain('side="bottom"');
    expect(src).toContain('data-testid="filters-apply"');
    expect(src).toMatch(/t\("classes\.showN", \{ n: shown\.length \}\)/);
  });
});

describe("fix 5 · /classes on a touch tablet uses the cards, and its search does not zoom", () => {
  const src = read("classes/classes-page.tsx");
  it("the phone layout (cards, select mode, bulk bar) covers touch tablets below 1024", () => {
    expect(src).toContain('useMedia("(max-width: 767px), (pointer: coarse) and (max-width: 1023px)")');
  });
  it("the inline search is 16 px on a coarse pointer", () => {
    expect(src.split("\n").find((l) => l.includes('aria-label={t("classes.searchLabel")}'))).toContain("pointer-coarse:text-base");
  });
});

describe("fix 6 · timetable: closing the inspector with Escape keeps focus on the class (768 measured <body>)", () => {
  it("focusClassChip moves focus to the chip of the class the inspector showed, else to the title", async () => {
    document.body.innerHTML = '<h2 id="calendar-title" tabindex="-1">Hafta 3</h2><button data-testid="calendar-event" data-assignment-id="41">PHAR 240</button>';
    focusClassChip(41);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(document.activeElement?.getAttribute("data-assignment-id")).toBe("41");
    focusClassChip(999);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(document.activeElement?.id).toBe("calendar-title");
    document.body.innerHTML = "";
  });
  it("the Escape path uses it when focus is inside the inspector", () => {
    const src = read("timetable/calendar-view.tsx");
    const esc = src.slice(src.indexOf('if (e.key === "Escape") {'), src.indexOf('if (e.key === "?")'));
    expect(esc).toContain("focusClassChip(");
  });
});

describe("fix 16 · drag-to-reorder has visible buttons on touch (MOBILE.md M-11: a gesture is only a shortcut)", () => {
  it("'Aşağı taşı' moves a row one step, the ends are disabled, the buttons show only on a coarse pointer", async () => {
    const onReorder = vi.fn();
    render(
      <I18nProvider initialLocale="tr">
        <SortableList label="Gruplar" items={[{ id: 1, label: "A Blok" }, { id: 2, label: "B Blok" }]} onReorder={onReorder} render={(g) => <span>{g.label}</span>} />
      </I18nProvider>,
    );
    const down = screen.getByRole("button", { name: "A Blok aşağı taşı" });
    expect(down.className).toContain("pointer-coarse:inline-flex");
    expect(screen.getByRole("button", { name: "A Blok yukarı taşı" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "B Blok aşağı taşı" })).toBeDisabled();
    await userEvent.click(down);
    expect(onReorder).toHaveBeenCalledWith([{ id: 2, label: "B Blok" }, { id: 1, label: "A Blok" }]);
  });
});

describe("fix 10 · 200 % text: action rows wrap instead of pushing the page sideways", () => {
  it("/admin/rooms 'Her bina için bir grup' + 'Yeni grup' wrap", () => {
    const src = read("admin/rooms-admin.tsx");
    const at = src.indexOf('t("crbs.rooms.fromBuildings")');
    const group = src.lastIndexOf('<div className="', src.lastIndexOf("<Button", at));
    expect(src.slice(group, group + 40)).toContain("flex-wrap");
  });
});

describe("fix 1 · CLS: async cards reserve their visible height while loading", () => {
  it("calendar push admin: a viewport-tall placeholder until the settings arrive (the card grew 142 → 379 px, CLS 0.44)", () => {
    const src = read("settings/calendar-push-admin.tsx");
    expect(src).toMatch(/q\.isLoading \? <div className="[^"]*min-h-\[70dvh\][^"]*" aria-busy="true" data-testid="calendar-push-loading"/);
  });
});

describe("fix 10 · Studio at 200 % text", () => {
  const src = read("studio/studio-view.tsx");
  it("the undo / redo / advanced row wraps", () => {
    expect(src).toContain('<div className="flex flex-wrap items-center gap-2 xl:hidden">');
  });
  it("the bottom bar's 'Geri' keeps its icon and moves its word to sr-only once the text is large (rem media query)", () => {
    const bar = src.slice(src.indexOf('data-glass="chrome"'), src.indexOf('data-testid="step-next"'));
    expect(bar).toMatch(/<span className="max-\[24rem\]:sr-only">\{t\("common\.back"\)\}<\/span>/);
  });
});

describe("fix 10 · /admin/ops range at 200 % text", () => {
  it("the 30 / 60 / 180 dk segment sits in its own horizontal scroller", () => {
    const src = read("admin/ops/ops-panel.tsx");
    const at = src.indexOf('aria-label={t("ops.chart.range")}');
    expect(src.slice(src.lastIndexOf("<div", at), at)).toContain('className="max-w-full overflow-x-auto"');
  });
});

describe("fix 11 · moderation on touch: card rows on tablets, 44 px chips", () => {
  const src = read("moderation/moderation-console.tsx");
  it("the console's tables become cards below 1024 on a coarse pointer (mod-row was 718×36 at 768)", () => {
    expect(read("moderation/use-media.ts")).toContain('export const TOUCH_LIST = "(max-width: 767px), (pointer: coarse) and (max-width: 1023px)"');
    expect(src).toMatch(/function CoordinatorConsole[\s\S]{0,400}const mobile = useTouchList\(\);/);
  });
  it("the filter chips ('Herkes' 86×28, chip-unsatisfied 165×28) are 44 px on touch", () => {
    const chips = src.split("\n").filter((l) => l.includes("<Chip "));
    expect(chips.length).toBeGreaterThanOrEqual(2);
    for (const c of chips) expect(c).toContain("pointer-coarse:min-h-11");
  });
});

describe("fix 11 · /dashboard 'Tümünü gör' is a 44 px target on touch (measured 75×16)", () => {
  it("both links are inline-flex boxes of 44 px on a coarse pointer", () => {
    const lines = read("dashboard/dashboard-view.tsx").split("\n");
    const links = lines.map((l, i) => (l.includes('t("dashboard.viewAll")') ? lines[i - 1] : null)).filter(Boolean) as string[];
    expect(links).toHaveLength(2);
    for (const l of links) expect(l).toMatch(/inline-flex[^"]*pointer-coarse:min-h-11/);
  });
});

describe("fix 12 · the one primary action sits in the page-actions capsule (thumb reach below lg)", () => {
  const inCapsule = (rel: string, testid: string) => {
    const src = read(rel);
    const at = src.indexOf(`data-testid="${testid}"`);
    return src.slice(Math.max(0, at - 400), at).includes('data-slot="page-actions" className={pageActionsCapsule}');
  };
  it("/moderation 'Yeniden oluştur' (was at y 179, then scrolled off)", () => expect(inCapsule("moderation/moderation-console.tsx", "recreate-open")).toBe(true));
  it("/exams/invigilation 'Yeni plan' (was at y 145)", () => expect(inCapsule("invigilation/invigilation-view.tsx", "invig-new")).toBe(true));
});

describe("fix 12 · /admin/rooms Gruplar: 'Yeni grup' in the capsule like 'Yeni derslik'", () => {
  it("the new-group button is wrapped in the page-actions capsule", () => {
    const src = read("admin/rooms-admin.tsx");
    const at = src.indexOf('t("crbs.rooms.newGroup")');
    expect(src.slice(Math.max(0, at - 300), at)).toContain('data-slot="page-actions" className={pageActionsCapsule}');
  });
});

describe("fix 13 · /admin/users new-user form: columns of at least 280 px (768 had two of 262)", () => {
  const src = read("admin/users-admin.tsx");
  it("the field grid fits as many ≥ 17.5rem columns as there is room for", () => {
    expect(src).toContain('<div className="grid gap-3 sm:grid-cols-[repeat(auto-fit,minmax(17.5rem,1fr))]">');
  });
  it("the dialog grows on desktop so two columns still fit there", () => {
    expect(lineOf("admin/users-admin.tsx", "user-dialog")).toContain("lg:max-w-2xl");
  });
});

describe("fix 17 · /admin/ops: the overall status is part of the title, not a lone pill floating above the tab bar", () => {
  it("PageTitle gets no actions (the capsule held only 'Çalışıyor'); the pill sits next to the lead", () => {
    const src = read("admin/ops/ops-panel.tsx");
    const title = src.split("\n").find((l) => l.includes("<PageTitle")) ?? "";
    expect(title).not.toContain("actions=");
    expect(title).toContain("<StatusPill status={overall(status.data)} />");
  });
});

describe("hero motion · publish → '✓ Yayında' confirms itself once (free transitions.dev success-check, ≤ 300 ms)", () => {
  const wrap = (r: ReturnType<typeof run>) => (
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="en">
        <PublishRunButton run={r} published={null} />
      </I18nProvider>
    </QueryClientProvider>
  );
  it("a run that is already published on load shows a still check (nothing performs on load, motion.md rule 3)", () => {
    render(wrap(run({ is_active: true })));
    expect(screen.getByTestId("run-published-check").getAttribute("data-state")).toBe("still");
  });
  it("after 'Yayınla' succeeds here, the check plays its appear transition", async () => {
    vi.spyOn(api.runs, "activate").mockResolvedValueOnce(run({ is_active: true }));
    const view = render(wrap(run({ horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", stats: { placed: 683, events_total: 683 } })));
    await userEvent.click(screen.getByTestId("run-publish"));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    view.rerender(wrap(run({ horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", is_active: true, stats: { placed: 683, events_total: 683 } })));
    expect((await screen.findByTestId("run-published-check")).getAttribute("data-state")).toBe("in");
  }, 20000);
});
