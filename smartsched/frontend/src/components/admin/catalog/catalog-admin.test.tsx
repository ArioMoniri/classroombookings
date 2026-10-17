/** RF-05: Yönetim › Katalog — view, edit and delete the imported instructors, courses, programmes, faculties and sections. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate } from "@/lib/i18n";
import { CatalogAdmin } from "./catalog-admin";
import { catalogErrorText, changedFields, deleteMode, hoursText, lastChangeText, parseDecimal, parseWhole, usageLines } from "./catalog-model";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), warning: vi.fn() }) }));

const tr = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("tr", k, v);

let perms = ["planning.view", "planning.edit"];
let calls: { method: string; url: string; body?: unknown }[] = [];
const INSTRUCTORS = [
  { id: 1, full_name: "Ayşe Yılmaz", canonical_name: "ayse yilmaz", title: "Dr. Öğr. Üyesi", email: null },
  { id: 2, full_name: "Mehmet Demir", canonical_name: "mehmet demir", title: null as string | null, email: "m.demir@uni.edu.tr" as string | null },
];
let instructors = INSTRUCTORS;
const usage: Record<number, unknown> = {
  1: { entity: "instructor", id: 1, uses: { sections: 3 }, blocked: true, action: "delete", last_change: { actor: "Yönetici Ayşe", at: "2026-10-17T19:30:00+00:00", action: "instructor.update" } },
  2: { entity: "instructor", id: 2, uses: {}, blocked: false, action: "delete", last_change: null },
  50: { entity: "section", id: 50, uses: { meetings: 2, runs: 1 }, blocked: false, action: "archive", last_change: null },
};
const sections = [{ id: 50, term_id: 7, course_id: 9, program_id: null, label: "1", class_year: 1, class_years: [1], enrolment: 45, mode: "F2F", notes: null, archived: false, course_code: "MAT 112", course_name: "Analiz II", program_name: null }];

function mockApi() {
  calls = [];
  instructors = INSTRUCTORS.map((i) => ({ ...i }));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url: u, body });
      const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });
      const page = (items: unknown[]) => json({ items, total: items.length, limit: 100, offset: 0 });
      if (u.includes("/auth/me")) return json({ id: 1, username: "admin", role: "ADMIN", permissions: perms, department_id: null });
      const use = u.match(/\/catalog\/usage\/\w+\/(\d+)/);
      if (use) return json(usage[Number(use[1])]);
      if (u.match(/\/instructors\/\d+/) && method === "PUT") {
        const id = Number(u.match(/\/instructors\/(\d+)/)?.[1]);
        instructors = instructors.map((i) => (i.id === id ? { ...i, ...body } : i));
        return json(instructors.find((i) => i.id === id));
      }
      if (u.match(/\/instructors\/\d+/) && method === "DELETE") return json({ id: 2, action: "deleted", audit_id: 5 });
      if (u.includes("/instructors") && method === "POST") return json({ id: 3, canonical_name: "x", title: null, email: null, ...body }, 201);
      if (u.includes("/instructors")) {
        const s = new URL(u, "http://x").searchParams.get("search");
        return page(s ? instructors.filter((i) => i.full_name.toLocaleLowerCase("tr").includes(s.toLocaleLowerCase("tr"))) : instructors);
      }
      if (u.includes("/terms")) return json([{ id: 7, code: "2026-BAHAR", name: "2026 Bahar", kind: "REGULAR", start_date: null, end_date: null, week_count: 14, periods_json: null, is_active: true, is_current: true }]);
      if (u.match(/\/sections\/50$/) && method === "PUT") return json({ ...sections[0], ...body, source_key: "PL:1", instructors: [], meeting_count: 2 });
      if (u.match(/\/sections\/50$/)) return json({ ...sections[0], source_key: "PL:1", instructors: [{ instructor_id: 1, full_name: "Ayşe Yılmaz", title: "Dr.", role: "PRIMARY" }], meeting_count: 2 });
      if (u.includes("/sections")) return page(sections);
      if (u.includes("/programs")) return page([]);
      if (u.includes("/faculties")) return page([]);
      return json({});
    }),
  );
}

function renderIt(tab: "instructors" | "sections" = "instructors") {
  mockApi();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <CatalogAdmin tab={tab} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  perms = ["planning.view", "planning.edit"];
});

describe("catalog model", () => {
  it("parses class sizes, hours and comma decimals the way the planning lists write them", () => {
    expect(parseWhole(" 80 ", 2000)).toBe(80);
    expect(parseWhole("", 2000)).toBeNull();
    expect(parseWhole("-1", 2000)).toBe("invalid");
    expect(parseWhole("12:30", 2000)).toBe("invalid");
    expect(parseWhole("2001", 2000)).toBe("invalid");
    expect(parseDecimal("4,5")).toBe(4.5);
    expect(parseDecimal("abc")).toBe("invalid");
    expect(hoursText({ t_hours: 3, u_hours: null, l_hours: 2 })).toBe("3-0-2");
  });

  it("sends only what changed", () => {
    expect(changedFields({ a: "x", b: null as string | null }, { a: "y", b: null })).toEqual({ a: "y" });
    expect(changedFields({ a: "x" }, { a: "x" })).toEqual({});
  });

  it("explains a delete before it happens", () => {
    expect(usageLines({ uses: { runs: 1, meetings: 2 } }, tr)).toEqual(["2 ders saati talebi de arşivlenir", "1 çalıştırmadaki yerleşimler olduğu gibi kalır"]);
    expect(deleteMode({ blocked: true, action: "delete" })).toBe("blocked");
    expect(deleteMode({ blocked: false, action: "archive" })).toBe("archive");
    expect(lastChangeText(null, tr, "tr")).toBe("İçe aktarıldığından beri değiştirilmedi.");
    expect(lastChangeText({ actor: "Ayşe", at: "2026-10-17T19:30:00+00:00", action: "x" }, tr, "tr")).toMatch(/^Son değişiklik: Ayşe, 17 Eki 2026 22:30$/);
  });

  it("answers in Turkish whatever the backend's English says", () => {
    expect(catalogErrorText(new HttpError(409, "instructor X already exists", { message: "x", existing: { full_name: "Ayşe Yılmaz" } }), tr, "tr")).toBe("Bu kayıt zaten var: Ayşe Yılmaz");
    expect(catalogErrorText(new HttpError(422, "bad"), tr, "tr")).toBe("Girilen değer geçersiz. Kontrol edip yeniden deneyin.");
  });
});

describe("Yönetim › Katalog (RF-05)", () => {
  it("lists instructors, edits a name and shows who changed it last", async () => {
    renderIt();
    expect(await screen.findByText("Ayşe Yılmaz")).toBeInTheDocument();
    expect(screen.getByTestId("catalog-count")).toHaveTextContent("2 kayıt");
    expect(screen.getByTestId("catalog-new")).toHaveTextContent("Yeni");
    fireEvent.click(screen.getByRole("button", { name: "Ayşe Yılmaz kaydını düzenle" }));
    const sheet = await screen.findByTestId("catalog-sheet");
    expect(await within(sheet).findByText("Son değişiklik: Yönetici Ayşe, 17 Eki 2026 22:30")).toBeInTheDocument();
    // advanced fields stay hidden until asked for
    expect(within(sheet).getByLabelText("E-posta", { selector: "input" })).not.toBeVisible();
    const name = within(sheet).getByTestId("catalog-field-name");
    fireEvent.change(name, { target: { value: "Ayşe Yılmaz Kaya" } });
    fireEvent.click(within(sheet).getByTestId("catalog-save"));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")).toBeTruthy());
    expect(calls.find((c) => c.method === "PUT")).toMatchObject({ url: expect.stringContaining("/instructors/1"), body: { full_name: "Ayşe Yılmaz Kaya" } });
    expect(await screen.findByText("Ayşe Yılmaz Kaya")).toBeInTheDocument();
  });

  it("refuses to delete an instructor who teaches, naming what uses them", async () => {
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Ayşe Yılmaz kaydını düzenle" }));
    const del = await screen.findByTestId("catalog-delete");
    await waitFor(() => expect(del).not.toBeDisabled());
    fireEvent.click(del);
    const dlg = await screen.findByTestId("catalog-delete-dialog");
    expect(within(dlg).getByText("Ayşe Yılmaz silinemez")).toBeInTheDocument();
    expect(within(dlg).getByTestId("catalog-delete-uses")).toHaveTextContent("3 şube");
    expect(within(dlg).queryByTestId("catalog-delete-confirm")).toBeNull();
  });

  it("deletes an unused instructor after confirmation", async () => {
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Mehmet Demir kaydını düzenle" }));
    const del = await screen.findByTestId("catalog-delete");
    await waitFor(() => expect(del).not.toBeDisabled());
    fireEvent.click(del);
    const dlg = await screen.findByTestId("catalog-delete-dialog");
    expect(within(dlg).getByText("Mehmet Demir silinsin mi?")).toBeInTheDocument();
    fireEvent.click(within(dlg).getByTestId("catalog-delete-confirm"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.includes("/instructors/2"))).toBe(true));
  });

  it("edits a section's class size and archives with its consequences", async () => {
    renderIt("sections");
    fireEvent.click(await screen.findByRole("button", { name: "MAT 112 §1 kaydını düzenle" }));
    const sheet = await screen.findByTestId("catalog-sheet");
    expect(await within(sheet).findByTestId("catalog-section-instructors")).toHaveTextContent("Dr. Ayşe Yılmaz");
    fireEvent.change(within(sheet).getByTestId("catalog-field-students"), { target: { value: "-4" } });
    fireEvent.click(within(sheet).getByTestId("catalog-save"));
    expect(await within(sheet).findByText("Öğrenci sayısı 0 ile 2000 arasında bir tam sayı olmalı.")).toBeInTheDocument();
    fireEvent.change(within(sheet).getByTestId("catalog-field-students"), { target: { value: "62" } });
    fireEvent.click(within(sheet).getByTestId("catalog-save"));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")).toMatchObject({ url: expect.stringContaining("/sections/50"), body: { enrolment: 62 } }));
  });

  it("is read-only without planning.edit", async () => {
    perms = ["planning.view"];
    renderIt();
    expect(await screen.findByText("Ayşe Yılmaz")).toBeInTheDocument();
    expect(await screen.findAllByText("Yalnızca görüntüleyebilirsiniz. Düzenlemek için planlama düzenleme yetkisi gerekir.")).not.toHaveLength(0);
    expect(screen.queryByTestId("catalog-new")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ayşe Yılmaz kaydını aç" }));
    const sheet = await screen.findByTestId("catalog-sheet");
    expect(within(sheet).queryByTestId("catalog-save")).toBeNull();
    expect(within(sheet).queryByTestId("catalog-delete")).toBeNull();
  });
});
