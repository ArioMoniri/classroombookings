/** FIX-H (round 4, 2026-10-18): the open HX-12b / personas / AUX-12 / CAL-10 items after FIX-E. */
import { readFileSync } from "node:fs";
import path from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate } from "@/lib/i18n";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), usePathname: () => "/my-classes", useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

const read = (rel: string) => readFileSync(path.resolve(import.meta.dirname, rel), "utf8");
const tr = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><I18nProvider initialLocale="tr">{ui}</I18nProvider></QueryClientProvider>);

describe("HX12B-F05: the run hero answers 'Yayınlayayım mı?'; the figures wait behind 'Ayrıntılar'", () => {
  it("the verdict and Yayınla stay in view; KPIs, policy lines and the soft bars are inside a closed details", () => {
    const src = read("runs/run-view.tsx");
    const details = src.indexOf('data-testid="run-details"');
    expect(details).toBeGreaterThan(0);
    expect(src.indexOf("<Verdict r={r}")).toBeLessThan(details);
    expect(src.indexOf('data-testid="run-publish-row"')).toBeLessThan(details);
    for (const inside of ["<RunPolicyLine", "<RunProfileLine", "<MissingWeeks", 'data-testid={`kpi-${x.k}`}', "<SoftBreakdown"]) expect(src.indexOf(inside), inside).toBeGreaterThan(details);
    expect(src).not.toMatch(/data-testid="run-details" open/);
    expect(translate("tr", "glass.report.details")).toBe("Ayrıntılar");
  });
});

describe("HX12B-F10: 'Başlarken' comes after the page, desktop only", () => {
  it("the shell mounts the home card below the page; the page slot no longer renders it", () => {
    const shell = read("shell/app-shell.tsx");
    expect(shell.indexOf("<LazyWelcomeHomeCardSlot />")).toBeGreaterThan(shell.indexOf("</PeriodGridGate>"));
    const slot = read("welcome/page-slot.tsx");
    expect(slot.split("export function WelcomeHomeCardSlot")[0]).not.toContain("<ChecklistHomeCard />");
    expect(slot).toMatch(/!desktop \|\| !CHECKLIST_HOMES\.includes\(pathname\)/);
  });
});

describe("HX12B-F11: one control for the period in the book sheet", () => {
  it("the select shows only when the chips cannot (a lone free period)", () => {
    expect(read("bookings/book-sheet.tsx")).toContain("{dayChoices.length > 1 && run.length <= 1 ? (");
  });
});

describe("HX12B-F13 / PER-F15: chips are 44 px boxes on touch", () => {
  it("Chip carries pointer-coarse:min-h-11 for both sizes and its remove button", async () => {
    const { Chip } = await import("./ui/chip");
    render(<Chip size="sm" onRemove={() => undefined} removeLabel="Kaldır">A</Chip>);
    expect(screen.getByRole("button", { name: "A" })).toHaveClass("pointer-coarse:min-h-11");
    expect(screen.getByRole("button", { name: "Kaldır" })).toHaveClass("pointer-coarse:min-h-11");
  });
  it("the settings model radios and run fix radios: 20 px inputs, 44 px rows", () => {
    expect(read("settings/settings-view.tsx")).toMatch(/pointer-coarse:min-h-11 \[&:not\(:last-child\)\]:hairline-b[\s\S]{0,200}size-5 shrink-0 accent/);
  });
});

describe("HX12B-F14: model names read as names; phones pick the settings group from a select", () => {
  it("modelLabel", async () => {
    const { modelLabel } = await import("./settings/settings-view");
    expect(modelLabel("claude-opus-5-5")).toBe("Claude Opus 5.5");
    expect(modelLabel("claude-sonnet-4-5-20250929")).toBe("Claude Sonnet 4.5");
    expect(modelLabel("claude-haiku-4")).toBe("Claude Haiku 4");
    expect(modelLabel("gpt-x")).toBe("gpt-x");
  });
  it("a select below sm, the tab strip from sm up", () => {
    const src = read("settings/settings-view.tsx");
    expect(src).toContain('data-testid="settings-section-select"');
    expect(src).toContain('className="mb-5 max-w-full overflow-x-auto max-sm:hidden"');
  });
});

describe("HX12B-F15 / F17 / F18", () => {
  it("the phone's 'Yeni kullanıcı' keeps its words", () => {
    expect(read("admin/users-admin.tsx")).toContain('size={phone && msEnabled && usersAdmin ? "icon" : "default"}');
  });
  it("no raw file name as the room-master subtitle; the runs list says 'İçe aktarılan çizelge' and 'Tercih puanı'", () => {
    expect(translate("tr", "importFlows.roomMaster.kindDesc")).not.toContain("room_master");
    expect(translate("tr", "glass.dashboard.importedBoard", { id: 3 })).toBe("İçe aktarılan çizelge #3");
    expect(translate("tr", "runs.soft")).toBe("Tercih puanı (100 üzerinden)");
  });
});

