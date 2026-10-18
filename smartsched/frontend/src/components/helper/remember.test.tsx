/**
 * HX-17 (helper.md §5.1, §17.1 #8; API.md HB-D §1): "Bunu hatırla". Typed "bunu hatırla: …" goes through
 * `POST /helper/turn` as it is (never `POST /helper/notes`); the server answers the `remember_note` confirm card, which
 * renders like every confirm card and saves only on the button. After its confirm or undo the notes, the memory count
 * and "Son işlemler" are refetched. In Rehber modu (no composer) the typed text offers one "Bunu hatırla: …" row that
 * sends the same turn. The client's label for the action is "Bunu hatırla" / "Remember this".
 */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useEffect, useMemo } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi, helperKeys } from "@/lib/api/helper";
import { CardHostContext } from "./cards/context";
import { EntryView } from "./cards/render";
import { GuideMode } from "./guide";
import { useHelperStore } from "./helper-store";
import { clientActionLabel, rememberText } from "./remember";
import { HelperCard, type ConfirmCard } from "./schema.gen";
import type { TurnEvent } from "./stream";
import { makeHost, renderHelper, resetHelperStore } from "./test-helpers";
import { activation, useHelperRunner } from "./use-helper-runner";

const stream = vi.fn<(text: string, lang: string, on: (e: TurnEvent) => void, opts?: unknown) => Promise<void>>();
vi.mock("./stream", async (orig) => ({ ...(await orig<typeof import("./stream")>()), streamTurn: (text: string, lang: string, on: (e: TurnEvent) => void, opts?: unknown) => stream(text, lang, on, opts) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const NOTE = "Pazartesi sabahları B blokta ders veriyorum";
const remember: ConfirmCard = HelperCard.parse({
  v: 1,
  id: "7a7b7c7d",
  type: "confirm",
  action: "remember_note",
  risk: "R1",
  title: { tr: "Bunu hatırlayayım mı?", en: "Shall I remember this?" },
  token: "eyJrIjoicmVtZW1iZXIifQ.c2ln",
  expires_at: new Date(Date.now() + 9 * 60_000).toISOString(),
  preview: [{ label: { tr: "Not", en: "Note" }, value: { tr: NOTE, en: NOTE } }],
  warnings: [{ tr: "Notlarınızı Profil › Yardımcı'da görebilir ve silebilirsiniz.", en: "You can see and delete your notes in Profile › Helper." }],
  button: { tr: `Hatırla: ${NOTE}`, en: `Remember: ${NOTE}` },
  undoable: true,
  danger: false,
  args: { text: NOTE },
}) as ConfirmCard;
const saved = HelperCard.parse({
  v: 1,
  id: "7a7b7c7e",
  type: "result",
  action: "remember_note",
  ok: true,
  message: { tr: `Not kaydedildi: ${NOTE}`, en: `Note saved: ${NOTE}` },
  entity: { kind: "note", id: 7, feature_id: "profile.helper_memory" },
  undo_token: "eyJrIjoidW5kbyJ9.bm90ZQ",
  undo_expires_at: new Date(Date.now() + 24 * 3600_000).toISOString(),
  follow_ups: [{ label: { tr: "Notlarım", en: "My notes" }, feature_id: "profile.helper_memory" }],
});
const undone = HelperCard.parse({ v: 1, id: "7a7b7c7f", type: "result", action: "remember_note", ok: true, message: { tr: "Geri alındı; not silindi.", en: "Undone; the note was deleted." } });

/** Hands the real runner to the test. */
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
  const host = useMemo(() => makeHost({ runner, actionVerb: clientActionLabel("tr") }), [runner]);
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
  stream.mockReset();
  vi.restoreAllMocks();
});

describe("rememberText (the server's detect)", () => {
  it("finds the person's words after a remember request at the start", () => {
    expect(rememberText(`bunu hatırla: ${NOTE}`)).toBe(NOTE);
    expect(rememberText(`BUNU HATIRLA - ${NOTE}`)).toBe(NOTE);
    expect(rememberText(`Şunu hatırla: ${NOTE}`)).toBe(NOTE);
    expect(rememberText(`hatırla: ${NOTE}`)).toBe(NOTE);
    expect(rememberText(`aklında tut: ${NOTE}`)).toBe(NOTE);
    expect(rememberText("remember this: I teach in block B")).toBe("I teach in block B");
    expect(rememberText("remember that I teach in block B")).toBe("I teach in block B");
  });
  it("is not a question about the past and not anywhere but the start", () => {
    expect(rememberText("bunu hatırla: hangi salondu?")).toBeNull();
    expect(rememberText("geçen hafta ne demiştim, hatırla: B blok")).toBeNull();
    expect(rememberText("hatırlatma kur")).toBeNull();
  });
});

describe("typed bunu hatırla goes through /turn", () => {
  it("sends the text as it is and renders the server's remember confirm card (not the fallback)", async () => {
    const add = vi.spyOn(helperApi, "addNote");
    stream.mockImplementation(async (_t, _l, on) => {
      on({ type: "run_started", turnId: "abcdef0123456789" });
      on({ type: "card", card: remember });
      on({ type: "run_finished", mode: "index", outcome: "confirm", fallback: null, reason: null });
    });
    const box: { runner: ReturnType<typeof useHelperRunner> | null } = { runner: null };
    renderHelper(
      <>
        <Grab onRunner={(r) => (box.runner = r)} />
        <Harness />
      </>,
    );
    await act(async () => {
      await box.runner!.ask(`bunu hatırla: ${NOTE}`);
    });
    expect(stream.mock.calls[0]![0]).toBe(`bunu hatırla: ${NOTE}`);
    expect(add).not.toHaveBeenCalled();
    const c = await screen.findByTestId("helper-card-confirm-remember_note");
    expect(c).toHaveTextContent("Bunu hatırlayayım mı?");
    expect(c).toHaveTextContent(NOTE);
    expect(screen.getByTestId("helper-card-confirm")).toHaveTextContent(`Hatırla: ${NOTE}`);
    expect(screen.queryByTestId("helper-card-fallback")).toBeNull();
  });

  it("confirm and undo refetch the notes, the memory and Son işlemler", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    const confirm = vi.spyOn(helperApi, "confirm").mockResolvedValue(saved);
    const undo = vi.spyOn(helperApi, "undo").mockResolvedValue(undone);
    const { qc } = renderHelper(<Harness />);
    const inval = vi.spyOn(qc, "invalidateQueries");
    act(() => {
      useHelperStore.getState().pushCard(remember);
    });
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(remember.token));
    expect(await screen.findByTestId("helper-card-result-remember_note")).toHaveTextContent(`Not kaydedildi: ${NOTE}`);
    for (const key of [helperKeys.notes, helperKeys.memory, helperKeys.recent]) expect(inval).toHaveBeenCalledWith({ queryKey: key });
    inval.mockClear();
    fireEvent.click(screen.getByTestId("helper-card-undo"));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("eyJrIjoidW5kbyJ9.bm90ZQ"));
    await waitFor(() => expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.notes }));
    expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.memory });
    expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.recent });
  });

  it("a booking's confirm refetches Son işlemler only", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    const booking = HelperCard.parse({ ...saved, action: "create_booking", entity: { kind: "booking", id: 5, feature_id: "my_bookings" }, follow_ups: [] });
    vi.spyOn(helperApi, "confirm").mockResolvedValue(booking);
    const { qc } = renderHelper(<Harness />);
    const inval = vi.spyOn(qc, "invalidateQueries");
    act(() => {
      useHelperStore.getState().pushCard({ ...remember, action: "create_booking" } as HelperCard);
    });
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.recent }));
    expect(inval).not.toHaveBeenCalledWith({ queryKey: helperKeys.notes });
  });
});

