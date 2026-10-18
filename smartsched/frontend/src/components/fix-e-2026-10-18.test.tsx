/** FIX-E (round 4, 2026-10-18): the majors of HX-12b, personas, AUX-12, CAL-10 and WG-10 that unit tests can hold. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { ClosedDayNotice, isClosedDay } from "./bookings/closed-day";
import type { Grid } from "@/lib/api/crbs";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), usePathname: () => "/moderation/me", useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

const tr = (ui: React.ReactNode) => render(<I18nProvider initialLocale="tr">{ui}</I18nProvider>);

describe("HX12B-F01 / PER-F11: a day without periods is never a blank grid", () => {
  it("says the day is closed and offers the next open day", async () => {
    const onGo = vi.fn();
    tr(<ClosedDayNotice next="2026-10-19" long={() => "Pazartesi 19 Ekim"} onGo={onGo} />);
    expect(screen.getByText("Bu gün rezervasyona kapalı.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Pazartesi 19 Ekim gününe git" }));
    expect(onGo).toHaveBeenCalledWith("2026-10-19");
  });
  it("only a one-day grid with no periods counts as closed", () => {
    expect(isClosedDay({ display: "day", periods: [] } as unknown as Grid)).toBe(true);
    expect(isClosedDay({ display: "room", periods: [] } as unknown as Grid)).toBe(false);
    expect(isClosedDay({ display: "day", periods: [{ id: 1 }] } as unknown as Grid)).toBe(false);
  });
});

describe("HX12B-F06: a planner's run page never reads the admin-only settings", () => {
  it("useSettings({peek, enabled:false}) sends nothing; peek is silent", async () => {
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { renderHook, waitFor } = await import("@testing-library/react");
    const client = await import("@/lib/api/client");
    const spy = vi.spyOn(client, "request").mockResolvedValue({} as never);
    const { useSettings } = await import("@/lib/api/hooks");
    const wrap = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
    renderHook(() => useSettings({ peek: true, enabled: false }), { wrapper: wrap });
    await new Promise((r) => setTimeout(r, 20));
    expect(spy).not.toHaveBeenCalled();
    renderHook(() => useSettings({ peek: true, enabled: true }), { wrapper: wrap });
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0]![1]).toMatchObject({ silent: true });
    spy.mockRestore();
  });
  it("the chat panel asks only with planning.admin", async () => {
    const { readFileSync } = await import("node:fs");
    const path = await import("node:path");
    const src = readFileSync(path.resolve(import.meta.dirname, "chat/chat-panel.tsx"), "utf8");
    expect(src).toMatch(/useSettings\(\{ peek: true, enabled: can\("planning\.admin"\) \}\)/);
  });
});

describe("HX12B-F07: an imported board never claims '✓ 0/632 ders yerleşti'", () => {
  it("says it is an imported board without the success tone, even with a clean truth of 0 placed", async () => {
    const { ScheduleRun } = await import("@/lib/api/schemas");
    const { Verdict } = await import("./runs/run-view");
    const { truthOf } = await import("./runs/run-truth");
    const board = ScheduleRun.parse({ id: 3, term_id: 1, term_code: "2026-GUZ", kind: "COURSE", horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", params: {}, objective_value: null, soft_score: 100, hard_score: 100, stats: {}, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: "2026-10-01T10:00:00Z", finished_at: "2026-10-01T10:00:00Z" });
    const truth = truthOf({ verdict: "clean", placed: 0, total: 632, unplaced: 632, hard_score: 100, broken: [], broken_count: 0, exceptions: [], exceptions_total: 0, headline: { tr: "0/632 ders yerleşti · hiçbir kural bozulmadı", en: "" } });
    tr(<Verdict r={board} truth={truth} outcome={{ kind: "done" } as never} />);
    const v = screen.getByTestId("run-verdict");
    expect(v).toHaveAttribute("data-state", "imported");
    expect(v).toHaveTextContent("İçe aktarılan çizelge: çözücü çalışmadı.");
    expect(v.className).not.toMatch(/feasible/);
  });
  it("a solver run whose clean truth placed nothing is not green", async () => {
    const { ScheduleRun } = await import("@/lib/api/schemas");
    const { Verdict } = await import("./runs/run-view");
    const { truthOf } = await import("./runs/run-truth");
    const run = ScheduleRun.parse({ id: 8, term_id: 1, term_code: "2026-GUZ", kind: "COURSE", horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", params: {}, objective_value: null, soft_score: 100, hard_score: 100, stats: { solver: "cp-sat", events: 10 }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: "2026-10-01T10:00:00Z", finished_at: "2026-10-01T10:00:00Z" });
    const truth = truthOf({ verdict: "clean", placed: 0, total: 10, unplaced: 10, hard_score: 100, broken: [], broken_count: 0, exceptions: [], exceptions_total: 0, headline: { tr: "0/10 ders yerleşti", en: "" } });
    tr(<Verdict r={run} truth={truth} outcome={{ kind: "done" } as never} />);
    expect(screen.getByTestId("run-verdict")).toHaveAttribute("data-state", "empty");
  });
});

describe("PER-F06 / HX12B-F08: Çizelge opens on the published run, not the newest scenario", () => {
  it("defaultRun prefers is_active of the right kind, then the latest", async () => {
    const { defaultRun } = await import("./timetable/use-calendar-data");
    const run = (id: number, extra: Record<string, unknown> = {}) => ({ id, kind: "COURSE", is_active: false, ...extra }) as never;
    const runs = [run(9), run(7), run(3, { is_active: true })];
    expect(defaultRun(runs, { kind: "REGULAR" } as never)?.id).toBe(3);
    expect(defaultRun([run(9), run(7)], { kind: "REGULAR" } as never)?.id).toBe(9);
    // an exam term's published course run does not win over its exam run
    expect(defaultRun([run(9, { kind: "EXAM" }), run(3, { is_active: true })], { kind: "FINAL" } as never)?.id).toBe(9);
  });
});

describe("PER-F02: Taleplerim shows the staff member's room request, not a dead end", () => {
  it("unlinked staff: the C 606 request is listed; no 'Hesabınız bağlı değil' page", async () => {
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const client = await import("@/lib/api/client");
    const req = { id: 2, status: "PENDING", step: 1, steps: 1, room_id: 6, room_name: "C 606", requester_name: "Personel Test", requested_at: "2026-10-18T10:00:00", bookings: [{ id: 9, date: "2026-10-19", start_period: 1, end_period: 1, period_name: "1. ders", status: "PENDING", room_id: 6 }], decisions: [], approvers: [], competing: [] };
    const spy = vi.spyOn(client, "request").mockImplementation((async (path: string) => {
      if (path === "/moderation/me") return { instructor_id: null, instructor: null, current_term: { id: 1, code: "2026-GUZ", name: "Güz 2026-27" }, can_add_preference: false };
      if (path === "/approvals/mine") return [req];
      if (path.startsWith("/bookings/context") || path.startsWith("/org/i18n") || path.startsWith("/auth")) throw new client.HttpError(404, "x");
      throw new client.HttpError(404, `unexpected ${path}`);
    }) as never);
    const { MyRequests } = await import("./moderation/moderation-console");
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <MyRequests />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("my-room-requests")).toHaveTextContent("C 606");
    expect(screen.getByTestId("mine-unlinked-note")).toBeTruthy();
    expect(screen.queryByText("Hesabınız bir öğretim elemanına bağlı değil")).toBeNull();
    spy.mockRestore();
  });
});

describe("PER-F04: a Bahar file onto Güz is caught before Uygula", () => {
  it("compares the file's season word with the target term", async () => {
    const { termMismatch, seasonOf } = await import("./import/term-hint");
    const terms = [{ id: 1, name: "Güz 2026-27" }, { id: 2, name: "Bahar 2026" }];
    expect(seasonOf("bahar_derslik_planlama_listesi_v5")).toBe("spring");
    expect(seasonOf("GÜZ programı")).toBe("fall");
    expect(termMismatch("bahar_derslik_planlama_listesi_v5.xlsx", terms[0], terms)).toEqual({ target: "Güz 2026-27", likely: { id: 2, name: "Bahar 2026" } });
    expect(termMismatch("bahar_derslik_planlama_listesi_v5.xlsx", terms[1], terms)).toBeNull();
    expect(termMismatch("planlama.xlsx", terms[0], terms)).toBeNull();
  });
  it("the preview keeps Uygula disabled until the target is confirmed", async () => {
    const { ImportPreview } = await import("./import/import-preview");
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const job = { id: 7, kind: "planning-list", filename: "bahar_derslik_planlama_listesi_v5.xlsx", status: "DONE", summary: { rows: 10, created: 4, updated: 2, skipped: 0, warnings: [] }, created_at: "2026-10-18T00:00:00Z" } as never;
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <ImportPreview job={job} onApplied={() => undefined} onCancel={() => undefined} termWarning={{ target: "Güz 2026-27", likely: { id: 2, name: "Bahar 2026" } }} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("import-term-mismatch")).toHaveTextContent("Bahar 2026");
    const apply = screen.getByTestId("import-apply");
    expect(apply).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Güz 2026-27/ }));
    expect(apply).not.toBeDisabled();
  });
});

describe("PER-F05: import warnings read in Turkish", () => {
  it("translates the report's examples; an unknown shape stays", async () => {
    const { warningTr } = await import("./import/warning-tr");
    expect(warningTr("instructor value 'UZEM' names no person (mode); not used as an instructor")).toBe("“UZEM” bir kişi değil (öğretim biçimi); öğretim elemanı sayılmadı");
    expect(warningTr("weeks value 0; assuming all")).toBe("Hafta değeri 0; bütün haftalar varsayıldı");
    expect(warningTr("time 13:40-18:00 snapped to P7-P12 (13:40-18:00): periods covered for at least half their length")).toBe("13:40–18:00 saati P7–P12 ders saatlerine (13:40–18:00) yuvarlandı");
    expect(warningTr("something new")).toBe("something new");
  });
});

describe("AUX12-F02: the 2FA setup sheet is a full screen below 600 px", () => {
  it("its overrides carry the base classes' data-[side=right] variant and survive cn()", async () => {
    const { MFA_SHEET_CLASS } = await import("./profile/security/mfa-setup-sheet");
    const { cn } = await import("@/lib/utils");
    const merged = cn("data-[side=right]:inset-y-2 data-[side=right]:right-2 data-[side=right]:w-3/4 data-[side=right]:sm:max-w-sm", MFA_SHEET_CLASS);
    for (const c of ["max-[599px]:data-[side=right]:w-full", "max-[599px]:data-[side=right]:inset-0", "max-[599px]:data-[side=right]:h-full"]) expect(merged.split(" ")).toContain(c);
    expect(MFA_SHEET_CLASS).not.toMatch(/(^| )max-\[599px\]:w-full/);
  });
});

describe("CAL10-F01: many departments sit behind one card with a search", () => {
  it("146 departments: one 'Bölüm dersleri' card; the search finds one; the other scopes stay", async () => {
    const { WhatStep } = await import("./calendar-export/steps");
    const choice = (key: string, kind: string, name: string | null = null) => ({ key, kind, departmentId: name ? Number(key.split(":")[1]) : null, departmentName: name, available: true, reason: null, reasonText: null, upcoming: null, hours: null, sample: null, fields: null }) as never;
    const names = ["Psikoloji", "Adli Bilimler", "Ağız ve Diş Sağlığı", ...Array.from({ length: 143 }, (_, i) => `Bölüm ${i}`)];
    const choices = [choice("my_classes", "my_classes"), ...names.map((n, i) => choice(`department_classes:${i + 1}`, "department_classes", n)), choice("my_bookings", "my_bookings")];
    const onPick = vi.fn();
    tr(<WhatStep choices={choices} onPick={onPick} notLinked={false} contactEmail={null} />);
    expect(screen.queryAllByTestId(/^cal-scope-department_classes:/)).toHaveLength(0);
    expect(screen.getByTestId("cal-scope-my_bookings")).toBeTruthy();
    await userEvent.click(screen.getByTestId("cal-scope-departments-toggle"));
    expect(screen.getAllByTestId(/^cal-scope-department_classes:/)).toHaveLength(8);
    await userEvent.type(screen.getByTestId("cal-departments-search"), "ağız");
    const hit = screen.getAllByTestId(/^cal-scope-department_classes:/);
    expect(hit).toHaveLength(1);
    await userEvent.click(hit[0]!);
    expect(onPick).toHaveBeenCalled();
  });
});

describe("CAL10-F02: no panel address, no link channel, and the reason said", () => {
  it("the options' link note hides the link channel; step 2 says why and keeps the file", async () => {
    const { adaptOptions, ExportOptions } = await import("@/lib/api/calendar-export");
    const { channelChoices } = await import("./calendar-export/model");
    const { HowStep } = await import("./calendar-export/steps");
    const raw = { enabled: true, linked: true, scopes: [], channels: { push: { google: { configured: false } }, link: { available: false, reason: "no_public_url", message_tr: "Abonelik bağlantısı için yöneticinizin panel adresini girmesi gerekiyor.", message_en: "x" }, file: { available: true } } };
    const o = ExportOptions.parse(adaptOptions(raw));
    const ch = channelChoices(o);
    expect(ch.map((c) => c.kind)).toEqual(["file"]);
    tr(<HowStep channels={ch} onPick={() => undefined} linkNote={o.channels.link_note?.tr ?? null} />);
    expect(screen.getByTestId("cal-link-note")).toHaveTextContent("panel adresini");
  });
});

describe("WG10-F02: welcome focus never stays on <body>", () => {
  it("an interactive tour step's card takes focus on İleri", async () => {
    const { TourCard, TourCardContext } = await import("./welcome/tour/tour-card");
    const target = document.createElement("button");
    document.body.appendChild(target);
    const step = { id: "reserve-when", target, title: "Önce zamanı seçin", body: "Gün ve saat.", interactive: true };
    const controls = { index: 1, total: 5, next: vi.fn(), back: vi.fn(), end: vi.fn() };
    (document.activeElement as HTMLElement | null)?.blur();
    tr(
      <TourCardContext.Provider value={{ step, controls, docked: false, bodyId: "b" }}>
        <TourCard />
      </TourCardContext.Provider>,
    );
    await new Promise((r) => setTimeout(r, 200));
    expect(document.activeElement).toBe(screen.getByTestId("tour-next"));
  });
  it("after a card's navigation the new page's h1 gets focus, not the old one", async () => {
    const { focusPageHeading } = await import("./welcome/welcome-store");
    const main = document.createElement("main");
    main.innerHTML = "<h1>Rezervasyonlar</h1>";
    document.body.appendChild(main);
    const old = main.querySelector("h1")!;
    focusPageHeading(2000, { afterNavigation: true });
    await new Promise((r) => setTimeout(r, 120));
    expect(document.activeElement).not.toBe(old);
    main.innerHTML = "<h1>Boş derslik bul</h1>";
    await new Promise((r) => setTimeout(r, 200));
    expect(document.activeElement?.textContent).toBe("Boş derslik bul");
    main.remove();
  });
});
