// RF-09 (rf-f-2026-10-18): /admin/weeks "Dönem haftaları": the kind of each week (Ders, Sınav, Tatil, Bütünleme)
// through PATCH /terms/{id}/weeks/{index}, the "Elle değiştirildi" badge, and the duplicate-week refusal inline.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
const TERM = { id: 2, code: "2026-BAHAR", name: "2025-2026 Bahar", kind: "REGULAR", start_date: "2026-02-16", end_date: "2026-06-05", week_count: 14, is_active: true };
vi.mock("@/components/shell/term-switcher", () => ({ useActiveTerm: () => ({ term: TERM, terms: [TERM], isLoading: false }) }));

import { TermWeeksEditor } from "./term-weeks-editor";

const W = (index: number, kind = "LECTURE", edited = false) => ({ id: index, term_id: 2, index, start_date: `2026-02-${String(9 + index * 7 > 28 ? 28 : 9 + index * 7).padStart(2, "0")}`, kind, label: `${index}. hafta`, edited });
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; body: unknown }[];
let routes: Record<string, (b: unknown) => Response>;
beforeEach(() => {
  calls = [];
  routes = {
    "GET /api/v1/terms/2/weeks": () => res(200, [W(1), W(2, "HOLIDAY", true), W(3)]),
    "PATCH /api/v1/terms/2/weeks/3": (b) => res(200, { ...W(3), kind: (b as { kind: string }).kind, edited: true }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ key, body });
      return routes[key]?.(body) ?? res(404, {});
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <TermWeeksEditor />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("Dönem haftaları (term week calendar)", () => {
  it("lists the term's weeks with their kind in Turkish and the 'Elle değiştirildi' badge", async () => {
    wrap();
    const w2 = await screen.findByTestId("term-week-2");
    expect(within(w2).getByLabelText("2. hafta türü")).toHaveDisplayValue("Tatil");
    expect(within(w2).getByText("Elle değiştirildi")).toBeInTheDocument();
    expect(within(screen.getByTestId("term-week-1")).queryByText("Elle değiştirildi")).toBeNull();
    const options = within(within(w2).getByLabelText("2. hafta türü")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Ders", "Sınav", "Tatil", "Bütünleme"]);
  });

  it("changes one week's kind with PATCH and shows it as edited", async () => {
    wrap();
    const select = await screen.findByLabelText("3. hafta türü");
    fireEvent.change(select, { target: { value: "EXAM" } });
    await waitFor(() => expect(calls.find((c) => c.key === "PATCH /api/v1/terms/2/weeks/3")?.body).toEqual({ kind: "EXAM" }));
    expect(await within(screen.getByTestId("term-week-3")).findByText("Elle değiştirildi")).toBeInTheDocument();
  });

  it("shows a refused change at the week", async () => {
    routes["PATCH /api/v1/terms/2/weeks/3"] = () => res(422, { detail: { code: "week_kind_invalid", message: "x", message_en: "x", message_tr: "Hafta türü Ders, Sınav, Tatil veya Bütünleme olmalı." } });
    wrap();
    fireEvent.change(await screen.findByLabelText("3. hafta türü"), { target: { value: "MAKEUP" } });
    expect(await within(screen.getByTestId("term-week-3")).findByRole("alert")).toHaveTextContent("Hafta türü Ders, Sınav, Tatil veya Bütünleme olmalı.");
  });

  it("adds a week under 'Gelişmiş'; a duplicate number is refused inline in the server's words", async () => {
    routes["PUT /api/v1/terms/2/weeks"] = () => res(422, { detail: { code: "week_index_duplicate", message: "duplicate week index", message_en: "duplicate week index", message_tr: "Aynı hafta numarası iki kez verildi." } });
    wrap();
    await screen.findByTestId("term-week-1");
    expect(screen.queryByLabelText("Hafta numarası")).toBeNull();
    fireEvent.click(screen.getByTestId("term-weeks-advanced"));
    fireEvent.change(screen.getByLabelText("Hafta numarası"), { target: { value: "2" } });
    fireEvent.click(screen.getByTestId("term-week-add"));
    const alert = await screen.findByTestId("term-week-add-error");
    expect(alert).toHaveTextContent("Aynı hafta numarası iki kez verildi.");
    const put = calls.find((c) => c.key === "PUT /api/v1/terms/2/weeks")!.body as { index: number }[];
    expect(put.map((w) => w.index)).toEqual([1, 2, 3, 2]);
    expect(screen.getByLabelText("Hafta numarası")).toHaveAttribute("aria-invalid", "true");
  });
});
