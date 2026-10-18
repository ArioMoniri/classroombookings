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

  it("says the totals in sentences and hides people when the faculty does not show them", async () => {
    renderHelper(<FacultyUsageView />);
    expect(await screen.findByTestId("faculty-total")).toHaveTextContent("Bu ay 42.000 token kullanıldı (120 istek).");
    expect(screen.getByTestId("faculty-usage")).toHaveTextContent("Fakültenin aylık payı: 100.000 token.");
    expect(screen.getByTestId("faculty-usage")).toHaveTextContent("En çok kullanılan: Yardımcı");
    expect(screen.queryByText("Kişiler")).toBeNull();
  });

  it("blocks a split over the allowance with the Turkish message", async () => {
    renderHelper(<FacultyUsageView />);
    const input = await screen.findByLabelText("Farmasötik Kimya: Aylık pay (token)");
    fireEvent.change(input, { target: { value: "50000" } });
    expect(screen.getByTestId("faculty-share-sum")).toHaveTextContent("Bölümlerin toplamı fakültenin payını aşıyor.");
    expect(screen.getByTestId("faculty-share-save")).toBeDisabled();
  });

  it("saves a valid split and shows a 422 inline", async () => {
    const put = vi.spyOn(helperAdminApi, "facultyAllocations").mockRejectedValue(new HttpError(422, "x", { code: "department_not_in_faculty", message_tr: "Bu bölüm bu fakülteye bağlı değil.", message_en: "Not in faculty." }));
    renderHelper(<FacultyUsageView />);
    fireEvent.change(await screen.findByLabelText("Farmasötik Kimya: Aylık pay (token)"), { target: { value: "20000" } });
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
