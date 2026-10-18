/**
 * HX-04: the card renderer and the confirm / undo plumbing (helper.md §4.1, §4.2, §4.6).
 * Every wire type renders from the backend-validated fixtures; an unknown write action falls back; only a trusted
 * click on the card's button confirms (typed "evet" never does); an expired token shows "Yenile"; a 409 brings the
 * new preview; focus after confirm and after undo is the result line, never <body>; nothing renders a server URL.
 */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { useMemo } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperApi } from "@/lib/api/helper";
import { useHelperStore, type CardEntry } from "../helper-store";
import { HelperCard } from "../schema.gen";
import { card, makeHost, renderHelper, resetHelperStore, type FixtureName } from "../test-helpers";
import { activation, useHelperRunner } from "../use-helper-runner";
import { CardHostContext } from "./context";
import { EntryView } from "./render";

const stream = vi.fn();
vi.mock("../stream", async (orig) => ({ ...(await orig<typeof import("../stream")>()), streamTurn: (...a: unknown[]) => stream(...a) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const entry = (name: FixtureName, over: Partial<CardEntry> = {}): CardEntry => {
  const c = card(name);
  return { kind: "card", key: `k-${name}`, card: c, phase: c.type === "confirm" || c.type === "form" || c.type === "choice" ? "pending" : "done", ...over };
};

const future = () => new Date(Date.now() + 9 * 60_000).toISOString();

/** The real runner over the store, like the sheet. */
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
  resetHelperStore();
  stream.mockReset();
});
afterEach(() => vi.restoreAllMocks());

describe("card renderer", () => {
  const all: [FixtureName, string][] = [
    ["answer", "helper-card-answer"],
    ["nav", "helper-card-nav"],
    ["list", "helper-card-list-find_free_rooms"],
    ["facts", "helper-card-facts-my_ai_usage"],
    ["choice", "helper-card-choice-create_booking"],
    ["form", "helper-card-form-create_booking"],
    ["confirm", "helper-card-confirm-create_booking"],
    ["result", "helper-card-result-create_booking"],
    ["limit", "helper-card-limit"],
    ["refusal", "helper-card-refusal"],
    ["error", "helper-card-error"],
  ];

  it.each(all)("renders the %s wire type", (name, testId) => {
    const e = entry(name, name === "confirm" ? { card: { ...card("confirm"), expires_at: future() } as HelperCard } : {});
    const { container } = renderHelper(<EntryView entry={e} />, { host: makeHost() });
    expect(screen.getByTestId(testId)).toBeInTheDocument();
    // the server never supplies a URL: no link carries one
    expect(container.querySelectorAll("a[href]")).toHaveLength(0);
  });

  it("shows at most 5 list rows and the rest on the page", () => {
    const host = makeHost();
    renderHelper(<EntryView entry={entry("list")} />, { host });
    expect(screen.getAllByTestId(/^helper-row-r\d$/)).toHaveLength(5);
    fireEvent.click(screen.getByTestId("helper-list-more"));
    expect(host.go).toHaveBeenCalledWith("/find-room");
  });

  it("a row action asks the action's card with the row's args (no model call)", () => {
    const host = makeHost();
    renderHelper(<EntryView entry={entry("list")} />, { host });
    fireEvent.click(within(screen.getByTestId("helper-row-r1")).getByRole("button", { name: "Ayır: A 201" }));
    expect(host.runner.runAction).toHaveBeenCalledWith("create_booking", { room: "101", date: "2026-10-19" });
  });

  it("nav: path line, Göster with an anchor, and nothing for an id the client cannot map or the person cannot open", () => {
    const host = makeHost();
    const { unmount } = renderHelper(<EntryView entry={entry("nav")} />, { host });
    expect(screen.getByTestId("helper-where-path")).toHaveTextContent("Yönetim › Dönem ve saatler › Tatiller");
    fireEvent.click(screen.getByTestId("helper-show"));
    expect(host.showMe).toHaveBeenCalledWith("admin.holidays");
    unmount();
    const unknown = { ...card("nav"), feature_id: "not.there" } as HelperCard;
    const a = renderHelper(<EntryView entry={{ ...entry("nav"), card: unknown }} />, { host });
    expect(a.container).toBeEmptyDOMElement();
    a.unmount();
    const b = renderHelper(<EntryView entry={entry("nav")} />, { host: makeHost({ can: () => false }) });
    expect(b.container).toBeEmptyDOMElement();
  });

  it("names the note an answer used (Notunuza göre)", () => {
    const c = HelperCard.parse({ ...card("answer"), notes_used: ["Tercih edilen bina: B blok"] });
    renderHelper(<EntryView entry={{ ...entry("answer"), card: c }} />, { host: makeHost() });
    expect(screen.getByTestId("helper-notes-used")).toHaveTextContent("Notunuza göre: Tercih edilen bina: B blok");
  });

  it("an unknown write action falls back to text + Menüde ara", () => {
    const odd = { ...card("confirm"), action: "transfer_money" } as HelperCard;
    renderHelper(<EntryView entry={{ ...entry("confirm"), card: odd }} />, { host: makeHost() });
    expect(screen.getByTestId("helper-card-fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("helper-card-confirm")).toBeNull();
  });

  it("Yalnızca metin turns a list into one line of text", () => {
    renderHelper(<EntryView entry={entry("list")} />, { host: makeHost({ textOnly: true }) });
    expect(screen.getByTestId("helper-card-list-find_free_rooms")).toHaveAttribute("data-text-only");
    expect(screen.getByText(/A 201, A 202/)).toBeInTheDocument();
  });

  it("an expired token reads 'Bu öneri eskidi.' with Yenile", () => {
    const host = makeHost();
    renderHelper(<EntryView entry={entry("confirm")} />, { host });
    expect(screen.getByTestId("helper-card-expired")).toHaveTextContent("Bu öneri eskidi.");
    fireEvent.click(screen.getByTestId("helper-card-refresh"));
    expect(host.runner.refresh).toHaveBeenCalled();
    expect(screen.queryByTestId("helper-card-confirm")).toBeNull();
  });

  it("R2 names who is affected", () => {
    renderHelper(<EntryView entry={entry("confirm_r2", { card: { ...card("confirm_r2"), expires_at: future() } as HelperCard })} />, { host: makeHost() });
    expect(screen.getByTestId("helper-card-affected")).toHaveTextContent("P. T.'ye bildirim gider.");
  });

  it("has no axe violations in the fixtures", async () => {
    const names: FixtureName[] = ["answer", "nav", "list", "facts", "choice", "form", "confirm", "result", "limit"];
    const { container } = renderHelper(
      <div>
        {names.map((n) => (
          <EntryView key={n} entry={entry(n, n === "confirm" ? { card: { ...card("confirm"), expires_at: future() } as HelperCard } : {})} />
        ))}
      </div>,
      { host: makeHost() },
    );
    const res = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
});

describe("confirm / undo plumbing", () => {
  function pushConfirm() {
    const c = { ...card("confirm"), expires_at: future() } as HelperCard;
    act(() => {
      useHelperStore.getState().pushCard(c);
    });
  }

  it("a non-trusted click does not confirm", async () => {
    const confirm = vi.spyOn(helperApi, "confirm");
    renderHelper(<Harness />);
    pushConfirm();
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("typed 'evet' does not confirm and says to press the button", async () => {
    const confirm = vi.spyOn(helperApi, "confirm");
    let runner: ReturnType<typeof useHelperRunner> | null = null;
    function Grab() {
      runner = useHelperRunner();
      return null;
    }
    renderHelper(
      <>
        <Grab />
        <Harness />
      </>,
    );
    pushConfirm();
    await act(async () => {
      await runner!.ask("evet");
    });
    expect(confirm).not.toHaveBeenCalled();
    expect(stream).not.toHaveBeenCalled();
    expect(screen.getByTestId("helper-note-line")).toHaveTextContent("Onaylamak için karttaki düğmeye basın.");
  });

  it("a trusted click confirms once, moves the focus to the result line, and Geri al undoes", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    const confirm = vi.spyOn(helperApi, "confirm").mockResolvedValue(card("result"));
    const undone = { ...card("result"), id: "6a6b6c6e", undo_token: null, message: { tr: "Rezervasyon iptal edildi.", en: "Booking cancelled." } } as HelperCard;
    const undo = vi.spyOn(helperApi, "undo").mockResolvedValue(undone);
    renderHelper(<Harness />);
    pushConfirm();
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(card("confirm").type === "confirm" ? (card("confirm") as { token: string }).token : ""));
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-testid", "helper-card-result"));
    expect(document.activeElement).not.toBe(document.body);
    fireEvent.click(screen.getByTestId("helper-card-undo"));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("eyJrIjoidW5kbyJ9.c2ln"));
    await waitFor(() => expect(document.activeElement).toHaveTextContent("Rezervasyon iptal edildi."));
    expect(screen.getByTestId("helper-card-undone")).toHaveTextContent("Geri alındı.");
  });

  it("a 409 changed shows the new preview to confirm again", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    const fresh = { ...card("confirm"), id: "5a5b5c5f", token: "bmV3.dG9rZW4", expires_at: future() };
    vi.spyOn(helperApi, "confirm").mockRejectedValue(new HttpError(409, "changed", { code: "changed", message_tr: "Önizleme değişti.", message_en: "Changed.", card: fresh }));
    renderHelper(<Harness />);
    pushConfirm();
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(screen.getByText("Önizleme değişti; yeni hâlini kontrol edip tekrar onaylayın.")).toBeInTheDocument());
    // the old card is parked, the new one waits for the button
    expect(screen.getAllByTestId("helper-card-confirm")).toHaveLength(1);
    expect(screen.getByText("Rezervasyon · bekliyor")).toBeInTheDocument();
  });

  it("a taken slot keeps the card with the server's message", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    vi.spyOn(helperApi, "confirm").mockRejectedValue(new HttpError(409, "conflict", { code: "conflict", message_tr: "Bu saat az önce doldu.", message_en: "This slot was just taken." }));
    renderHelper(<Harness />);
    pushConfirm();
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(screen.getByTestId("helper-card-error")).toHaveTextContent("Bu saat az önce doldu."));
    expect(screen.getByTestId("helper-card-confirm")).toBeEnabled();
  });

  it("a new pending card parks the older one (one card in focus)", async () => {
    renderHelper(<Harness />);
    pushConfirm();
    act(() => {
      useHelperStore.getState().pushCard(card("form"));
    });
    expect(await screen.findByText("Rezervasyon · bekliyor")).toBeInTheDocument();
    expect(screen.getByTestId("helper-card-form-create_booking")).toBeInTheDocument();
  });

  it("a shortcut's clock time resolves the period and goes straight to the confirm card (A1)", async () => {
    const grid = await import("@/lib/api/crbs");
    vi.spyOn(grid.crbs.bookings, "grid").mockResolvedValue({ periods: [{ id: 3, name: "3", time_start: "10:00", time_end: "10:50", start_period: 3, end_period: 3 }] } as never);
    const cardCall = vi.spyOn(helperApi, "card").mockResolvedValueOnce(card("form")).mockResolvedValueOnce({ ...card("confirm"), expires_at: future() } as HelperCard);
    let runner: ReturnType<typeof useHelperRunner> | null = null;
    function Grab() {
      runner = useHelperRunner();
      return null;
    }
    renderHelper(
      <>
        <Grab />
        <Harness />
      </>,
    );
    await act(async () => {
      await runner!.runAction("create_booking", { room: "A 204", date: "2026-10-19" }, { hints: { time: "10:00" } });
    });
    expect(cardCall).toHaveBeenLastCalledWith("create_booking", { room: "12", date: "2026-10-19", period_id: 3 });
    expect(screen.getByTestId("helper-card-confirm")).toBeInTheDocument();
    expect(screen.queryByTestId("helper-card-form-create_booking")).toBeNull();
  });
});
