/**
 * FIX-B (fix-b-2026-10-18): fixes from docs/testing/e2e-queue/results-2026-10-18.md (Mobile A, Mobile B, RF-2, RF-M).
 * jsdom has no layout, so sizes and wrapping are source contracts (as in mobile-b-phase2.test.tsx); behaviour (what is
 * mounted, hidden, focused, closed) is rendered. The stack re-measure (CLS, scrollWidth, M-05, M-09) is in the report's
 * E2E TO RUN list.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate, type MessageKey } from "@/lib/i18n";
import { SettleGate, SETTLE_CAP_MS } from "./common/settle-gate";
import { welcomeHold } from "./shell/welcome-settle";
import { QuietNumbers } from "./dashboard/dashboard-view";
import { MailNoticesCard } from "./settings/mail-notices";
import { dirtyCapsuleIndex, useDirtyCapsule } from "./settings/dirty-capsule";
import { fixtureIndex } from "@/test/fixtures/calendar-index";
import { MobileCalendar, type MobileCalendarProps } from "./timetable/mobile-calendar";
import { dateOf } from "./timetable/model/dates";
import { buildModel } from "./timetable/model/index-model";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const SRC = join(process.cwd(), "src");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");
const lineOf = (rel: string, needle: string) => read(rel).split("\n").find((l) => l.includes(needle)) ?? "";

const wrap = (node: ReactNode) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <I18nProvider initialLocale="tr">{node}</I18nProvider>
  </QueryClientProvider>
);

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/* ------------------------------------------------------------------------------------------ F-MB-1 (CLS) */

describe("F-MB-1 · SettleGate: async cards appear together, in one step, instead of pushing each other down", () => {
  it("while not ready: a reserved-height placeholder is shown and the content is mounted but hidden (its queries run)", () => {
    render(
      <SettleGate ready={false} testId="gate-loading" placeholderClassName="min-h-[60dvh]">
        <p>content</p>
      </SettleGate>,
    );
    const ph = screen.getByTestId("gate-loading");
    expect(ph).toHaveAttribute("aria-busy", "true");
    expect(ph.className).toContain("min-h-[60dvh]");
    const content = screen.getByText("content");
    expect(content.closest("[hidden]")).not.toBeNull();
  });

  it("when ready: the placeholder goes and the content shows; it never hides again on a refetch", () => {
    const view = render(
      <SettleGate ready={false} testId="gate-loading">
        <p>content</p>
      </SettleGate>,
    );
    view.rerender(
      <SettleGate ready testId="gate-loading">
        <p>content</p>
      </SettleGate>,
    );
    expect(screen.queryByTestId("gate-loading")).toBeNull();
    expect(screen.getByText("content").closest("[hidden]")).toBeNull();
    view.rerender(
      <SettleGate ready={false} testId="gate-loading">
        <p>content</p>
      </SettleGate>,
    );
    expect(screen.queryByTestId("gate-loading")).toBeNull();
    expect(screen.getByText("content").closest("[hidden]")).toBeNull();
  });

  it("a slow answer never holds the page: the content shows after the cap", () => {
    vi.useFakeTimers();
    render(
      <SettleGate ready={false} testId="gate-loading">
        <p>content</p>
      </SettleGate>,
    );
    act(() => vi.advanceTimersByTime(SETTLE_CAP_MS - 10));
    expect(screen.getByTestId("gate-loading")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(20));
    expect(screen.queryByTestId("gate-loading")).toBeNull();
    expect(SETTLE_CAP_MS).toBeLessThanOrEqual(2000);
  });
});

