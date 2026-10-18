/** HX-09: /admin/ai › Yardımcı — mode, audiences, actions with risk words, Gelişmiş, stale save, sentence tiles. */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperAdminApi, type HelperAdmin } from "@/lib/api/helper";
import { renderHelper } from "../test-helpers";
import { HelperAdminTab } from "./helper-admin";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const T = (tr: string, en = tr) => ({ tr, en });
const data = (over: Partial<HelperAdmin["settings"]> = {}, version = "v1"): HelperAdmin => ({
  settings: {
    enabled: true,
    mode: "ai",
    audiences: { academician: true, admin: true },
    actions: { create_booking: { enabled: true, audiences: null }, decide_approval: { enabled: true, audiences: null } },
    memory: { enabled: true, retention_days: 180 },
    history_days: 30,
    feedback_notes: true,
    guard: { scope: "normal" },
    ...over,
  },
  version,
  effective: { mode: "index", reason: "not_routed", message: T("Yardımcı rehber modunda.") },
  catalog: {
    audiences: [{ id: "academician", label: T("Öğretim elemanı") }, { id: "admin", label: T("Yönetici") }],
    actions: [
      { name: "create_booking", kind: "write", risk: "R1", summary: T("Rezerve et"), risk_label: T("Kendi rezervasyonu") },
      { name: "decide_approval", kind: "write", risk: "R2", summary: T("Talebi onayla ya da reddet"), risk_label: T("Başkalarını etkiler") },
    ],
    scopes: [{ id: "normal", label: T("Normal"), hint: null }],
  },
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(helperAdminApi, "get").mockResolvedValue(data());
  vi.spyOn(helperAdminApi, "summary").mockResolvedValue({
    days: 7,
    k_min: 5,
    tiles: [
      { id: "questions", tr: "Son 7 günde 312 soru; %71'i doğrudan sayfaya yönlendirildi.", en: "312 questions" },
      { id: "modes", tr: "Soruların 192'si dizinden yanıtlandı.", en: "" },
      { id: "actions", tr: "31 rezervasyon yardımcıdan yapıldı.", en: "" },
      { id: "thumbs", tr: "Yanıtların %88'i yararlı bulundu.", en: "" },
    ],
    misses: [{ query: "yemekhane menusu", users: 6, count: 9 }],
  });
});

describe("Yardımcı tab", () => {
  it("shows the effective state, the risk words and the 4 sentence tiles", async () => {
    renderHelper(<HelperAdminTab />);
    expect(await screen.findByTestId("helper-admin-effective")).toHaveTextContent("Yardımcı rehber modunda.");
    expect(screen.getByTestId("helper-admin-action-create_booking")).toHaveTextContent("Kendi rezervasyonu");
    expect(screen.getByTestId("helper-admin-action-decide_approval")).toHaveTextContent("Başkalarını etkiler");
    expect(await screen.findByTestId("helper-summary-tile-0")).toHaveTextContent("%71'i doğrudan sayfaya");
    expect(screen.getAllByTestId(/^helper-summary-tile-/)).toHaveLength(4);
    expect(screen.getByTestId("helper-summary")).toHaveTextContent("“yemekhane menusu” · 6 kişi");
    // memory and retention sit behind Gelişmiş
    expect(screen.queryByLabelText("Not saklama süresi (gün)")).toBeNull();
    fireEvent.click(screen.getByTestId("helper-admin-advanced"));
    expect(screen.getByLabelText("Not saklama süresi (gün)")).toBeInTheDocument();
  });

  it("switching create_booking off and the mode to Yalnızca dizin saves with the version", async () => {
    const put = vi.spyOn(helperAdminApi, "put").mockResolvedValue(data({ mode: "index" }, "v2"));
    renderHelper(<HelperAdminTab />);
    const row = await screen.findByTestId("helper-admin-action-create_booking");
    fireEvent.click(row.querySelector("[role=switch]")!);
    fireEvent.click(screen.getByTestId("helper-admin-mode-index"));
    fireEvent.click(screen.getByTestId("helper-admin-save"));
    await waitFor(() => expect(put).toHaveBeenCalled());
    const body = put.mock.calls[0]![0];
    expect(body.version).toBe("v1");
    expect(body.mode).toBe("index");
    expect(body.actions?.create_booking).toEqual({ enabled: false, audiences: null });
  });

  it("a stale save says so and reloads", async () => {
    vi.spyOn(helperAdminApi, "put").mockRejectedValue(new HttpError(409, "stale", { code: "stale_settings", message_tr: "x", message_en: "x" }));
    renderHelper(<HelperAdminTab />);
    fireEvent.click(await screen.findByTestId("helper-admin-save"));
    expect(await screen.findByTestId("helper-admin-error")).toHaveTextContent("Başka bir yönetici ayarları değiştirdi.");
    await waitFor(() => expect(helperAdminApi.get).toHaveBeenCalledTimes(2));
  });
});