describe("PER-F07: one place per setting", () => {
  it("Ayarlar has no Kullanıcılar or Rezervasyon kuralları tab; booking rules live in Kurulum; old links redirect", () => {
    const src = read("settings/settings-view.tsx");
    expect(src).not.toMatch(/value: "users"/);
    expect(src).not.toMatch(/value: "booking-rules"/);
    expect(read("../app/(app)/settings/page.tsx")).toContain('redirect("/admin/booking-rules")');
    expect(read("admin/wave1-sections.ts")).toContain('href: "/admin/booking-rules"');
  });
  it("the sidebar: four headings, rare entries under 'Daha fazla'", async () => {
    const { NAV_GROUPS } = await import("./shell/nav-config");
    expect(NAV_GROUPS.map((g) => g.labelKey)).toEqual(["nav.plan", "nav.results", "nav.admin"]);
    const rare = NAV_GROUPS.flatMap((g) => g.items).filter((i) => i.more).map((i) => i.href);
    expect(rare).toEqual(["/programs/new", "/runs/compare", "/analytics/forecast", "/exams/invigilation", "/exams/advisor", "/admin/ops", "/admin/ai", "/admin/catalog"]);
    // tour and helper anchors stay visible
    for (const href of ["/onboarding", "/analytics/heatmap", "/admin/integrations", "/timetable", "/runs"]) expect(rare).not.toContain(href);
    expect(read("shell/sidebar.tsx")).toContain("aria-expanded={showRare}");
  });
});

describe("PER-F04 / PER-F05: the server's term check and Turkish warnings", () => {
  it("serverTermMismatch decides when the server answered", async () => {
    const { serverTermMismatch } = await import("./import/term-hint");
    expect(serverTermMismatch(undefined)).toBeUndefined();
    expect(serverTermMismatch({ target_name: "Güz 2026-27", mismatch: false })).toBeNull();
    expect(serverTermMismatch({ target_name: "Güz 2026-27", mismatch: true, suggested_term_id: 3, suggested_term_name: "Bahar 2026" })).toEqual({ target: "Güz 2026-27", likely: { id: 3, name: "Bahar 2026" } });
  });
  it("warnings read the importer's own sentence; groups list the kind and the rows", async () => {
    const { warningText, WarningGroups } = await import("./import/parse-warnings-table");
    expect(warningText({ row: 1, field: "", value: null, message: "x", severity: "warning", message_tr: "Türkçe" }, "tr")).toBe("Türkçe");
    expect(warningText({ row: 1, field: "", value: null, message: "weeks value 0; assuming all", severity: "warning" }, "tr")).toBe("Hafta değeri 0; bütün haftalar varsayıldı");
    tr(<WarningGroups groups={[{ code: "instructor_not_person", label_tr: "Kişi olmayan öğretim elemanı değeri", label_en: "", count: 37, variants: 1, items: [{ message_tr: "“UZEM” bir kişi değil", message_en: "", count: 37, rows: [1, 2, 3] }] }]} />);
    expect(screen.getByTestId("warning-group-instructor_not_person")).toHaveTextContent("Kişi olmayan öğretim elemanı değeri37 satır");
    expect(screen.getByTestId("warning-group-instructor_not_person")).toHaveTextContent("“UZEM” bir kişi değil · satır 1, 2, 3 …");
  });
});

describe("PER-F09: Derslerim", () => {
  it("byDay groups Monday first", async () => {
    const { byDay } = await import("./my-classes/my-classes-view");
    const c = (date: string, start: string) => ({ uid: date + start, date, start, end: "10:00", codes: ["PSY 262"], section: "1", title: null, rooms: ["C 503"], week: 5 });
    expect(byDay([c("2026-03-04", "08:30"), c("2026-03-02", "13:30"), c("2026-03-02", "08:30")]).map(([d, rows]) => [d, rows.length])).toEqual([["2026-03-02", 2], ["2026-03-04", 1]]);
  });
  it("an unlinked account reads what to do", async () => {
    const client = await import("@/lib/api/client");
    const spy = vi.spyOn(client, "request").mockImplementation(async (p: string) => {
      if (p === "/me/classes/week") return { week_start: "2026-03-02", week_end: "2026-03-08", prev: "2026-02-23", next: "2026-03-09", today: "2026-03-04", linked: false, term_id: null, classes: [] } as never;
      throw new Error(p);
    });
    const { MyClassesView } = await import("./my-classes/my-classes-view");
    tr(<MyClassesView />);
    expect(await screen.findByTestId("my-classes-not-linked")).toHaveTextContent("Planlama ofisine başvurun.");
    expect(screen.getByRole("heading", { level: 1, name: "Derslerim" })).toBeInTheDocument();
    spy.mockRestore();
  });
  it("is a bookings entry for academicians only", async () => {
    const { ADMIN_NAV_ITEMS } = await import("./admin/nav-items");
    expect(ADMIN_NAV_ITEMS.find((i) => i.href === "/my-classes")).toMatchObject({ hideWith: "planning.view", bookings: true });
  });
});
