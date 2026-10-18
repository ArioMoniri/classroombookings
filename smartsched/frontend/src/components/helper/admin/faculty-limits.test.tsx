/**
 * HX-10 admin side: Yönetim › Yapay zekâ › Limitler › Fakülteler. One row per faculty (monthly allowance), details
 * with this month's use in words, the department split checked against the allowance, the quota managers; the
 * cost cap and strict mode behind "Gelişmiş". Saved with `PUT /ai/admin/limits` {faculties, departments, strict};
 * the server's 422 ("bölümlerin toplamı fakülteyi aşıyor") is shown inline on the faculty it names.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { aiAdminApi, type Limits } from "@/lib/api/ai-admin";
import { catalogApi } from "@/lib/api/catalog-admin";
import { helperAdminApi, type FacultyUsage } from "@/lib/api/helper";
import { renderHelper } from "../test-helpers";
import { FacultyLimits } from "./faculty-limits";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const limits = {
  org_monthly_tokens: 1_000_000,
  org_monthly_cost_usd: 0,
  user_daily_tokens: 0,
  user_monthly_tokens: 0,
  roles: {},
  users: {},
  soft_pct: 80,
  alert_recipients: [],
  requests_per_minute: 30,
  max_concurrent: 2,
  topups: [],
  org: { month: "2026-10", month_tokens: 0, month_cost_usd: 0 },
  faculties: { "3": { monthly_tokens: 100000, monthly_cost_usd: 0, managers: [41], show_people: false } },
  departments: { "11": { monthly_tokens: 60000, monthly_cost_usd: 0 }, "99": { monthly_tokens: 5000, monthly_cost_usd: 0 } },
  strict: false,
} as unknown as Limits;

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
  by_feature: [],
  trend: [],
  show_people: false,
  people: null,
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(catalogApi, "faculties").mockResolvedValue({ items: [{ id: 3, name: "Eczacılık Fakültesi", canonical_name: "eczacilik" }, { id: 4, name: "Tıp Fakültesi", canonical_name: "tip" }], total: 2, limit: 500, offset: 0 } as never);
  vi.spyOn(helperAdminApi, "facultyUsage").mockResolvedValue(usage);
});

const openDetails = async (name: string) => {
  const row = await screen.findByTestId(`faculty-limit-${name}`);
  fireEvent.click(within(row).getByText("Bölümler ve yöneticiler"));
  return row;
};

describe("Fakülteler (admin allocation editor)", () => {
  it("lists every faculty with its allowance in words", async () => {
    renderHelper(<FacultyLimits data={limits} canEdit />);
    expect(await screen.findByLabelText("Eczacılık Fakültesi: aylık pay (token)")).toHaveValue("100000");
    expect(screen.getByTestId("faculty-limit-4")).toHaveTextContent("Pay yok: kurumun bütçesinden kullanır.");
    // advanced options stay closed
    expect(screen.getByTestId("faculty-limits-advanced")).not.toHaveAttribute("open");
  });

  it("shows this month's use and the department split, and saves faculties + departments together", async () => {
    const save = vi.spyOn(aiAdminApi, "saveLimits").mockResolvedValue(limits);
    renderHelper(<FacultyLimits data={limits} canEdit />);
    const row = await openDetails("3");
    expect(await within(row).findByText("Bu ay 42.000 token kullanıldı.")).toBeInTheDocument();
    fireEvent.change(within(row).getByLabelText("Farmasötik Kimya: aylık pay (token)"), { target: { value: "30000" } });
    expect(within(row).getByTestId("faculty-limit-sum-3")).toHaveTextContent("Bölümlere toplam 90.000 / 100.000 token.");
    fireEvent.change(screen.getByLabelText("Tıp Fakültesi: aylık pay (token)"), { target: { value: "200000" } });
    fireEvent.click(screen.getByTestId("faculty-limits-save"));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0]![0]).toEqual({
      faculties: {
        "3": { monthly_tokens: 100000, monthly_cost_usd: 0, managers: [41], show_people: false },
        "4": { monthly_tokens: 200000, monthly_cost_usd: 0, managers: [], show_people: false },
      },
      // department 99 belongs to a faculty that was not opened: kept as stored
      departments: { "11": { monthly_tokens: 60000, monthly_cost_usd: 0 }, "12": { monthly_tokens: 30000, monthly_cost_usd: 0 }, "99": { monthly_tokens: 5000, monthly_cost_usd: 0 } },
      strict: false,
    });
  });

  it("blocks a department split over the allowance with the Turkish message", async () => {
    renderHelper(<FacultyLimits data={limits} canEdit />);
    const row = await openDetails("3");
    fireEvent.change(await within(row).findByLabelText("Farmasötik Kimya: aylık pay (token)"), { target: { value: "50000" } });
    expect(within(row).getByTestId("faculty-limit-sum-3")).toHaveTextContent("Bölümlerin toplamı fakültenin payını aşıyor.");
    expect(screen.getByTestId("faculty-limits-save")).toBeDisabled();
  });

  it("shows the server's 422 inline on the faculty it names", async () => {
    vi.spyOn(aiAdminApi, "saveLimits").mockRejectedValue(
      new HttpError(422, "x", {
        code: "department_sum_exceeds_faculty",
        message_tr: "Bölümlere dağıtılan pay (105000 jeton) fakültenin payını (100000 jeton) aşıyor.",
        message_en: "The departments' allocations exceed the faculty's.",
        field: "faculties.3",
      }),
    );
    renderHelper(<FacultyLimits data={limits} canEdit />);
    await screen.findByTestId("faculty-limit-3");
    fireEvent.click(screen.getByTestId("faculty-limits-save"));
    const inline = await within(screen.getByTestId("faculty-limit-3")).findByRole("alert");
    expect(inline).toHaveTextContent("Bölümlere dağıtılan pay (105000 jeton) fakültenin payını (100000 jeton) aşıyor.");
  });

  it("keeps the managers and the people switch with the faculty, and strict mode under Gelişmiş", async () => {
    const save = vi.spyOn(aiAdminApi, "saveLimits").mockResolvedValue(limits);
    renderHelper(<FacultyLimits data={limits} canEdit />);
    const row = await openDetails("3");
    fireEvent.change(within(row).getByLabelText("Kota yöneticileri (kullanıcı numaraları)"), { target: { value: "41, 52" } });
    fireEvent.click(within(row).getByLabelText("Yöneticiler kişi bazında token toplamlarını görsün"));
    fireEvent.click(screen.getByLabelText("Fakültelerin toplamı kurumun aylık bütçesini aşamasın"));
    fireEvent.click(screen.getByTestId("faculty-limits-save"));
    await waitFor(() => expect(save).toHaveBeenCalled());
    const body = save.mock.calls[0]![0] as { faculties: Record<string, unknown>; strict: boolean };
    expect(body.faculties["3"]).toEqual({ monthly_tokens: 100000, monthly_cost_usd: 0, managers: [41, 52], show_people: true });
    expect(body.strict).toBe(true);
  });

  it("is read-only without the edit right", async () => {
    renderHelper(<FacultyLimits data={limits} canEdit={false} />);
    expect(await screen.findByLabelText("Eczacılık Fakültesi: aylık pay (token)")).toBeDisabled();
    expect(screen.queryByTestId("faculty-limits-save")).toBeNull();
  });
});