describe("F-MB-1 · the 'Başlarken' card on /dashboard, /admin and /reserve no longer lands above a rendered page", () => {
  const base = { pathname: "/dashboard", hydrated: true, meLoading: false, meKnown: true, welcomePending: false, slotLoaded: true };
  it("holds the page on a checklist home until GET /welcome has answered", () => {
    expect(welcomeHold({ ...base, welcomePending: true })).toBe(true);
    expect(welcomeHold({ ...base, pathname: "/admin", welcomePending: true })).toBe(true);
    expect(welcomeHold({ ...base, pathname: "/reserve", welcomePending: true })).toBe(true);
    expect(welcomeHold({ ...base, meLoading: true, meKnown: false, welcomePending: true })).toBe(true);
    // server render and the hydration pass: the same (held) markup
    expect(welcomeHold({ ...base, hydrated: false, welcomePending: true })).toBe(true);
    // the slot is its own chunk (lazy-shell.tsx): the page waits for it too, or the card would land a moment later
    expect(welcomeHold({ ...base, slotLoaded: false })).toBe(true);
    expect(welcomeHold(base)).toBe(false);
  });
  it("never holds other routes, a failed /me or a signed-out session", () => {
    expect(welcomeHold({ ...base, pathname: "/runs", welcomePending: true })).toBe(false);
    expect(welcomeHold({ ...base, pathname: "/admin/users", welcomePending: true })).toBe(false);
    expect(welcomeHold({ ...base, meKnown: false, welcomePending: true })).toBe(false);
  });
  it("the shell mounts the hold around the welcome slot and the page", () => {
    const shell = read("components/shell/app-shell.tsx");
    expect(shell).toMatch(/<WelcomeSettle>\s*\{\/\*[^]*?\*\/\}\s*<LazyWelcomePageSlot \/>/);
    expect(shell.indexOf("</WelcomeSettle>")).toBeGreaterThan(shell.indexOf("</PeriodGridGate>"));
  });
});

describe("F-MB-1 · /dashboard: the hero numbers hold their final height while loading", () => {
  it("QuietNumbers without data renders the four labels and a number line each (same rows as with data)", () => {
    render(wrap(<QuietNumbers />));
    const terms = document.querySelectorAll("dt");
    expect([...terms].map((d) => d.textContent)).toEqual(["İnceleme bekleyen", "Şubeler", "Planlanabilir derslik", "Bu haftaki çakışma"]);
    const busy = document.querySelector("dl");
    expect(busy).toHaveAttribute("aria-busy", "true");
    // the two hint lines ("… talepten", "… derslikten") are reserved too
    expect(document.querySelectorAll("[data-testid=quiet-hint-loading]").length).toBe(2);
    for (const s of document.querySelectorAll("[data-testid=quiet-number-loading]")) expect(s.className).toContain("h-[1lh]");
  });
  it("the room-use title keeps its words while the number loads (it wraps the same way on a phone)", () => {
    const src = read("components/dashboard/dashboard-view.tsx");
    expect(src).not.toContain('<Skeleton className="h-10 w-72" />');
    expect(src).toContain('data-testid="hero-number-loading"');
  });
});

describe("F-MB-1 · Ayarlar › Entegrasyonlar and /exams/invigilation", () => {
  it("the integrations cards wait for their four settings answers behind one placeholder", () => {
    const src = read("components/settings/settings-view.tsx");
    expect(src).toContain('testId="integrations-loading"');
    expect(src).toMatch(/useIntegrationSettings\(\)/);
    expect(src).toMatch(/useExportAdminSettings\(\)/);
    expect(src).toMatch(/usePublicSettings\(\)/);
    expect(src).toMatch(/useWebhooks\(\)/);
  });
  it("the board-run notice appears with the panel, not above the loading placeholder", () => {
    const src = read("components/invigilation/invigilation-view.tsx");
    expect(src).toMatch(/const panelLoading = /);
    expect(src).toMatch(/!panelLoading && run && tab === "plans" && isBoardRun\(run\)/);
  });
  it("a fixed page-actions capsule arriving with the data adds no gap to the header column on a phone", () => {
    expect(read("components/common/page-header.tsx")).toContain("max-lg:has-[>[data-slot=page-actions]]:contents");
  });
});

/* -------------------------------------------------------------------------------------- F-RF2-1 (M-05) */

