/**
 * F-05 S03 (P19-T2) "Tercih ekle": the sheet sends only the chosen kind's fields for the classes picked, shows the
 * summary before sending and the server's `effective` after; every refusal code reads as TR/EN text, and a time
 * wish on a class whose time the department fixed explains why. Real Bahar rows: R601 PTL 102 §1 (Tue P4, asked
 * C 601) and PTL 184 §1.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { Matching } from "@/lib/api/moderation";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ posted: [] as unknown[], reply: null as null | ((body: unknown) => unknown) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path === "/bookings/rooms") return [
      { id: 32, code: "C 301", name: "C 301", capacity: 72, tags: [], fields: [] },
      { id: 50, code: "C 601", name: "C 601", capacity: 72, tags: [], fields: [] },
      { id: 7, code: "A 306", name: "A 306", capacity: 40, tags: [], fields: [] },
    ];
    if (path === "/moderation/me/preferences" && opts.method === "POST") {
      state.posted.push(opts.body);
      return state.reply!(opts.body);
    }
    throw new Error(`unexpected ${opts.method ?? "GET"} ${path}`);
  },
}));

import { WishSheet } from "./wish-sheet";

const row = (request_id: number, label: string, start: number | null): Matching =>
  Matching.parse({
    request_id,
    section_id: request_id + 1000,
    term_id: 1,
    label,
    requested: { day: start ? 2 : null, start_period: start, end_period: start ? start + 1 : null, rooms: ["C 601"] },
    definitive: { rooms: ["C 601"] },
    verdict: "not_evaluated",
    verdict_text: { tr: "Değerlendirilmedi", en: "Not evaluated" },
    priority: { value: 0, source: "default" },
  });
const classes = [row(590, "PTL 102 §1", 4), row(801, "PTL 184 §1", null)];
const created = (body: { request_ids: number[] }) => ({
  submission: "fe71960fd30a",
  status: "pending",
  items: [{ id: 40, constraint_id: 40, term_id: 1, status: "pending", kind: "room_preference", request_ids: body.request_ids, labels: ["PTL 102 §1"], text: { tr: "PTL 102 §1: oda tercihi C 301", en: "PTL 102 §1: room preference C 301" } }],
  effective: { tr: "Koordinatör onaylarsa bir sonraki çözümde bölüm talebinden sonra gelen bir tercih olarak uygulanır", en: "If the coordinator accepts it, it applies at the next solve, ranked below the department's request" },
});
const refuse = (status: number, code: string, message_tr: string, message: string) => () => {
  throw new HttpError(status, message, { detail: { code, message, message_tr } });
};

function renderSheet(locale: "tr" | "en" = "tr", initial = [590]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <WishSheet open onOpenChange={() => undefined} classes={classes} initial={initial} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("Tercih ekle sheet", () => {
  beforeEach(() => {
    state.posted = [];
    state.reply = (b) => created(b as { request_ids: number[] });
  });

  it("preselects the row's class, shows the summary before sending and the server's effective text after", async () => {
    const user = userEvent.setup();
    renderSheet();
    const sheet = await screen.findByTestId("wish-sheet");
    expect(within(sheet).getByRole("checkbox", { name: /PTL 102 §1/ })).toBeChecked();
    expect(within(sheet).getByRole("checkbox", { name: /PTL 184 §1/ })).not.toBeChecked();
    await user.click(await within(sheet).findByRole("checkbox", { name: /C 301/ }));
    expect(within(sheet).getByTestId("wish-summary")).toHaveTextContent("PTL 102 §1: oda tercihi C 301");
    expect(within(sheet).getByTestId("wish-summary")).toHaveTextContent("bölüm talebinden sonra gelir");
    await user.type(within(sheet).getByTestId("wish-note"), "deney düzeneği bu binada");
    await user.click(within(sheet).getByTestId("wish-submit"));
    await waitFor(() => expect(state.posted).toHaveLength(1));
    expect(state.posted[0]).toEqual({ kind: "room_preference", request_ids: [590], room_ids: [32], note: "deney düzeneği bu binada" });
    const sent = await screen.findByTestId("wish-sent");
    expect(sent).toHaveTextContent("PTL 102 §1: oda tercihi C 301");
    expect(screen.getByText(/Koordinatör onaylarsa bir sonraki çözümde/)).toBeInTheDocument();
  });

  it("refuses an empty wish without calling the server", async () => {
    const user = userEvent.setup();
    renderSheet("en", []);
    await user.click(await screen.findByTestId("wish-submit"));
    expect(screen.getByTestId("wish-issues")).toHaveTextContent("Select at least one class.");
    expect(screen.getByTestId("wish-issues")).toHaveTextContent("Select at least one room.");
    expect(state.posted).toHaveLength(0);
  });

  it("explains that the department form fixes the time (fixed_by_department), before and after sending", async () => {
    const user = userEvent.setup();
    state.reply = refuse(422, "fixed_by_department", "Bölüm formu PTL 102 §1 için gün ve saati sabitliyor; saat tercihi bunu değiştiremez (koordinatöre danışın)", "the department form fixes the day and time of PTL 102 §1");
    renderSheet();
    await user.click(await screen.findByTestId("wish-kind-day_window"));
    expect(screen.getByTestId("wish-fixed")).toHaveTextContent("gün ve saatini bölüm formu sabitliyor");
    await user.selectOptions(screen.getByTestId("wish-latest"), "6");
    await user.click(screen.getByTestId("wish-submit"));
    const err = await screen.findByTestId("wish-error");
    expect(state.posted[0]).toEqual({ kind: "day_window", request_ids: [590], latest: 6 });
    expect(err).toHaveTextContent("Bölüm formu bu dersin gün ve saatini sabitliyor; saat tercihi bunu değiştiremez.");
    expect(err).toHaveTextContent("PTL 102 §1 için gün ve saati sabitliyor");
  });

  it.each([
    ["already_requested", 422, "The department form already asks for this for these classes; no preference is needed."],
    ["not_yours", 403, "You can add preferences only for the classes you teach."],
    ["room_closed", 422, "This room is not used for classes; choose another room."],
    ["too_many_pending", 409, "Many of your preferences are waiting for review; add a new one once some are decided."],
  ])("reads %s in English", async (code, status, text) => {
    const user = userEvent.setup();
    state.reply = refuse(status, code, "", "server words");
    renderSheet("en");
    await user.click(await screen.findByRole("checkbox", { name: /C 301/ }));
    await user.click(screen.getByTestId("wish-submit"));
    expect(await screen.findByTestId("wish-error")).toHaveTextContent(text);
  });

  it("adds a typed room code for rooms the account cannot list, and a building wish", async () => {
    const user = userEvent.setup();
    renderSheet("tr", [590, 801]);
    await user.type(await screen.findByTestId("wish-room-search"), "c302{Enter}");
    expect(screen.getByTestId("wish-rooms-picked")).toHaveTextContent("C 302");
    await user.click(screen.getByTestId("wish-submit"));
    await waitFor(() => expect(state.posted).toHaveLength(1));
    expect(state.posted[0]).toEqual({ kind: "room_preference", request_ids: [590, 801], rooms: ["C 302"] });
  });

  it("sends a building wish from the chips", async () => {
    const user = userEvent.setup();
    renderSheet("tr");
    await user.click(await screen.findByTestId("wish-kind-building_preference"));
    await user.click(await screen.findByTestId("wish-building-A"));
    expect(screen.getByTestId("wish-summary")).toHaveTextContent("PTL 102 §1: A blok tercihi");
    await user.click(screen.getByTestId("wish-submit"));
    await waitFor(() => expect(state.posted[0]).toEqual({ kind: "building_preference", request_ids: [590], buildings: ["A"] }));
  });
});
