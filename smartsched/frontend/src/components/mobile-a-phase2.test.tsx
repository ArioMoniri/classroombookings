/**
 * Mobile optimiser A, phase 2 (docs/testing/mobile/2026-10-17-mobile-a.md §4): the code-level part of the fixes that
 * the first phase-2 pass left open. jsdom has no layout, media queries or `content-visibility`, so size and position
 * rules are source contracts (like mobile-b-phase2.test.tsx); behaviour is rendered. The stack re-measure (CLS, INP,
 * M-13 landscape, 200 % text) is listed as E2E TO RUN in the lane's hand-off.
 */
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { BOOKING_ROW_CLASS } from "./bookings/my-bookings-view";
import { DatePicker } from "./bookings/date-picker";
import { dateFormatter } from "./bookings/date-format";

const SRC = join(process.cwd(), "src");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");
const lineOf = (rel: string, needle: string) => read(rel).split("\n").find((l) => l.includes(needle)) ?? "";

describe("fix 13 · rem-based text and the text-scale meta", () => {
  const css = read("app/globals.css");
  const block = (sel: string) => css.slice(css.indexOf(sel), css.indexOf("}", css.indexOf(sel)));
  it("body text is 0.875rem / 1.25rem, not 14 px / 20 px, so the OS text size reaches it", () => {
    const body = block("  body {\n    @apply text-foreground;");
    expect(body).toContain("font-size: 0.875rem;");
    expect(body).toContain("line-height: 1.25rem;");
    expect(body).not.toMatch(/font-size:\s*\d+px/);
  });
  it("every type-* utility and text-2xs size in rem or a rem clamp, never px", () => {
    for (const m of css.matchAll(/@utility type-[\w-]+ \{([^}]*)\}/g)) expect(m[1]).not.toMatch(/font-size:\s*\d+px/);
    expect(block(".text-2xs")).toContain("font-size: 0.625rem");
  });
  it("the root layout emits <meta name=\"text-scale\" content=\"scale\">", () => {
    expect(read("app/layout.tsx")).toMatch(/other:\s*\{\s*"text-scale":\s*"scale"\s*\}/);
  });
});

describe("fix 4 · landscape (≤ 500 px tall): compact bars", () => {
  const tabBar = read("components/shell/tab-bar.tsx");
  it("tab items are one 44 px row with the label beside the icon, and the capsule loses its padding", () => {
    const item = lineOf("components/shell/tab-bar.tsx", "const ITEM =");
    expect(item).toContain("[@media(max-height:500px)]:min-h-11");
    expect(item).toContain("[@media(max-height:500px)]:flex-row");
    expect(lineOf("components/shell/tab-bar.tsx", "<nav aria-label")).toContain("[@media(max-height:500px)]:p-0");
    expect(lineOf("components/shell/tab-bar.tsx", 'data-testid="open-palette-mobile"')).toContain("[@media(max-height:500px)]:size-11");
    expect(tabBar).toContain("[@media(max-height:500px)]:bottom-[max(0.5rem,env(safe-area-inset-bottom))]");
  });
  it("the shell's bottom reservation follows the compact bar, and the top bar (static there) reserves nothing", () => {
    const css = read("app/globals.css");
    const q = css.slice(css.indexOf("@media (max-height: 500px) {\n    :root"), css.indexOf("@media (width >= 64rem) {\n    :root"));
    expect(q).toContain("--shell-top-h: 0px;");
    expect(q).toContain("--shell-bottom-h: calc(2.75rem + max(0.5rem, env(safe-area-inset-bottom)));");
    expect(lineOf("components/shell/top-bar.tsx", "<header className=\"sticky top-0 z-30 box-content flex h-12")).toContain("[@media(max-height:500px)]:static");
  });
  it("/reserve's one-row confirm bar sits just above the compact tab bar", () => {
    const qr = lineOf("components/quick-reserve/quick-reserve-view.tsx", 'data-testid="qr-confirm"');
    expect(qr).toContain("max-lg:[@media(max-height:500px)]:bottom-[calc(3.25rem+max(0.5rem,env(safe-area-inset-bottom)))]");
  });
});

describe("fix 14 + mobile-b fix 10 · narrow screens and 200 % text", () => {
  it("the search circle moves from the tab bar to the top bar below 22.5rem (360 px, or a 390 px phone at large text)", () => {
    expect(lineOf("components/shell/tab-bar.tsx", 'data-testid="open-palette-mobile"')).toContain("max-[22.5rem]:hidden");
    expect(lineOf("components/shell/top-bar.tsx", 'data-testid="open-palette-narrow"')).toContain("max-[22.5rem]:inline-flex");
    expect(read("components/shell/tab-bar.tsx")).not.toContain("max-[359px]");
    expect(read("components/shell/top-bar.tsx")).not.toContain("max-[359px]");
  });
  it("the /bookings date chip drops the weekday and year there (no ellipsis at 320)", () => {
    const fmt = dateFormatter(undefined, "tr");
    render(
      <I18nProvider initialLocale="tr">
        <DatePicker value="2026-10-22" onChange={() => undefined} dates={[]} weeks={[]} termStart="2026-09-14" termEnd="2027-01-15" fmt={fmt} compact />
      </I18nProvider>,
    );
    const trigger = screen.getByTestId("date-picker-trigger");
    const short = trigger.querySelector("[data-slot=date-chip-short]")!;
    expect(short).toHaveTextContent("22 Eki");
    expect(short).toHaveClass("hidden", "max-[22.5rem]:inline");
    expect(short.previousElementSibling).toHaveClass("max-[22.5rem]:hidden");
    expect(short.previousElementSibling).toHaveTextContent(fmt.weekday("2026-10-22"));
  });
});

describe("fix 5 · content-visibility on long lists", () => {
  it("my bookings rows", () => {
    expect(BOOKING_ROW_CLASS).toContain("[content-visibility:auto]");
    expect(BOOKING_ROW_CLASS).toContain("[contain-intrinsic-size:auto_4rem]");
  });
  it("the recurring preview's dates", () => {
    expect(lineOf("components/bookings/recurring-preview-table.tsx", "<li key={row.date}")).toContain("[content-visibility:auto]");
  });
  it("the kiosk building's room cards", () => {
    expect(lineOf("components/public-schedule/public-views.tsx", "<li key={r.code} className=")).toContain("[content-visibility:auto] [contain-intrinsic-size:auto_11rem]");
  });
  it("the free-room rows on /bookings (first pass) keep it", () => {
    expect(lineOf("components/bookings/free-slots-list.tsx", "data-testid={`free-room-")).toContain("[content-visibility:auto]");
  });
});

describe("fix 2 · the kiosk date row on phones", () => {
  it("the long date is its own line under the arrows, and the placeholder reserves both lines", () => {
    expect(lineOf("components/public-schedule/kiosk.tsx", 'data-testid="kiosk-long-date"')).toContain("max-sm:basis-full");
    expect(lineOf("components/public-schedule/kiosk.tsx", 'data-testid="kiosk-nav-placeholder"')).toContain("max-sm:min-h-[calc(3.25rem+var(--text-title-3)*var(--text-title-3-lh))]");
  });
});