describe("F-RF2-1 · Ayarlar › Genel: a changed card's save floats in the phone capsule", () => {
  function renderMail() {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ reminder_lead_hours: 24, new_device_sign_in_mail: true }), { status: 200, headers: { "Content-Type": "application/json" } })),
    );
    render(wrap(<MailNoticesCard />));
  }
  it("at rest the save sits in its card; after a change it is in the fixed capsule above the tab bar, focus stays", async () => {
    renderMail();
    const input = await screen.findByTestId("mail-notices-hours");
    await waitFor(() => expect(input).toHaveValue("24"));
    const slot = () => screen.getByTestId("mail-notices-save").parentElement!;
    expect(slot().getAttribute("data-slot")).toBeNull();
    expect(slot().className).not.toContain("max-lg:fixed");
    input.focus();
    fireEvent.change(input, { target: { value: "48" } });
    expect(slot()).toHaveAttribute("data-slot", "page-actions");
    expect(slot().className).toContain("max-lg:fixed");
    expect(slot().className).toContain("max-lg:bottom-[calc(var(--shell-bottom-h)+0.75rem+var(--capsule-offset,0rem))]");
    expect(document.activeElement).toBe(input);
    expect(screen.getByTestId("mail-notices-save").className).toContain("pointer-coarse:min-h-11");
  });
  it("two changed cards stack their capsules instead of covering each other", () => {
    const seen: number[] = [];
    function Probe({ dirty, id }: { dirty: boolean; id: string }) {
      const c = useDirtyCapsule(dirty);
      if (dirty) seen.push(dirtyCapsuleIndex(c));
      return <div data-testid={id} {...c.props} />;
    }
    const view = render(
      <>
        <Probe dirty id="a" />
        <Probe dirty={false} id="b" />
      </>,
    );
    expect(screen.getByTestId("a").style.getPropertyValue("--capsule-offset")).toBe("0rem");
    view.rerender(
      <>
        <Probe dirty id="a" />
        <Probe dirty id="b" />
      </>,
    );
    const offsets = ["a", "b"].map((id) => screen.getByTestId(id).style.getPropertyValue("--capsule-offset")).sort();
    expect(offsets).toEqual(["0rem", "3.75rem"]);
  });
  it("the security-contact card uses the same capsule, and MOBILE.md names the per-card pattern for the tab", () => {
    expect(read("components/settings/security-contact.tsx")).toContain("useDirtyCapsule(");
    expect(readFileSync(join(process.cwd(), "../../docs/testing/flows/MOBILE.md"), "utf8")).toContain("`?tab=general`");
  });
});

/* --------------------------------------------------------------------------------------- F-RF2-2 (#418) */

describe("F-RF2-2 · /my-bookings renders the same markup on the server and in the hydration pass", () => {
  it("the page waits for hydration (cached /me, booking context and the deep link changed the first client render)", () => {
    const page = read("app/(app)/my-bookings/page.tsx");
    expect(page).toContain("<HydrationGate");
    expect(page).toMatch(/<HydrationGate[^>]*>\s*<MyBookingsView \/>\s*<\/HydrationGate>/);
  });
});

/* ------------------------------------------------------------------------------------ F-MA-1 / F-MB-3 */

describe("F-MA-1 · 200 % text on /find-room and /my-bookings: no sideways scroll", () => {
  it("the find-room fieldsets and columns may shrink (a fieldset is min-content wide by default)", () => {
    const src = read("components/findroom/find-room-view.tsx");
    const fieldsets = src.split("\n").filter((l) => l.includes("<fieldset"));
    expect(fieldsets.length).toBe(2);
    for (const f of fieldsets) expect(f).toContain("min-w-0");
    expect(src).toContain('className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(20rem,22.5rem)_minmax(0,1fr)] lg:items-start"');
    expect(lineOf("components/findroom/find-room-view.tsx", "lg:sticky lg:top-16")).toContain("min-w-0");
  });
  it("the stats tiles reflow to fewer columns when the text is large, and long words wrap inside a tile", () => {
    const dl = lineOf("components/profile/my-stats.tsx", "<dl");
    expect(dl).toContain("grid-cols-[repeat(auto-fit,minmax(min(100%,6.5rem),1fr))]");
    expect(dl).not.toMatch(/\bgrid-cols-3\b/);
    expect(lineOf("components/profile/my-stats.tsx", "<dt")).toContain("[overflow-wrap:anywhere]");
  });
  it("the shared Field shrinks inside its grid cell", () => {
    expect(lineOf("components/admin/kit.tsx", 'cn("flex flex-col gap-1.5", className)')).toBe("");
    expect(read("components/admin/kit.tsx")).toContain('cn("flex min-w-0 flex-col gap-1.5", className)');
  });
});

