/**
 * F-05 S03 (P19-T2) "Tercih ekle": the sheet sends only the chosen kind's fields for the classes picked; before
 * sending, the server previews the same body (`?dry_run=1`, debounced) and the summary shows its own `items[].text`
 * and `effective` (a local sentence only while it loads); a preview refusal reads like the real one. Rooms come
 * from `GET /moderation/me/rooms`, grouped by building with the capacity; typed codes are still accepted. Every
 * refusal code reads as TR/EN text, and a time wish on a class whose time the department fixed explains why. Real
 * Bahar rows: R601 PTL 102 §1 (Tue P4, asked C 601) and PTL 184 §1; real server answers in
 * __fixtures__/wish-preview-bahar.json.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { Matching } from "@/lib/api/moderation";
import { I18nProvider } from "@/lib/i18n/provider";
import fx from "./__fixtures__/wish-preview-bahar.json";

// every test waits for the debounced server preview (400 ms) besides typing: more than vitest's 5 s on a loaded runner
vi.setConfig({ testTimeout: 20_000 });

const state = vi.hoisted(() => ({
  posted: [] as unknown[],
  previewed: [] as unknown[],
  reply: null as null | ((body: unknown) => unknown),
  preview: null as null | ((body: unknown) => unknown),
  rooms: null as null | (() => unknown),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}) => {
    if (path === "/moderation/me/rooms") return state.rooms!();
    if (path === "/moderation/me/preferences" && opts.method === "POST" && opts.query?.dry_run) {
      state.previewed.push(opts.body);
      return state.preview!(opts.body);
    }
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
/** the real dry-run answers: a building wish previews as the building answer, everything else as the room one */
const previewOf = (body: unknown) => ((body as { kind: string }).kind === "building_preference" ? fx.preview_building : fx.preview_room);
const real = (answer: { detail: unknown }, status = 422) => () => {
  throw new HttpError(status, `${status}`, answer);
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
    state.previewed = [];
    state.reply = (b) => created(b as { request_ids: number[] });
    state.preview = previewOf;
    state.rooms = () => fx.rooms;
  });

  it("preselects the row's class, shows the summary before sending and the server's effective text after", async () => {
    const user = userEvent.setup();
    renderSheet();
    const sheet = await screen.findByTestId("wish-sheet");
    expect(within(sheet).getByRole("checkbox", { name: /PTL 102 §1/ })).toBeChecked();
    expect(within(sheet).getByRole("checkbox", { name: /PTL 184 §1/ })).not.toBeChecked();
    await user.click(await within(sheet).findByRole("checkbox", { name: /C 301/ }));
    // the local sentence only while the server's preview is on its way, then the server's own words
    const summary = within(sheet).getByTestId("wish-summary");
    expect(summary).toHaveAttribute("data-source", "local");
    expect(summary).toHaveTextContent("PTL 102 §1: oda tercihi C 301");
    await waitFor(() => expect(summary).toHaveAttribute("data-source", "server"));
    expect(within(summary).getByTestId("wish-summary-item")).toHaveTextContent("PTL 102 §1: oda tercihi C 301");
    expect(within(summary).getByTestId("wish-effective")).toHaveTextContent(fx.preview_room.effective.tr);
    expect(summary).toHaveTextContent("bölüm talebinden sonra gelir");
    expect(state.previewed.at(-1)).toEqual({ kind: "room_preference", request_ids: [590], room_ids: [32] });
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
    expect(state.previewed).toHaveLength(0);
    expect(screen.getByTestId("wish-summary")).toHaveAttribute("data-source", "none");
  });

  it("explains that the department form fixes the time (fixed_by_department), before and after sending", async () => {
    const user = userEvent.setup();
    state.reply = real(fx.refused_fixed);
    state.preview = real(fx.refused_fixed);
    renderSheet();
    await user.click(await screen.findByTestId("wish-kind-day_window"));
    expect(screen.getByTestId("wish-fixed")).toHaveTextContent("gün ve saatini bölüm formu sabitliyor");
    await user.selectOptions(screen.getByTestId("wish-latest"), "6");
    // the server's preview already says no, in the same words a submit would
    const pre = await screen.findByTestId("wish-preview-error");
    expect(pre).toHaveTextContent("Bu haliyle gönderilemez:");
    expect(pre.querySelector("[data-code]")).toHaveAttribute("data-code", "fixed_by_department");
    expect(pre).toHaveTextContent("Bölüm formu PTL 102 §1 için gün ve saati sabitliyor");
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

  it("groups the rooms by building with the capacity, searches code, block and tags", async () => {
    const user = userEvent.setup();
    renderSheet();
    const list = await screen.findByTestId("wish-room-list");
    const groups = within(list).getAllByTestId("wish-room-group");
    expect(groups.map((g) => g.getAttribute("data-building"))).toEqual(["A", "C"]);
    expect(groups[0]).toHaveTextContent("A Blok · 2 oda");
    expect(groups[1]).toHaveTextContent("C Blok · 3 oda");
    expect(within(groups[1]!).getAllByTestId("wish-room").map((r) => r.getAttribute("data-code"))).toEqual(["C301", "C302", "C601"]);
    expect(within(groups[1]!).getAllByTestId("wish-room")[0]).toHaveTextContent("72 kişilik");
    const search = screen.getByTestId("wish-room-search");
    await user.type(search, "pc");
    expect(within(screen.getByTestId("wish-room-list")).getAllByTestId("wish-room").map((r) => r.getAttribute("data-code"))).toEqual(["A103"]);
    await user.clear(search);
    await user.type(search, "c blok");
    expect(within(screen.getByTestId("wish-room-list")).getAllByTestId("wish-room")).toHaveLength(3);
    await user.clear(search);
    await user.type(search, "zz");
    expect(screen.getByTestId("wish-rooms-none")).toBeInTheDocument();
  });

  it("takes a typed code: a listed room by its id, any other code as typed (the server checks it)", async () => {
    const user = userEvent.setup();
    renderSheet("tr", [590, 801]);
    await screen.findByTestId("wish-room-list");
    await user.type(screen.getByTestId("wish-room-search"), "c302{Enter}");
    expect(screen.getByTestId("wish-rooms-picked")).toHaveTextContent("C 302");
    expect(screen.getByRole("checkbox", { name: /C 302/ })).toBeChecked();
    state.preview = real(fx.refused_unknown_room);
    await user.type(screen.getByTestId("wish-room-search"), "z999{Enter}");
    expect(screen.getByTestId("wish-rooms-picked")).toHaveTextContent("Z 999");
    const pre = await screen.findByTestId("wish-preview-error");
    expect(pre.querySelector("[data-code]")).toHaveAttribute("data-code", "unknown_room");
    expect(pre).toHaveTextContent("Bilinmeyen oda: Z 999");
    state.reply = (b) => created(b as { request_ids: number[] });
    await user.click(screen.getByTestId("wish-submit"));
    await waitFor(() => expect(state.posted).toHaveLength(1));
    expect(state.posted[0]).toEqual({ kind: "room_preference", request_ids: [590, 801], room_ids: [33], rooms: ["Z 999"] });
  });

  it("an account without the room list (403 not_linked) still types codes", async () => {
    const user = userEvent.setup();
    state.rooms = () => {
      throw new HttpError(403, "403", { detail: { code: "not_linked", message: "no instructor record is linked to this account", message_tr: "Bu hesaba bağlı öğretim elemanı kaydı yok" } });
    };
    renderSheet();
    expect(await screen.findByTestId("wish-rooms-typed-hint")).toHaveTextContent("oda kodunu");
    await user.type(screen.getByTestId("wish-room-search"), "c 404");
    await user.click(screen.getByTestId("wish-room-add-code"));
    expect(screen.getByTestId("wish-rooms-picked")).toHaveTextContent("C 404");
  });

  it("sends a building wish from the chips", async () => {
    const user = userEvent.setup();
    renderSheet("tr");
    await user.click(await screen.findByTestId("wish-kind-building_preference"));
    await user.click(await screen.findByTestId("wish-building-A"));
    await waitFor(() => expect(screen.getByTestId("wish-summary")).toHaveAttribute("data-source", "server"));
    expect(screen.getByTestId("wish-summary-item")).toHaveTextContent("PTL 102 §1: A blok tercihi");
    expect(state.previewed.at(-1)).toEqual({ kind: "building_preference", request_ids: [590], buildings: ["A"] });
    await user.click(screen.getByTestId("wish-submit"));
    await waitFor(() => expect(state.posted[0]).toEqual({ kind: "building_preference", request_ids: [590], buildings: ["A"] }));
  });

  it("reads a preview refusal in English (already_requested, real answer) and asks again when the form changes", async () => {
    const user = userEvent.setup();
    state.preview = (b) => ((b as { buildings?: string[] }).buildings?.includes("C") ? real(fx.refused_already_requested)() : previewOf(b));
    renderSheet("en");
    await user.click(await screen.findByTestId("wish-kind-building_preference"));
    await user.click(await screen.findByTestId("wish-building-C"));
    const pre = await screen.findByTestId("wish-preview-error");
    expect(pre).toHaveTextContent("This cannot be sent as it is:");
    expect(pre).toHaveTextContent("The department form already asks for this for these classes; no preference is needed.");
    await user.click(screen.getByTestId("wish-building-C"));
    await user.click(screen.getByTestId("wish-building-A"));
    await waitFor(() => expect(screen.getByTestId("wish-summary-item")).toHaveTextContent("PTL 102 §1: building A preferred"));
    expect(screen.queryByTestId("wish-preview-error")).toBeNull();
  });
});
