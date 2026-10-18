/**
 * HX-03 (helper.md §2.4, §2.5, §5.3, §8): the sheet — non-modal on desktop, a modal dialog with a focus trap on
 * phones; focus in on open and back to the opener on Esc; F6; the chip; Rehber modu with no model; a limit disables
 * the composer with the reason while search and shortcuts stay; ⌘J (not on a run page); hidden when switched off.
 */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi, type HelperStatus } from "@/lib/api/helper";
import fixtures from "./__fixtures__/cards.json";
import { HelperRoot } from "./helper-root";
import { HelperSheet } from "./helper-sheet";
import { useHelperStore } from "./helper-store";
import type { TurnEvent } from "./stream";
import { renderHelper, resetHelperStore } from "./test-helpers";
import { HelperCard } from "./schema.gen";

let pathname = "/reserve";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => pathname, useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ can: () => true, perms: [] }),
  useMeFull: () => ({ data: { id: 1, permissions: [] }, isLoading: false }),
}));
let usage: Record<string, unknown> | undefined;
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: usage }) }));
const stream = vi.fn<(text: string, lang: string, on: (e: TurnEvent) => void) => Promise<void>>();
vi.mock("./stream", async (orig) => ({ ...(await orig<typeof import("./stream")>()), streamTurn: (text: string, lang: string, on: (e: TurnEvent) => void) => stream(text, lang, on) }));

function media(desktop: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: q.includes("min-width: 1024px") ? desktop : false,
    media: q,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "cloud", provider_label: { tr: "Anthropic (Claude)", en: "Anthropic (Claude)" }, fallback_active: false, message: null, ...over });

function open(opener?: HTMLElement) {
  act(() => useHelperStore.getState().openSheet({ opener: opener ?? null }));
}

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  usage = undefined;
  pathname = "/reserve";
  stream.mockReset();
  vi.restoreAllMocks();
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
  vi.spyOn(helperApi, "memory").mockResolvedValue({ institution_enabled: true, enabled: true, notes: 2, max_notes: 20, max_chars: 200, retention_days: 180, history_days: 30 });
  vi.spyOn(helperApi, "search").mockResolvedValue({ q: "tatil", question: false, pages: [HelperCard.parse(fixtures.nav)] as never, where: [], data: {}, skipped: [], timing_ms: 1 });
});

