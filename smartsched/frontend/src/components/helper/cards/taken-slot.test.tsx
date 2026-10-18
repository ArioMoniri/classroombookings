/**
 * FIX-D / HB18-F03 (docs/testing/round4/2026-10-18-hb18.md): the helper's refusals come as FastAPI bodies,
 * `{"detail": {"code", "message_tr", "message_en", "alternatives", …}}`. `ApiError` keeps an object `detail` as the
 * whole body, and `helperRefusal` read `code` one level too high, so a slot taken before the click read
 * "Yanıt alınamadı." with "Rezerve et" still offered. Now: the server's words, no "Rezerve et", "Başka saat öner"
 * and the free rooms of the same slot.
 */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useMemo } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperApi, helperRefusal } from "@/lib/api/helper";
import { useHelperStore } from "../helper-store";
import type { HelperCard } from "../schema.gen";
import { card, makeHost, renderHelper, resetHelperStore } from "../test-helpers";
import { activation, useHelperRunner } from "../use-helper-runner";
import { CardHostContext } from "./context";
import { EntryView } from "./render";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

/** The exact 409 body of `POST /helper/actions/confirm` for a slot taken in between (backend test_fix_a). */
const TAKEN = {
  detail: {
    code: "conflict",
    message_tr: "Bu saat az önce doldu.",
    message_en: "This slot was just taken.",
    conflict: { kind: "booking" },
    alternatives: [
      { room_id: 31, code: "B101", name: "B 101", capacity: 40, start_period: 3, end_period: 3, status: "free", reason: null },
      { room_id: 32, code: "B102", name: "B 102", capacity: 30, start_period: 3, end_period: 3, status: "requestable", reason: null },
    ],
  },
};

function Harness() {
  const runner = useHelperRunner();
  const entries = useHelperStore((s) => s.entries);
  const host = useMemo(() => makeHost({ runner }), [runner]);
  return (
    <CardHostContext.Provider value={host}>
      {entries.map((e) => (
        <div key={e.key} data-entry={e.key} tabIndex={-1}>
          <EntryView entry={e} />
        </div>
      ))}
    </CardHostContext.Provider>
  );
}

const future = () => new Date(Date.now() + 9 * 60_000).toISOString();

beforeEach(() => resetHelperStore());
afterEach(() => vi.restoreAllMocks());

describe("helperRefusal reads FastAPI's {detail: {...}} (HB18-F03)", () => {
  it("unwraps the object detail the API client keeps as the whole body", () => {
    const r = helperRefusal(new HttpError(409, "409 Conflict", TAKEN));
    expect(r).toMatchObject({ status: 409, code: "conflict", tr: "Bu saat az önce doldu.", en: "This slot was just taken." });
    expect(r.alternatives.map((a) => a.room_id)).toEqual([31, 32]);
  });

  it("still reads an already flat detail", () => {
    expect(helperRefusal(new HttpError(409, "x", { code: "already_done", message_tr: "Bu işlem zaten yapıldı." }))).toMatchObject({ code: "already_done", tr: "Bu işlem zaten yapıldı." });
  });

  it("goes through the real request client (fetch → HttpError → refusal)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(TAKEN), { status: 409, headers: { "content-type": "application/json" } }));
    const err = await helperApi.confirm("tok").catch((e: unknown) => e);
    expect(helperRefusal(err)).toMatchObject({ status: 409, code: "conflict", tr: "Bu saat az önce doldu." });
  });

  it("409 already_done in the real shape marks the card done", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    vi.spyOn(helperApi, "confirm").mockRejectedValue(new HttpError(409, "x", { detail: { code: "already_done", message_tr: "Bu işlem zaten yapıldı.", message_en: "This was already done." } }));
    renderHelper(<Harness />);
    act(() => void useHelperStore.getState().pushCard({ ...card("confirm"), expires_at: future() } as HelperCard));
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(screen.getByTestId("helper-card-error")).toHaveTextContent("Bu işlem zaten yapılmış."));
    expect(screen.queryByTestId("helper-card-confirm")).toBeNull();
  });
});

describe("a slot taken before the click (HB18-F03)", () => {
  async function takenCard() {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    vi.spyOn(helperApi, "confirm").mockRejectedValue(new HttpError(409, "409 Conflict", TAKEN));
    const cardCall = vi.spyOn(helperApi, "card").mockResolvedValue({ ...card("confirm"), id: "7a7b7c7d", expires_at: future() } as HelperCard);
    renderHelper(<Harness />);
    act(() => void useHelperStore.getState().pushCard({ ...card("confirm"), expires_at: future() } as HelperCard));
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(screen.getByTestId("helper-card-error")).toHaveTextContent("Bu saat az önce doldu."));
    return cardCall;
  }

  it("shows the server's words, drops 'Rezerve et', offers 'Başka saat öner' and the free rooms", async () => {
    await takenCard();
    expect(screen.queryByText("Yanıt alınamadı. Arama ve kısayollar çalışıyor.")).toBeNull();
    expect(screen.queryByTestId("helper-card-confirm")).toBeNull();
    expect(screen.getByTestId("helper-card-other-time")).toHaveTextContent("Başka saat öner");
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(screen.getAllByTestId("helper-card-alt-room").map((r) => r.textContent)).toEqual(["B 101 · 40 kişilik", "B 102 · 30 kişilik"]);
  });

  it("a free room asks for its own confirm card (same day and period)", async () => {
    const cardCall = await takenCard();
    fireEvent.click(screen.getAllByTestId("helper-card-alt-room")[0]!);
    await waitFor(() => expect(cardCall).toHaveBeenCalledWith("create_booking", expect.objectContaining({ room: "31", date: "2026-10-19", period_id: 3 })));
  });

  it("'Başka saat öner' opens the free-room search for that day", async () => {
    const cardCall = await takenCard();
    fireEvent.click(screen.getByTestId("helper-card-other-time"));
    await waitFor(() => expect(cardCall).toHaveBeenCalledWith("find_free_rooms", { date: "2026-10-19" }));
  });
});
