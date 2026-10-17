/** F-01 S05, S09, S10: Taleplerim — the status word, the rejection reason on the card, withdraw asks first. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { dateFormatter } from "@/components/bookings/date-format";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ rows: [] as unknown[], withdraw: vi.fn() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string } = {}) => {
    if (path === "/approvals/mine") return state.rows;
    const m = /^\/approvals\/(\d+)\/withdraw$/.exec(path);
    if (m && opts.method === "POST") return state.withdraw(Number(m[1]));
    throw new Error(`unexpected ${path}`);
  },
}));

import { MyRequests } from "./my-requests";

const booking = (date: string, p: number) => ({ id: p, date, start_period: p, end_period: p, period_name: `${p}. ders`, status: "PENDING", room_id: 7 });
const req = (id: number, status: string, extra: Record<string, unknown> = {}) => ({
  id,
  status,
  step: 1,
  steps: 1,
  room_id: 7,
  room_name: "A 202",
  requester_name: "Pınar Tekin",
  requested_at: "2026-02-16T08:00:00",
  bookings: [booking("2026-02-19", 3)],
  decisions: [],
  approvers: [{ id: 1, name: "Onay Yöneticisi" }],
  competing: [],
  ...extra,
});

function renderMine(locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <MyRequests fmt={dateFormatter(null, locale)} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("MyRequests (Taleplerim)", () => {
  beforeEach(() => {
    state.withdraw.mockReset();
    state.rows = [
      req(1, "PENDING"),
      req(2, "REJECTED", {
        reason_code: "room_unavailable",
        note: "Bu saatte bölüm sınavı var.",
        decided_by: { id: 1, name: "Onay Yöneticisi" },
        decisions: [{ step: 1, approver_name: "Onay Yöneticisi", decision: "REJECTED", reason_code: "room_unavailable", note: "Bu saatte bölüm sınavı var.", decided_at: "2026-02-16T09:00:00" }],
      }),
      req(3, "APPROVED"),
      req(4, "WITHDRAWN"),
    ];
  });

  it("shows Bekliyor / Reddedildi / Onaylandı / Geri çekildi and the rejection reason on the card", async () => {
    renderMine();
    const list = await screen.findByTestId("my-requests");
    expect(list).toHaveTextContent("1 bekliyor");
    const status = (id: number) => list.querySelector(`[data-request-id="${id}"] [data-status]`)!.textContent;
    expect(status(1)).toBe("Bekliyor");
    expect(status(2)).toBe("Reddedildi");
    expect(status(3)).toBe("Onaylandı");
    expect(status(4)).toBe("Geri çekildi");
    expect(within(list.querySelector('[data-request-id="2"]')!).getByTestId("request-reason-line")).toHaveTextContent("Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var.");
    // expanded: the reason block names who decided; the timeline repeats the reason
    await userEvent.click(screen.getByTestId("my-request-2"));
    expect(screen.getByTestId("request-reason")).toHaveTextContent("Karar veren: Onay Yöneticisi");
    expect(screen.getByTestId("request-timeline")).toHaveTextContent("Oda uygun değil: Bu saatte bölüm sınavı var.");
    // only an open request can be withdrawn
    expect(screen.queryByTestId("withdraw-2")).toBeNull();
  });

  it("withdraw asks first; cancel sends nothing, confirm calls the backend", async () => {
    state.withdraw.mockImplementation(async (id: number) => req(id, "WITHDRAWN"));
    renderMine();
    await userEvent.click(await screen.findByTestId("my-request-1"));
    await userEvent.click(screen.getByTestId("withdraw-1"));
    const dialog = await screen.findByTestId("withdraw-confirm");
    expect(dialog).toHaveTextContent("A 202 talebi geri çekilsin mi?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Vazgeç" }));
    expect(state.withdraw).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("withdraw-1"));
    await userEvent.click(await screen.findByTestId("withdraw-confirm-button"));
    await waitFor(() => expect(state.withdraw).toHaveBeenCalledWith(1));
  });

  it("T-R1-13: a two-period submission is one row with one status and the whole span; withdraw takes both", async () => {
    const two = (id: number, p: number, status = "PENDING") => req(id, status, { group_id: 9, bookings: [{ ...booking("2026-10-22", p), id, time_start: p === 6 ? "12:40" : "13:30", time_end: p === 6 ? "13:20" : "14:10" }] });
    state.rows = [two(5, 6), two(6, 7)];
    state.withdraw.mockImplementation(async (id: number) => req(id, "WITHDRAWN"));
    renderMine();
    const list = await screen.findByTestId("my-requests");
    expect(list.querySelectorAll("ul > li")).toHaveLength(1);
    expect(list).toHaveTextContent("1 bekliyor");
    const row = within(list).getByTestId("my-request-group");
    expect(row.getAttribute("data-status")).toBe("PENDING");
    expect(within(row).getByTestId("group-slot-line")).toHaveTextContent("P6–P7 (12:40–14:10)");
    await userEvent.click(screen.getByTestId("my-request-5"));
    await userEvent.click(screen.getByTestId("withdraw-group-9"));
    await userEvent.click(await screen.findByTestId("withdraw-confirm-button"));
    await waitFor(() => expect(state.withdraw).toHaveBeenCalledTimes(2));
    expect(state.withdraw.mock.calls.map((c) => c[0])).toEqual([5, 6]);
  });

  it("reads in English", async () => {
    renderMine("en");
    const list = await screen.findByTestId("my-requests");
    expect(list.querySelector('[data-request-id="4"] [data-status]')!.textContent).toBe("Withdrawn");
    expect(within(list.querySelector('[data-request-id="2"]')!).getByTestId("request-reason-line")).toHaveTextContent("Reason: Room unavailable: Bu saatte bölüm sınavı var.");
  });
});
