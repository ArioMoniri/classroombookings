import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Term } from "@/lib/api/schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { NEW_TERM_VALUE, TERM_CREATE_PERMISSIONS, TermSelect, termFromCreated } from "./term-create";

// owner report 2026-11-02 (Çizelge item 4): "Yeni dönem oluştur…" in every term dropdown, for people who may create terms
const perms = vi.hoisted(() => ({ list: [] as string[] }));
vi.mock("@/lib/permissions", async (orig) => ({
  ...(await orig<typeof import("@/lib/permissions")>()),
  usePermissions: () => ({
    perms: perms.list,
    can: (need: string | readonly string[]) => (typeof need === "string" ? [need] : need).some((p) => perms.list.includes(p)),
    canAll: () => false,
    userId: 1,
    loading: false,
    departmentId: null,
  }),
}));
const create = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/crbs", async (orig) => {
  const real = await orig<typeof import("@/lib/api/crbs")>();
  return { ...real, crbsAdmin: { ...real.crbsAdmin, terms: { ...real.crbsAdmin.terms, create } } };
});
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const TERMS: Term[] = [
  { id: 1, code: "2026-BAHAR", name: "2026 Bahar", kind: "REGULAR", start_date: "2026-02-02", end_date: "2026-06-28", week_count: 15, is_active: true },
  { id: 3, code: "2026-FINAL", name: "2026 Final", kind: "FINAL", start_date: "2026-06-01", end_date: "2026-06-21", week_count: 3, is_active: false },
];

function renderSelect(value: number | null = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["terms"], TERMS);
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <label htmlFor="t">Hedef dönem</label>
        <TermSelect id="t" terms={TERMS} value={value} onChange={onChange} defaultKind="FINAL" data-testid="term" />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { qc, onChange, select: screen.getByTestId("term") as HTMLSelectElement };
}

beforeEach(() => {
  perms.list = [];
  create.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("TermSelect: Yeni dönem oluştur…", () => {
  it("is hidden from people who may not create terms", () => {
    const { select } = renderSelect();
    expect([...select.options].map((o) => o.value)).toEqual(["1", "3"]);
  });

  it("is the last option for planning.edit or setup.sessions (the backend's POST /terms guard)", () => {
    expect([...TERM_CREATE_PERMISSIONS]).toEqual(["planning.edit", "setup.sessions"]);
    for (const p of TERM_CREATE_PERMISSIONS) {
      perms.list = [p];
      const { select } = renderSelect();
      const last = select.options[select.options.length - 1]!;
      expect(last.value).toBe(NEW_TERM_VALUE);
      expect(last.textContent).toBe("Yeni dönem oluştur…");
      document.body.innerHTML = "";
    }
  });

  it("choosing it opens the dialog and keeps the current term", () => {
    perms.list = ["planning.edit"];
    const { select, onChange } = renderSelect();
    fireEvent.change(select, { target: { value: NEW_TERM_VALUE } });
    expect(screen.getByTestId("term-create-dialog")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
    expect(select.value).toBe("1");
    // Sınav preselected from the caller (an exam flow)
    expect(screen.getByTestId("term-create-kind-FINAL").getAttribute("aria-checked")).toBe("true");
  });

  it("a value the list does not hold shows a placeholder, never the create action", () => {
    perms.list = ["planning.edit"];
    const { select } = renderSelect(99);
    expect(select.value).toBe("99");
    expect(select.selectedOptions[0]?.textContent).toBe("Dönem seçin");
  });

  it("creates the term with code, name, kind and dates, puts it in the list and selects it", async () => {
    perms.list = ["setup.sessions"];
    create.mockResolvedValue({ id: 12, code: "2027-BAHAR", name: "2027 Bahar", start_date: "2027-02-01", end_date: "2027-06-27", cancelled_booking_ids: [] });
    const { select, onChange, qc } = renderSelect();
    fireEvent.change(select, { target: { value: NEW_TERM_VALUE } });
    const save = screen.getByTestId("term-create-save") as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("term-create-code"), { target: { value: " 2027-BAHAR " } });
    fireEvent.change(screen.getByTestId("term-create-name"), { target: { value: "2027 Bahar" } });
    fireEvent.click(screen.getByTestId("term-create-kind-REGULAR"));
    const start = screen.getByTestId("term-create-start");
    fireEvent.change(start, { target: { value: "2027-02-01" } });
    fireEvent.blur(start);
    const end = screen.getByTestId("term-create-end");
    fireEvent.change(end, { target: { value: "2027-06-27" } });
    fireEvent.blur(end);
    await waitFor(() => expect(save.disabled).toBe(false));
    fireEvent.click(save);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(12));
    expect(create).toHaveBeenCalledWith({ code: "2027-BAHAR", name: "2027 Bahar", kind: "REGULAR", start_date: "2027-02-01", end_date: "2027-06-27", week_count: 21 });
    expect((qc.getQueryData(["terms"]) as Term[]).map((x) => x.id)).toContain(12);
    await waitFor(() => expect(screen.queryByTestId("term-create-dialog")).toBeNull());
  });

  it("says so when the code is taken (409)", async () => {
    perms.list = ["planning.edit"];
    const { HttpError } = await import("@/lib/api/client");
    create.mockRejectedValue(new HttpError(409, "term code exists", { detail: "term code exists" }));
    const { select, onChange } = renderSelect();
    fireEvent.change(select, { target: { value: NEW_TERM_VALUE } });
    fireEvent.change(screen.getByTestId("term-create-code"), { target: { value: "2026-BAHAR" } });
    for (const [id, v] of [["term-create-start", "2027-02-01"], ["term-create-end", "2027-03-01"]] as const) {
      const el = screen.getByTestId(id);
      fireEvent.change(el, { target: { value: v } });
      fireEvent.blur(el);
    }
    const save = screen.getByTestId("term-create-save") as HTMLButtonElement;
    await waitFor(() => expect(save.disabled).toBe(false));
    fireEvent.click(save);
    expect((await screen.findByTestId("term-create-error")).textContent).toBe("Bu kodla bir dönem zaten var.");
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("termFromCreated", () => {
  it("fills the GET /terms shape from the POST answer", () => {
    expect(termFromCreated({ id: 5, code: "X", name: "X", start_date: null, end_date: null }, "FINAL", "2027-06-01", "2027-06-21")).toEqual({ id: 5, code: "X", name: "X", kind: "FINAL", start_date: "2027-06-01", end_date: "2027-06-21", week_count: 3, is_active: false });
  });
});