describe("helper sheet", () => {
  it("desktop: a non-modal complementary sheet; focus goes to the composer; Esc closes and returns focus", async () => {
    media(true);
    const { getByText } = renderHelper(
      <>
        <button type="button">Ara veya sor</button>
        <main id="main" tabIndex={-1} />
        <HelperSheet />
      </>,
    );
    const opener = getByText("Ara veya sor");
    opener.focus();
    open(opener);
    const sheet = await screen.findByTestId("helper-sheet");
    expect(sheet).toHaveAttribute("role", "complementary");
    expect(sheet).not.toHaveAttribute("aria-modal");
    expect(sheet).toHaveAccessibleName("Yardımcı");
    const field = await screen.findByRole("textbox", { name: "Yardımcıya yazın" });
    await waitFor(() => expect(document.activeElement).toBe(field));
    expect(await screen.findByTestId("helper-status")).toHaveTextContent("Bulut · Anthropic (Claude)");
    expect(screen.getByTestId("helper-memory-used")).toHaveTextContent("2 notunuzu kullanıyorum");
    fireEvent.keyDown(field, { key: "Escape" });
    await waitFor(() => expect(useHelperStore.getState().open).toBe(false));
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("desktop: F6 moves the focus between the page and the sheet", async () => {
    media(true);
    renderHelper(
      <>
        <main id="main" tabIndex={-1} />
        <HelperSheet />
      </>,
    );
    open();
    const field = await screen.findByRole("textbox", { name: "Yardımcıya yazın" });
    await waitFor(() => expect(document.activeElement).toBe(field));
    fireEvent.keyDown(window, { key: "F6" });
    expect(document.activeElement).toBe(document.getElementById("main"));
    fireEvent.keyDown(window, { key: "F6" });
    expect(document.activeElement).toBe(field);
  });

  it("phone: a modal dialog with a 44 px Kapat and a focus trap", async () => {
    media(false);
    renderHelper(<HelperSheet />);
    open();
    const sheet = await screen.findByTestId("helper-sheet");
    expect(sheet).toHaveAttribute("role", "dialog");
    expect(sheet).toHaveAttribute("aria-modal", "true");
    expect(sheet).toHaveAccessibleName("Yardımcı");
    const close = screen.getByTestId("helper-close");
    expect(close).toHaveAccessibleName("Kapat");
    expect(close.className).toContain("size-11");
    close.focus();
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(sheet.contains(document.activeElement)).toBe(true);
  });

  it("Rehber modu in index mode: a search field and no composer; nothing is streamed", async () => {
    media(true);
    vi.spyOn(helperApi, "status").mockResolvedValue(status({ mode: "index", reason: "not_routed", provider_kind: null, provider_label: null }));
    renderHelper(<HelperSheet />);
    open();
    const field = await screen.findByTestId("helper-guide-input");
    expect(screen.queryByTestId("helper-composer")).toBeNull();
    expect(screen.getByTestId("helper-guide")).toHaveTextContent("Rehber modu");
    fireEvent.change(field, { target: { value: "tatil" } });
    expect(await screen.findByTestId("helper-card-nav")).toHaveTextContent("Tatiller");
    expect(stream).not.toHaveBeenCalled();
    expect(screen.getByTestId("helper-status")).toHaveTextContent("Yapay zekâ kapalı");
  });

  it("at the limit the composer is disabled with the reason; the search stays", async () => {
    media(true);
    usage = { state: "hard", pct: 100 };
    renderHelper(<HelperSheet />);
    open();
    expect(await screen.findByTestId("helper-blocked")).toHaveTextContent("Yardımcı bu ay sınırda");
    expect(screen.getByRole("textbox", { name: "Yardımcıya yazın" })).toBeDisabled();
    expect(screen.getByTestId("helper-guide-input")).toBeInTheDocument();
    expect(screen.getByTestId("helper-status")).toHaveTextContent("Sınıra ulaşıldı");
  });

  it("asks the palette's question once open and shows the streamed cards", async () => {
    media(true);
    let release: () => void = () => undefined;
    stream.mockImplementation(async (_t, _l, on) => {
      on({ type: "run_started", turnId: "abcdef0123456789" });
      on({ type: "tool_start", name: "find_free_rooms" });
      await new Promise<void>((r) => (release = r));
      on({ type: "card", card: HelperCard.parse(fixtures.answer) });
      on({ type: "run_finished", mode: "ai", outcome: "answered", fallback: null, reason: null });
    });
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet({ ask: "Yarın 10'da boş salon var mı?" }));
    expect(await screen.findByTestId("helper-thinking")).toHaveTextContent("Düşünüyor…");
    expect(screen.getByTestId("helper-log")).toHaveAttribute("aria-busy", "true");
    expect(stream).toHaveBeenCalledWith("Yarın 10'da boş salon var mı?", "tr", expect.any(Function));
    await act(async () => release());
    expect(await screen.findByTestId("helper-card-answer")).toHaveTextContent("A 204 yarın 10:00–10:50 boş.");
    expect(screen.getByTestId("helper-feedback")).toBeInTheDocument();
    expect(screen.queryByTestId("helper-thinking")).toBeNull();
  });
});

describe("helper root", () => {
  it("⌘J / Ctrl+J opens the sheet; on a run page it is the run chat's", async () => {
    media(true);
    renderHelper(<HelperRoot />);
    await waitFor(() => expect(helperApi.status).toHaveBeenCalled());
    fireEvent.keyDown(window, { key: "j", ctrlKey: true });
    expect(useHelperStore.getState().open).toBe(true);
    fireEvent.keyDown(window, { key: "j", ctrlKey: true });
    expect(useHelperStore.getState().open).toBe(false);
    window.history.pushState({}, "", "/runs/5");
    fireEvent.keyDown(window, { key: "j", metaKey: true });
    expect(useHelperStore.getState().open).toBe(false);
    window.history.pushState({}, "", "/");
  });

  it("renders nothing when an administrator switched the helper off", async () => {
    media(true);
    vi.spyOn(helperApi, "status").mockResolvedValue(status({ enabled: false, mode: "index", reason: "disabled" }));
    renderHelper(<HelperRoot />);
    await waitFor(() => expect(helperApi.status).toHaveBeenCalled());
    await act(async () => undefined);
    fireEvent.keyDown(window, { key: "j", ctrlKey: true });
    expect(useHelperStore.getState().open).toBe(false);
  });
});
