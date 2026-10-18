/** HX-10: the faculty manager's view — sentences, the department split checked against the allowance, 422 inline. */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperAdminApi, type FacultyUsage } from "@/lib/api/helper";
import { renderHelper } from "../test-helpers";
import { FacultyUsageView, shareCheck } from "./faculty-usage";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const usage: FacultyUsage = {
  faculty: { id: 3, name: "Eczacılık Fakültesi" },
  faculties: [{ id: 3, name: "Eczacılık Fakültesi" }],
  month: "2026-10",
  allocation: { monthly_tokens: 100000, monthly_cost_usd: null },
  totals: { tokens: 42000, cost_usd: 0.4, calls: 120 },
  by_department: [
    { id: 11, name: "Farmakoloji", tokens: 30000, calls: 80, allocation: { monthly_tokens: 60000, monthly_cost_usd: null } },
    { id: 12, name: "Farmasötik Kimya", tokens: 12000, calls: 40, allocation: null },
  ],
  by_feature: [{ feature: "helper", label_tr: "Yardımcı", label_en: "Helper", tokens: 30000 }],
  trend: [{ day: "2026-10-14", tokens: 9000 }, { day: "2026-10-15", tokens: 4000 }],
  show_people: false,
  people: null,
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(helperAdminApi, "facultyUsage").mockResolvedValue(usage);
});

describe("faculty usage", () => {
  it("checks the split against the allowance", () => {
    expect(shareCheck({ a: 60000, b: 30000 }, 100000)).toEqual({ sum: 90000, over: false });
    expect(shareCheck({ a: 60000, b: 50000 }, 100000)).toEqual({ sum: 110000, over: true });
    expect(shareCheck({ a: 1 }, null)).toEqual({ sum: 1, over: false });
  });

  it("HX-18 M8: leads with the share of the allowance and the requests, with no 'token' in the copy", async () => {
    renderHelper(<FacultyUsageView />);
    expect(await screen.findByTestId("faculty-total")).toHaveTextContent("Bu ay fakülte payından %42 kullanıldı (120 istek).");
    const view = screen.getByTestId("faculty-usage");
    expect(view).toHaveTextContent("Farmakoloji80 istek · bölüm payından %50");
    expect(view).toHaveTextContent("Son günlerde en yoğun gün: 14 Ekim.");
    expect(view).toHaveTextContent("En çok kullanılan: Yardımcı");
    expect(view.textContent).not.toMatch(/token/i);
    expect(screen.queryByText("Kişiler")).toBeNull();
  });

  it("HX-18 M8: the raw units only under Gelişmiş, in plain words", async () => {
    renderHelper(<FacultyUsageView />);
    const more = await screen.findByTestId("faculty-advanced");
    expect(screen.queryByTestId("faculty-units")).toBeNull();
    fireEvent.click(more);
    expect(screen.getByTestId("faculty-units")).toHaveTextContent("Bu ay 42.000 yapay zekâ birimi kullanıldı; fakültenin aylık payı 100.000 birim.");
    expect(screen.getByTestId("faculty-usage").textContent).not.toMatch(/token/i);
  });

  it("HX-18 M8: the server's share of the allowance (HB-21) wins over the client's sum", async () => {
    vi.spyOn(helperAdminApi, "facultyUsage").mockResolvedValue({
      ...usage,
      allocation: { monthly_tokens: null, monthly_cost_usd: 5 },
      faculty: { id: 3, name: "Eczacılık Fakültesi", share_of_allowance: 0.4 },
      by_department: [{ ...usage.by_department[0]!, share_of_allowance: 0.25 }],
    } as FacultyUsage);
    renderHelper(<FacultyUsageView />);
    expect(await screen.findByTestId("faculty-total")).toHaveTextContent("Bu ay fakülte payından %40 kullanıldı (120 istek).");
    expect(screen.getByTestId("faculty-usage")).toHaveTextContent("80 istek · bölüm payından %25");
    expect(screen.getByTestId("faculty-usage")).not.toHaveTextContent("Fakülteye henüz aylık pay ayrılmadı.");
  });

  it("HX-18 M8: with no allowance it says the requests and that no share is set", async () => {
    vi.spyOn(helperAdminApi, "facultyUsage").mockResolvedValue({ ...usage, allocation: null });
    renderHelper(<FacultyUsageView />);
    expect(await screen.findByTestId("faculty-total")).toHaveTextContent("Bu ay 120 istek yapıldı.");
    expect(screen.getByTestId("faculty-usage")).toHaveTextContent("Fakülteye henüz aylık pay ayrılmadı.");
  });

  it("HX-18 M8: English uses per cent and AI units", async () => {
    renderHelper(<FacultyUsageView />, { locale: "en" });
    expect(await screen.findByTestId("faculty-total")).toHaveTextContent("42% of the faculty's allowance used this month (120 requests).");
    expect(screen.getByTestId("faculty-usage").textContent).not.toMatch(/token/i);
  });

  it("HX-18 m3: the share fields stay 16 px on a touch tablet", async () => {
    renderHelper(<FacultyUsageView />);
    const input = await screen.findByLabelText("Farmasötik Kimya: Aylık pay (yapay zekâ birimi)");
    expect(input.className).toMatch(/pointer-fine:sm:type-callout/);
  });

  it("blocks a split over the allowance with the Turkish message", async () => {
    renderHelper(<FacultyUsageView />);
    const input = await screen.findByLabelText("Farmasötik Kimya: Aylık pay (yapay zekâ birimi)");
    fireEvent.change(input, { target: { value: "50000" } });
    expect(screen.getByTestId("faculty-share-sum")).toHaveTextContent("Bölümlerin toplamı fakültenin payını aşıyor.");
    expect(screen.getByTestId("faculty-share-save")).toBeDisabled();
  });

  it("saves a valid split and shows a 422 inline", async () => {
    const put = vi.spyOn(helperAdminApi, "facultyAllocations").mockRejectedValue(new HttpError(422, "x", { code: "department_not_in_faculty", message_tr: "Bu bölüm bu fakülteye bağlı değil.", message_en: "Not in faculty." }));
    renderHelper(<FacultyUsageView />);
    fireEvent.change(await screen.findByLabelText("Farmasötik Kimya: Aylık pay (yapay zekâ birimi)"), { target: { value: "20000" } });
    fireEvent.click(screen.getByTestId("faculty-share-save"));
    await waitFor(() => expect(put).toHaveBeenCalledWith(3, { "11": { monthly_tokens: 60000 }, "12": { monthly_tokens: 20000 } }));
    expect(await screen.findByTestId("faculty-share-error")).toHaveTextContent("Bu bölüm bu fakülteye bağlı değil.");
  });

  it("a person who manages no faculty is told so", async () => {
    vi.spyOn(helperAdminApi, "facultyUsage").mockRejectedValue(new HttpError(403, "x", { code: "no_faculty", message_tr: "x" }));
    renderHelper(<FacultyUsageView />);
    expect(await screen.findByText("Yönettiğiniz bir fakülte yok.")).toBeInTheDocument();
  });
});
