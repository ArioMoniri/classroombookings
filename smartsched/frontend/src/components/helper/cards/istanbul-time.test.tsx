/**
 * FIX-D / HB18-F01 (docs/testing/round4/2026-10-18-hb18.md): in Europe/Istanbul a confirm card with a naive UTC
 * `expires_at` (the server's format before the fix) was born "Bu öneri eskidi.", a trusted click never confirmed, and
 * "Geri al" vanished up to 3 h early. Runs under TZ=Europe/Istanbul.
 */
process.env.TZ = "Europe/Istanbul";

import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useMemo } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi } from "@/lib/api/helper";
import { useHelperStore, type CardEntry } from "../helper-store";
import type { HelperCard } from "../schema.gen";
import { card, makeHost, renderHelper, resetHelperStore } from "../test-helpers";
import { activation, useHelperRunner } from "../use-helper-runner";
import { CardHostContext } from "./context";
import { EntryView } from "./render";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reserve" }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

/** "2026-10-18T13:11:22" — naive UTC, as the server sent it before the fix. */
const naiveUtc = (msFromNow: number) => new Date(Date.now() + msFromNow).toISOString().slice(0, 19);

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

beforeEach(() => resetHelperStore());
afterEach(() => vi.restoreAllMocks());

describe("helper times in Europe/Istanbul", () => {
  it("the test really runs at UTC+3", () => {
    expect(new Date().getTimezoneOffset()).toBe(-180);
  });

  it("a confirm card with a naive UTC expiry 9 minutes ahead is live, not 'eskidi'", () => {
    const c = { ...card("confirm"), expires_at: naiveUtc(9 * 60_000) } as HelperCard;
    const e: CardEntry = { kind: "card", key: "k1", card: c, phase: "pending" };
    renderHelper(<EntryView entry={e} />, { host: makeHost() });
    expect(screen.getByTestId("helper-card-confirm")).toBeInTheDocument();
    expect(screen.queryByTestId("helper-card-expired")).toBeNull();
  });

  it("a trusted click on that card confirms (the runner reads the expiry as UTC too)", async () => {
    vi.spyOn(activation, "trusted").mockReturnValue(true);
    const confirm = vi.spyOn(helperApi, "confirm").mockResolvedValue(card("result"));
    renderHelper(<Harness />);
    act(() => {
      useHelperStore.getState().pushCard({ ...card("confirm"), expires_at: naiveUtc(9 * 60_000) } as HelperCard);
    });
    fireEvent.click(await screen.findByTestId("helper-card-confirm"));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
  });

  it("a result card keeps 'Geri al' while a naive UTC undo window is still open", () => {
    const c = { ...card("result"), undo_expires_at: naiveUtc(60 * 60_000) } as HelperCard;
    renderHelper(<EntryView entry={{ kind: "card", key: "k2", card: c, phase: "done" }} />, { host: makeHost() });
    expect(screen.getByTestId("helper-card-undo")).toBeInTheDocument();
  });

  it("an expiry that really passed still reads 'Bu öneri eskidi.'", () => {
    const c = { ...card("confirm"), expires_at: new Date(Date.now() - 60_000).toISOString() } as HelperCard;
    renderHelper(<EntryView entry={{ kind: "card", key: "k3", card: c, phase: "pending" }} />, { host: makeHost() });
    expect(screen.getByTestId("helper-card-expired")).toHaveTextContent("Bu öneri eskidi.");
  });
});
