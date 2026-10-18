/**
 * UI alignment (docs/testing/ui-alignment/2026-10-18/report.md): the icons and controls of one row share a centre line
 * and one size (docs/design/tokens.md §A.5, §A3). jsdom has no layout, so the measured rule lives in
 * e2e/ui-alignment.spec.ts; here the classes that produce it are pinned and the size props are rendered.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({
  usePathname: () => "/my-bookings",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { SelectField } from "./admin/kit";
import { dateFormatter } from "./bookings/date-format";
import { DatePicker } from "./bookings/date-picker";
import { TabBar } from "./shell/tab-bar";

const SRC = join(process.cwd(), "src");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");
const lineOf = (rel: string, needle: string) => read(rel).split("\n").find((l) => l.includes(needle)) ?? "";

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "p.t@smartsched.local", username: "pt", full_name: "P. T.", role: "TEACHER", permissions: ["book_single.create", "room.view"] });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/approvals/inbox") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("phone tab bar: the detached search sits on the tabs' icon line", () => {
  it("is built like a tab (capsule padding, item box, 20 px glyph box, label) in a centred row", async () => {
    stubFetch();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <I18nProvider initialLocale="tr">
          <TabBar />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const nav = await screen.findByRole("navigation", { name: "Sekmeler" });
    await waitFor(() => expect(within(nav).getAllByRole("link").length).toBeGreaterThanOrEqual(3));
    const search = screen.getByTestId("open-palette-mobile");
    expect(search).toHaveAccessibleName("Ara veya sor");
    // same padding as the tab capsule (p-1), so the item boxes start at the same y
    expect(search).toHaveClass("p-1", "glass-chrome", "rounded-full", "max-[22.5rem]:hidden", "[@media(max-height:500px)]:p-0");
    expect(nav).toHaveClass("p-1", "[@media(max-height:500px)]:p-0");
    const tab = within(nav).getAllByRole("link")[0]!;
    const box = search.firstElementChild!;
    for (const c of ["flex-col", "min-h-12", "justify-center", "gap-0.5"]) {
      expect(tab).toHaveClass(c);
      expect(box).toHaveClass(c);
    }
    // the glyph box: one 20 px size for every tab's icon and the search's
    const glyph = box.firstElementChild!;
    expect(glyph).toHaveClass("[&_svg]:size-5");
    expect(tab.querySelector("span[aria-hidden]:not([data-slot])")).toHaveClass("[&_svg]:size-5");
    expect(within(search).getByText("Ara")).toHaveAttribute("data-slot", "tab-label");
    // the row centres its two capsules (items-end put the 48 px circle 4 px below the 56 px capsule's centre)
    const row = search.parentElement!;
    expect(row).toHaveClass("items-center");
    expect(row).not.toHaveClass("items-end");
  });
});

describe("one control height and icon size per toolbar row", () => {
  it("the /bookings date trigger takes the toolbar's sm size (28 px, 14 px glyph) and stays md by default", () => {
    const fmt = dateFormatter(undefined, "tr");
    const props = { onChange: () => undefined, dates: [], weeks: [], termStart: "2026-09-14", termEnd: "2027-01-15", fmt } as const;
    const { unmount } = render(
      <I18nProvider initialLocale="tr">
        <DatePicker value="2026-10-22" {...props} size="sm" />
      </I18nProvider>,
    );
    expect(screen.getByTestId("date-picker-trigger")).toHaveAttribute("data-size", "sm");
    unmount();
    render(
      <I18nProvider initialLocale="tr">
        <DatePicker value="2026-10-22" {...props} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("date-picker-trigger")).toHaveAttribute("data-size", "md");
    expect(lineOf("components/bookings/bookings-view.tsx", "{g ? <DatePicker {...datePickerProps(g)} size=\"sm\" />")).toContain("h-(--control-h-sm)");
  });
  it("SelectField passes fieldSize to the NativeSelect (the toolbar's room and session pickers are sm, the sheet's md)", () => {
    render(
      <SelectField aria-label="Dönem" fieldSize="sm" defaultValue="a">
        <option value="a">A</option>
      </SelectField>,
    );
    expect(screen.getByRole("combobox", { name: "Dönem" })).toHaveClass("h-(--control-h-sm)");
    expect(lineOf("components/bookings/bookings-view.tsx", 'data-testid="session-select"')).toContain('fieldSize={wide ? "md" : "sm"}');
    expect(lineOf("components/bookings/bookings-view.tsx", 'data-testid="room-select"')).toContain('fieldSize={wide ? "md" : "sm"}');
  });
  it("the timetable subject picker's chevron takes the button's icon size (it was 12 px beside 14 px glyphs)", () => {
    const toolbar = read("components/timetable/capsule-toolbar.tsx");
    expect(toolbar).not.toContain('<ChevronDown className="size-3');
    expect(lineOf("components/timetable/capsule-toolbar.tsx", 'data-testid="subject-picker"')).toContain("size={size}");
  });
  it("the phone timetable header is one --control-h-lg row: lens button and subject capsule share height and centre", () => {
    const mobile = read("components/timetable/mobile-calendar.tsx");
    expect(mobile).toContain('<div className="flex items-center gap-2 pt-1">');
    expect(lineOf("components/timetable/mobile-calendar.tsx", '<span className="glass-chrome flex')).toContain("h-(--control-h-lg) min-w-(--control-h-lg)");
    expect(mobile).toContain('condensed size="md" />');
    expect(mobile).not.toContain("size-10 items-center justify-center rounded-full");
  });
});

describe("command palette input row", () => {
  it("the search glyph is on the icon scale (20 px beside the title-3 input), not 18 px", () => {
    const line = lineOf("components/ui/command.tsx", "<SearchIcon");
    expect(line).toContain("size-5");
    expect(line).not.toContain("size-[18px]");
  });
});
