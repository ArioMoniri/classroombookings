/** WG-04 sheet: audience cards (max 5), focus to the title, Esc = Sonra, focus return, phone pager, admin overrides. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildSheet } from "./model";
import { DESKTOP_MEDIA, makeState, mockMedia, PHONE_MEDIA, renderWelcome } from "./test-helpers";
import { WelcomeSheet, type SheetAction } from "./welcome-sheet";

// the first test pays the cold transform of the shell modules on a shared, loaded host
vi.setConfig({ testTimeout: 20_000 });

vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return { ...real, request: async (path: string) => (path === "/auth/me" ? { id: 7, full_name: "Ayşe Tekin", role: "TEACHER", permissions: [] } : null) };
});

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

function Harness({ state = makeState(), onAction, startOpen = true }: { state?: ReturnType<typeof makeState>; onAction: (a: SheetAction) => void; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  const model = buildSheet(state)!;
  return (
    <>
      <main>
        <h1>Hızlı rezervasyon</h1>
        <button type="button" data-testid="opener" onClick={() => setOpen(true)}>
          aç
        </button>
      </main>
      <WelcomeSheet
        open={open}
        model={model}
        state={state}
        tourEnabled
        checklistEnabled
        onAction={(a) => {
          onAction(a);
          setOpen(false);
        }}
      />
    </>
  );
}

describe("WelcomeSheet (desktop)", () => {
  beforeEach(() => mockMedia(DESKTOP_MEDIA));

  it("greets by name with the audience badge, four cards, focus on the title", async () => {
    renderWelcome(<Harness onAction={() => undefined} />, { state: makeState() });
    const title = await screen.findByTestId("welcome-sheet-title");
    expect(title).toHaveTextContent("SmartSched'e hoş geldiniz, Ayşe");
    expect(screen.getByTestId("welcome-badge")).toHaveTextContent("Öğretim elemanı · Psikoloji");
    expect(screen.getAllByTestId(/^welcome-card-/)).toHaveLength(4);
    await waitFor(() => expect(title).toHaveFocus());
    expect(screen.getByTestId("welcome-sheet")).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("welcome-start-tour")).toHaveTextContent("Kısa turu başlat (1 dk)");
  });

  it("Esc counts as 'Sonra' and focus returns to the element that had it", async () => {
    const onAction = vi.fn();
    renderWelcome(<Harness onAction={onAction} startOpen={false} />, { state: makeState() });
    const opener = screen.getByTestId("opener");
    opener.focus();
    await userEvent.click(opener);
    await waitFor(() => expect(screen.getByTestId("welcome-sheet-title")).toHaveFocus());
    await userEvent.keyboard("{Escape}");
    expect(onAction).toHaveBeenCalledWith({ type: "later" });
    await waitFor(() => expect(screen.queryByTestId("welcome-sheet")).toBeNull());
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("the buttons report their action; a card opens its part", async () => {
    const onAction = vi.fn();
    renderWelcome(<Harness onAction={onAction} />, { state: makeState() });
    fireEvent.click(await screen.findByTestId("welcome-card-my_bookings"));
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ type: "card", card: expect.objectContaining({ key: "my_bookings", href: "/my-bookings" }) }));
  });

  it("'Ayrıca' card for a secondary audience and the 'Güncellendi' badge", async () => {
    const state = makeState({ audiences: ["staff", "approver"], primary: "staff", sheet: { cards: [], updated: true } });
    renderWelcome(<Harness state={state} onAction={() => undefined} />, { state });
    expect(await screen.findByTestId("welcome-card-approvals_inbox")).toHaveTextContent("Ayrıca");
    expect(screen.getAllByTestId(/^welcome-card-/)).toHaveLength(5);
    expect(screen.getByTestId("welcome-updated")).toHaveTextContent("Güncellendi");
  });

  it("an admin override replaces the product text and fills {ad}", async () => {
    const state = makeState({ sheet: { cards: [], updated: false, overrides: { title: "Merhaba {ad}, hoş geldiniz" } } });
    renderWelcome(<Harness state={state} onAction={() => undefined} />, { state });
    expect(await screen.findByTestId("welcome-sheet-title")).toHaveTextContent("Merhaba Ayşe, hoş geldiniz");
  });

  it("English copy", async () => {
    renderWelcome(<Harness onAction={() => undefined} />, { state: makeState(), locale: "en" });
    expect(await screen.findByTestId("welcome-sheet-title")).toHaveTextContent("Welcome to SmartSched, Ayşe");
    expect(screen.getByTestId("welcome-later")).toHaveTextContent("Later");
  });
});

describe("WelcomeSheet (phone pager)", () => {
  beforeEach(() => mockMedia(PHONE_MEDIA));

  it("one card per page, '1 / 4', İleri → Başlayalım on the last page opens that card", async () => {
    const onAction = vi.fn();
    renderWelcome(<Harness onAction={onAction} />, { state: makeState() });
    expect(await screen.findByTestId("welcome-sheet")).toHaveAttribute("data-variant", "pager");
    expect(screen.getByTestId("welcome-page")).toHaveTextContent("1 / 4");
    expect(screen.getByRole("group", { name: "1 / 4" })).toHaveAttribute("aria-roledescription", "slayt");
    expect(screen.getByTestId("welcome-dots")).toHaveAttribute("aria-hidden");
    const next = screen.getByTestId("welcome-next");
    for (let i = 0; i < 3; i++) await act(async () => fireEvent.click(next));
    expect(screen.getByTestId("welcome-page")).toHaveTextContent("4 / 4");
    expect(next).toHaveTextContent("Başlayalım");
    fireEvent.click(next);
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ type: "card", card: expect.objectContaining({ key: "calendar" }) }));
  });
});