describe("F-MB-3 · 32 px root on /generate and /analytics/heatmap", () => {
  it("the Studio bar decides by its own width in rem (container query), so a large root font hides the Back word", () => {
    const src = read("components/studio/studio-view.tsx");
    expect(src).toContain('data-glass="chrome" className="@container/sbar glass-chrome');
    expect(src).toContain('<span className="@max-[22rem]/sbar:sr-only">{t("common.back")}</span>');
    expect(lineOf("components/studio/studio-view.tsx", 'testId="bar-generate"')).toContain('className="min-w-0 shrink"');
    expect(read("components/studio/generate-step.tsx")).toContain('<span className="min-w-0 truncate">');
  });
  it("the tab-bar items keep their 44 px minimum in pixels, not 2× at a 32 px root (the search capsule: ask to the UI-alignment lane)", () => {
    const tab = read("components/shell/tab-bar.tsx");
    expect(tab).toContain("min-w-[min(2.75rem,44px)]");
  });
});

/* ------------------------------------------------------------------------------------------ F-MA-2 */

describe("F-MA-2 · tab-bar labels are never cut off at 320 and 390", () => {
  it("labels may take two lines (no ellipsis), items stay ≥ 48 px tall", () => {
    const tab = read("components/shell/tab-bar.tsx");
    const label = /const LABEL = "([^"]+)"/.exec(tab)![1]!;
    expect(label).not.toContain("truncate");
    expect(label).not.toContain("whitespace-nowrap");
    expect(label).toContain("line-clamp-2");
    expect(label).toContain("text-center");
    const item = /const ITEM = "([^"]+)"/.exec(tab)![1]!;
    expect(item).toContain("min-h-12");
    expect(item).not.toMatch(/(^| )px-1( |$)/);
  });
  it("every single-word tab label fits a 58 px column (≤ 8 letters), in both languages", () => {
    // every label the bar can show (Onaylar never is a tab: it stays under Diğer)
    const keys: MessageKey[] = ["nav.tab.bookings", "nav.tab.myBookings", "nav.tab.findRoom", "nav.tab.myRequests", "nav.tab.reserve", "nav.tab.dashboard", "nav.requests", "nav.generate", "nav.tab.timetable", "glass.shell.more"];
    for (const l of ["tr", "en"] as const)
      for (const k of keys) for (const word of translate(l, k).split(" ")) expect(word.length, `${l} ${k} "${word}"`).toBeLessThanOrEqual(8);
    expect(translate("tr", "nav.tab.myBookings")).toBe("Benim");
    expect(translate("tr", "nav.tab.myRequests")).toBe("Talepler");
    // the planner's bar reads the same words in Turkish; English gets 8-letter forms of Dashboard / Timetable
    expect(translate("tr", "nav.tab.dashboard")).toBe(translate("tr", "nav.dashboard"));
    expect(translate("tr", "nav.tab.timetable")).toBe(translate("tr", "nav.timetable"));
    const tab = read("components/shell/tab-bar.tsx");
    expect(tab).toContain('"/dashboard": "nav.tab.dashboard"');
    expect(tab).toContain('"/timetable": "nav.tab.timetable"');
  });
});

/* ------------------------------------------------------------------------------------------ F-MB-2 */

describe("F-MB-2 · timetable column tags are 12 px", () => {
  it("the tag uses the footnote type token (12 px), never the 10 px text-2xs", () => {
    const tag = lineOf("components/timetable/time-grid.tsx", 'data-testid="column-tag"');
    expect(tag).toContain("type-footnote");
    expect(tag).not.toContain("text-2xs");
  });
});

/* ------------------------------------------------------------------------------- RF-M #5 (lens menu) */

describe("RF-M #5 · the phone lens menu closes after a pick", () => {
  const model = buildModel(fixtureIndex());
  const dates = [1, 2, 3, 4, 5, 6, 7].map((d) => dateOf(model.index.weeks, 3, d));
  it("picking 'Ay' switches the lens and closes the menu, focus back on the menu button", async () => {
    const onLens = vi.fn();
    const props: MobileCalendarProps = {
      model, week: 3, day: 3, dates, onDay: vi.fn(), onWeek: vi.fn(), heat: new Map(), now: { minutes: 600, iso: "2026-02-18" },
      selection: new Set(), onSelect: vi.fn(), subject: null, onSubject: vi.fn(), runId: 42, termId: 1,
      actions: {} as MobileCalendarProps["actions"], readOnly: true, lens: "agenda", onLens,
    };
    render(wrap(<MobileCalendar {...props} />));
    const trigger = screen.getByRole("button", { name: "Takvim görünümü" });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("menuitemradio", { name: "Ay" }));
    expect(onLens).toHaveBeenCalledWith("month");
    await waitFor(() => expect(screen.queryByRole("menuitemradio", { name: "Ay" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
