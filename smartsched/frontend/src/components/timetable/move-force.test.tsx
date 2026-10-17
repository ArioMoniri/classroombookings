/**
 * Round-1 R1-M-06 / R1-S-09: an administrator can force a move that breaks a hard rule from the timetable - the move
 * dialog lists what breaks and offers "Move anyway" with a required written reason; a planner only reads that an
 * administrator can do it. The reason is passed on to the bulk move (force + reason).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fixtureIndex } from "@/test/fixtures/calendar-index";
import { I18nProvider } from "@/lib/i18n/provider";
import { MoveDialog } from "./move-dialog";
import { buildModel, eventsOf } from "./model/index-model";

const model = buildModel(fixtureIndex());
const ev = eventsOf(model, 1, 3).find((e) => e.a.label === "BME 419 §1")!;

function stubServer() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = String(url).includes("move-preview")
        ? { ok: false, applied: false, dry_run: true, items: [{ aid: ev.a.id, label: "BME 419 §1", ok: false, hard: [{ code: "capacity", severity: "hard", text: { tr: "102 öğrenci 58 kişilik A 101'e sığmaz", en: "102 students do not fit A 101 (58 seats)" } }], soft: [], day: 3, start_period: 7, end_period: 9, room_ids: [2], room_codes: ["A 101"], weeks: [], moved_ids: [], split_ids: [] }], ok_count: 0, conflict_count: 1, assignments: [], undo: null }
        : { run_id: 42, day: 3, start_period: 7, end_period: 9, weeks: [], size: 102, rooms: [{ room_id: 2, code: "A 101", building: "A", capacity: 58, tags: [], status: "too_small", fit: null, reason: { tr: "102 öğrenci 58 kişilik A 101'e sığmaz", en: "102 students do not fit A 101 (58 seats)" }, with_label: null }] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
}

function renderDialog(canForce: boolean, onConfirm = vi.fn(async () => true)) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <MoveDialog model={model} ev={ev} week={3} open onOpenChange={() => undefined} onConfirm={onConfirm} canForce={canForce} initialTarget={{ room: 2, day: 3, sp: 7 }} />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return onConfirm;
}

afterEach(() => vi.unstubAllGlobals());

describe("forcing a move from the timetable (R1-M-06)", () => {
  it("an administrator sees what breaks and moves anyway only with a written reason", async () => {
    stubServer();
    const onConfirm = renderDialog(true);
    expect(await screen.findByTestId("move-force-panel")).toBeInTheDocument();
    expect((await screen.findAllByText(/sığmaz/)).length).toBeGreaterThan(0);
    const force = screen.getByTestId("move-force");
    expect(force).toBeDisabled();
    expect(screen.getByTestId("move-confirm")).toBeDisabled();
    await userEvent.type(screen.getByTestId("move-force-reason"), "ab");
    expect(force).toBeDisabled(); // at least 3 characters
    await userEvent.type(screen.getByTestId("move-force-reason"), "c bölüm onayı");
    expect(force).toBeEnabled();
    await userEvent.click(force);
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    expect(onConfirm).toHaveBeenCalledWith({ room: 2, day: 3, sp: 7, ep: 9 }, expect.objectContaining({ scope: "all" }), "abc bölüm onayı");
  });

  it("a planner reads that only an administrator can do it, and gets no force button", async () => {
    stubServer();
    renderDialog(false);
    expect(await screen.findByTestId("move-force-admin-only")).toHaveTextContent("yalnızca yönetici");
    expect(screen.queryByTestId("move-force")).toBeNull();
  });
});
