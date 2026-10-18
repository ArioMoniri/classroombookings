/**
 * HB-E (HB-17 P1): `create_booking` takes a clock time `start` ("13:30") and the server finds the room's period.
 * The form card asks for a time field instead of a required period dropdown; the period dropdown appears only when a
 * `period_id` was already chosen ("Değiştir" on a confirm card). The form submits `start`. The server's 422
 * `time_outside_grid` and 409 `no_period_at_time` show their text at the time field (the form stays), and the
 * confirm card shows the resolved period in its "Zaman" line.
 */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useEffect, useMemo } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperApi } from "@/lib/api/helper";
import { CardHostContext } from "./cards/context";
import { formFromConfirm } from "./cards/form";
import { EntryView } from "./cards/render";
import { useHelperStore } from "./helper-store";
import { HelperCard, type ConfirmCard } from "./schema.gen";
import { card, makeHost, renderHelper, resetHelperStore } from "./test-helpers";
import { useHelperRunner } from "./use-helper-runner";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const future = () => new Date(Date.now() + 9 * 60_000).toISOString();

function Grab({ onRunner }: { onRunner: (r: ReturnType<typeof useHelperRunner>) => void }) {
  const runner = useHelperRunner();
  useEffect(() => {
    onRunner(runner);
  });
  return null;
}

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

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  vi.restoreAllMocks();
});

function pushForm(c: HelperCard = card("form_start")) {
  act(() => {
    useHelperStore.getState().pushCard(c);
  });
}

describe("create_booking with a start time", () => {
  it("asks for a time (no period dropdown) and submits start", async () => {
    const cardCall = vi.spyOn(helperApi, "card").mockResolvedValue({ ...card("confirm"), expires_at: future() } as HelperCard);
    renderHelper(<Harness />);
    pushForm();
    const start = await screen.findByTestId("helper-field-start");
    expect(start).toHaveAttribute("type", "time");
    expect(start).toBeRequired();
    expect(screen.getByLabelText("Başlangıç")).toBe(start);
    expect(screen.queryByTestId("helper-field-period_id")).toBeNull();
    fireEvent.change(start, { target: { value: "13:30" } });
    fireEvent.click(screen.getByTestId("helper-form-submit"));
    await waitFor(() => expect(cardCall).toHaveBeenCalledWith("create_booking", { room: "12", date: "2026-10-19", start: "13:30" }));
  });

  it.each([
    [422, "time_outside_grid", "21:00 saati 08:40-20:20 ders gününün dışında"],
    [409, "no_period_at_time", "A 204 için 13:35 saatinde başlayan ayrılabilir bir ders saati yok."],
  ])("a %s %s shows the server's text at the time field; the form stays", async (status, code, text) => {
    vi.spyOn(helperApi, "card").mockRejectedValue(new HttpError(status, code, { code, message_tr: text, message_en: "en text" }));
    renderHelper(<Harness />);
    pushForm();
    const start = await screen.findByTestId("helper-field-start");
    fireEvent.change(start, { target: { value: "21:00" } });
    fireEvent.click(screen.getByTestId("helper-form-submit"));
    const err = await screen.findByTestId("helper-field-error-start");
    expect(err).toHaveTextContent(text);
    expect(start).toHaveAttribute("aria-invalid", "true");
    expect(start.getAttribute("aria-describedby")).toContain(err.id);
    await waitFor(() => expect(document.activeElement).toBe(start));
    expect(screen.getByTestId("helper-form-submit")).toBeInTheDocument(); // still pending
    expect(screen.queryByTestId("helper-note-line")).toBeNull();
    // a new time clears the message
    fireEvent.change(start, { target: { value: "13:30" } });
    expect(screen.queryByTestId("helper-field-error-start")).toBeNull();
  });

  it("Değiştir on a confirm card: the chosen period stays (optional), the time is optional too", () => {
    const c = { ...card("confirm"), args: { room: "12", date: "2026-10-19", start: "", period_id: 3, notes: "" } } as ConfirmCard;
    const f = formFromConfirm(c)!;
    expect(f.fields.map((x) => [x.name, x.kind, x.required])).toEqual([
      ["room", "room", true],
      ["date", "date", true],
      ["start", "time", false],
      ["period_id", "period", false],
      ["notes", "text", false],
    ]);
    expect(f.fields.find((x) => x.name === "period_id")!.value).toBe(3);
    const noPeriod = formFromConfirm({ ...c, args: { room: "12", date: "2026-10-19", start: "13:30" } } as ConfirmCard)!;
    expect(noPeriod.fields.map((x) => x.name)).toEqual(["room", "date", "start", "notes"]);
    expect(noPeriod.fields.find((x) => x.name === "start")).toMatchObject({ required: true, value: "13:30" });
  });

  it("a shortcut's clock time goes to the server as start (no grid lookup)", async () => {
    const grid = await import("@/lib/api/crbs");
    const gridCall = vi.spyOn(grid.crbs.bookings, "grid");
    const cardCall = vi.spyOn(helperApi, "card").mockResolvedValueOnce(card("form_start")).mockResolvedValueOnce({ ...card("confirm"), expires_at: future() } as HelperCard);
    const box: { runner: ReturnType<typeof useHelperRunner> | null } = { runner: null };
    renderHelper(
      <>
        <Grab onRunner={(r) => (box.runner = r)} />
        <Harness />
      </>,
    );
    await act(async () => {
      await box.runner!.runAction("create_booking", { room: "A 204", date: "2026-10-19" }, { hints: { time: "13:30" } });
    });
    expect(cardCall).toHaveBeenLastCalledWith("create_booking", { room: "12", date: "2026-10-19", start: "13:30" });
    expect(gridCall).not.toHaveBeenCalled();
    expect(screen.getByTestId("helper-card-confirm")).toBeInTheDocument();
  });

  it("the confirm card shows the resolved period", async () => {
    renderHelper(<Harness />);
    act(() => {
      useHelperStore.getState().pushCard({ ...card("confirm"), expires_at: future() } as HelperCard);
    });
    const c = await screen.findByTestId("helper-card-confirm-create_booking");
    expect(c).toHaveTextContent("Zaman");
    expect(c).toHaveTextContent("Yarın 10:00–10:50");
  });
});
