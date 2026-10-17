/**
 * Round-3 R3-M-06 (loop-r3-laneD): focus never falls to <body>
 *  1. after "Yayınla" in the re-solve preview: the publish button disappears with the dialog (the run is active), so
 *     focus goes to the "✓ Yayında" status;
 *  2. after a section / request priority is saved in the matching inspector: the sheet closes and focus returns to
 *     the class row it was opened from (`data-row-id`), also when the row element was re-rendered meanwhile.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { MatchingInspector } from "./matching-inspector";
import { RecreatePreview } from "./recreate-preview";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/moderation", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/permissions", () => ({ usePermissions: () => ({ loading: false, perms: ["planning.view", "planning.edit"], can: () => true, canAll: () => true }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
afterEach(() => vi.unstubAllGlobals());

const diff = (active: boolean) => ({
  run_id: 15, base_run_id: 8, compare_to_run_id: 8, compared_to: "published", chain: [8], status: "FEASIBLE_PARTIAL", ready: true, is_active: active,
  counts: { moved: 0, unchanged: 3, newly_placed: 0, unplaceable: 0, newly_unplaced: 0, affected_people: 0 },
});

describe("focus after the preview publish (R3-M-06)", () => {
  it("lands on the '✓ Yayında' status, never on <body>", async () => {
    let active = false;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (/\/runs\/15\/activate$/.test(url) && init?.method === "POST") { active = true; return json({ id: 15, is_active: true }); }
      if (/\/moderation\/runs\/15\/diff/.test(url)) return json(diff(active));
      if (/\/constraints/.test(url)) return json([]);
      if (/\/runs\/15(\?|$)/.test(url)) return json({ detail: "not here" }, 404);
      return json({ items: [], total: 0 });
    }));
    wrap(<RecreatePreview runId={15} />);
    await userEvent.click(await screen.findByTestId("preview-publish"));
    await userEvent.click(await screen.findByTestId("publish-confirm"));
    await waitFor(() => expect(screen.getByTestId("preview-state")).toHaveTextContent("✓ Yayında"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("preview-state")));
    expect(document.activeElement).not.toBe(document.body);
  }, 20_000);
});

const matching = {
  request_id: 1602, section_id: 374, term_id: 2, course_code: "PSY 277", course_name: "Statistical Applications", section: "1", label: "PSY 277", program: null, faculty: null, enrolment: 42,
  instructors: [], requested: { day: 1, days: [], start_period: 3, end_period: 5, time: "10:10–12:30", weeks: [], room_text: "Derslik", rooms: [], building: null, tags: [], capacity: null, status: "PARSED" },
  definitive: { text: "A 308", room_ids: [1], rooms: ["A 308"] }, assigned: null, satisfied: { room: null, building: null, tags: null, day: true, period: true },
  verdict: "satisfied", verdict_text: { tr: "Karşılandı", en: "Satisfied" }, reason: null, priority: { value: 0, source: "default" }, source: "run", provenance: { row: 92, source_key: null }, teacher_preferences: [],
};

function Harness() {
  const [open, setOpen] = useState<number | null>(null);
  const [gen, setGen] = useState(0); // a refetch re-renders the row as a new element
  return (
    <>
      <div key={gen} role="row" tabIndex={0} data-row-id="1602" data-testid="the-row" onKeyDown={(e) => e.key === "p" && setOpen(1602)}>PSY 277</div>
      <MatchingInspector termId={2} requestId={open} canEdit onClose={() => { setOpen(null); setGen((g) => g + 1); }} focusPriority />
    </>
  );
}

describe("focus after a section priority save in the inspector (R3-M-06)", () => {
  it("returns to the class row, never to <body>", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (/\/moderation\/sections\/374\/priority/.test(url) && init?.method === "PUT") return json({ priority: 1, previous: null });
      if (/\/moderation\/matchings\/1602/.test(url)) return json(matching);
      return json({ items: [], total: 0, term_id: 2 });
    }));
    wrap(<Harness />);
    screen.getByTestId("the-row").focus();
    await userEvent.keyboard("p");
    const save = await screen.findByTestId("priority-save");
    await userEvent.click((await screen.findAllByText("Tüm şube"))[0]!);
    await userEvent.click(save);
    await waitFor(() => expect(screen.queryByTestId("matching-inspector")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("the-row")));
  });
});
