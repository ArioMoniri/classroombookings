/**
 * Round-3 R3-M-01 follow-up (lane S → lane D): the recreate sheet's method follows the staged edits. A sheet mounted
 * while nothing was staged must still send `mode: "repair"` ("En az değişiklik") once an edit is staged; with nothing
 * staged it runs "baştan" and says so.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { RecreateSheet } from "./recreate-sheet";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => vi.unstubAllGlobals());

function setup() {
  const bodies: Record<string, unknown>[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (/\/moderation\/resolve$/.test(url)) { bodies.push(JSON.parse(String(init?.body))); return json({ run_id: 21, status: "QUEUED", base_run_id: 8 }, 202); }
    return json({ term_id: 2, published_run_id: 8, total: 0, counts: {}, changed_request_ids: [], items: [] });
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (staged: number[]) => (
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <RecreateSheet open onOpenChange={() => undefined} termId={2} baseRunId={8} staged={staged} />
      </I18nProvider>
    </QueryClientProvider>
  );
  return { bodies, ui };
}

describe("recreate sheet method (R3-M-01 follow-up)", () => {
  it("sends repair once an edit is staged after the sheet mounted with nothing staged", async () => {
    const { bodies, ui } = setup();
    const { rerender } = render(ui([]));
    expect(await screen.findByTestId("recreate-repair-unavailable")).toBeInTheDocument();
    rerender(ui([1602]));
    await waitFor(() => expect(screen.queryByTestId("recreate-repair-unavailable")).toBeNull());
    await userEvent.click(screen.getByTestId("recreate-start"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ mode: "repair", changed_request_ids: [1602], base_run_id: 8 });
  }, 20_000);
  it("runs from scratch with nothing staged, and keeps an explicit 'Baştan çöz' choice", async () => {
    const { bodies, ui } = setup();
    const { rerender } = render(ui([]));
    await userEvent.click(await screen.findByTestId("recreate-start"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ mode: "full" });
    rerender(ui([1602]));
    await userEvent.click(screen.getByRole("radio", { name: /Baştan çöz/ }));
    await userEvent.click(screen.getByTestId("recreate-start"));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ mode: "full" });
  }, 20_000);
});
