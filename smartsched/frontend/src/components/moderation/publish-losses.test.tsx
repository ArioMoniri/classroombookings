/**
 * Round-1 R1-S-04: the re-solve publish confirm says which classes lose their room (with the cause) and needs an
 * explicit tick before it publishes.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiffOut } from "@/lib/api/moderation";
import { I18nProvider } from "@/lib/i18n/provider";
import { PublishDialog } from "./recreate-preview";

const place = { day: 1, start_period: 3, end_period: 5, time: "10:10–12:30", when: { tr: "Pazartesi 10:10–12:30", en: "Monday 10:10–12:30" }, room_ids: [21], rooms: ["B 201"], weeks: [3] };
const diff = DiffOut.parse({
  run_id: 15,
  base_run_id: 10,
  status: "FEASIBLE_PARTIAL",
  ready: true,
  counts: { moved: 1, newly_placed: 1, unplaceable: 2, newly_unplaced: 1, affected_people: 2 },
  unplaceable: [
    { request_id: 1, label: "ACU 141", was_placed: true, from: place, base_conflict: true, reason: { code: "base_conflict", text: { tr: "Yayımdaki hücresi artık kesin bir kuralı bozuyor", en: "Its published cell now breaks a hard rule" } } },
    { request_id: 2, label: "ING 302", was_placed: false, reason: { code: "unplaced", text: { tr: "Yerleşmedi", en: "Not placed" } } },
  ],
});

afterEach(() => vi.unstubAllGlobals());

describe("re-solve publish confirm (R1-S-04)", () => {
  it("lists every class that loses its room and needs the tick", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [], total: 0 }), { status: 200, headers: { "Content-Type": "application/json" } })));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <PublishDialog open onOpenChange={() => undefined} diff={diff} termId={2} onPublished={() => undefined} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const box = await screen.findByTestId("publish-losses");
    expect(box).toHaveTextContent("1 ders dersliğini kaybediyor");
    expect(box).toHaveTextContent("ACU 141");
    expect(box).toHaveTextContent("kesin bir kuralı bozuyor");
    expect(box).not.toHaveTextContent("ING 302"); // never placed: not a loss
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("publish-losses-ack"));
    expect(screen.getByTestId("publish-confirm")).toBeEnabled();
  });
});