describe("the action's label", () => {
  it("Bunu hatırla / Remember this", () => {
    expect(clientActionLabel("tr")("remember_note")).toBe("Bunu hatırla");
    expect(clientActionLabel("en")("remember_note")).toBe("Remember this");
    expect(clientActionLabel("tr")("create_booking")).toBeNull();
  });
});

describe("Rehber modu", () => {
  it("typed bunu hatırla offers one row that sends the same turn", async () => {
    const host = makeHost();
    renderHelper(<GuideMode />, { host });
    fireEvent.change(screen.getByTestId("helper-guide-input"), { target: { value: `bunu hatırla: ${NOTE}` } });
    const row = await screen.findByTestId("helper-guide-remember");
    expect(row).toHaveTextContent(`Bunu hatırla: ${NOTE}`);
    fireEvent.click(row);
    expect(host.runner.ask).toHaveBeenCalledWith(`bunu hatırla: ${NOTE}`);
  });

  it("no row for a question", async () => {
    vi.spyOn(helperApi, "search").mockResolvedValue({ q: "", question: true, pages: [], where: [], data: {}, skipped: [], timing_ms: 1 });
    renderHelper(<GuideMode />, { host: makeHost() });
    fireEvent.change(screen.getByTestId("helper-guide-input"), { target: { value: "bunu hatırla: hangi salondu?" } });
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.queryByTestId("helper-guide-remember")).toBeNull();
  });
});
