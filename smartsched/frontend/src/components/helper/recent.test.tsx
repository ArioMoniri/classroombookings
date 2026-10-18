/**
 * HX-15 (helper.md §2.3 group 1, §17.1 #6; API.md HB-D §3): "Son işlemler" — the person's own confirmed helper actions
 * from `GET /helper/actions/recent?limit=5`, in the empty palette (at most 3, before the starters) and in the empty
 * sheet. Each row: the server's label, when, the status; "Geri al" posts the row's `undo_token` to
 * `POST /helper/actions/undo` (a 409 shows the server's text); the group is hidden while the list is empty.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { Command, CommandList } from "@/components/ui/command";
import { HttpError } from "@/lib/api/client";
import { helperApi, helperKeys, type HelperStatus, type RecentAction } from "@/lib/api/helper";
import fixtures from "./__fixtures__/cards.json";
import { HelperPaletteBottom, HelperPaletteTop } from "./palette-groups";
import { RecentActions, whenLabel } from "./recent";
import { HelperCard } from "./schema.gen";
import { renderHelper, resetHelperStore } from "./test-helpers";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/reserve" }));
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: () => true, perms: [] }) }));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));
vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const iso = (msAgo: number) => new Date(Date.now() - msAgo).toISOString().slice(0, 19); // naive UTC, as the server sends
const row = (over: Partial<RecentAction>): RecentAction => ({
  id: 41,
  action: "remember_note",
  kind: "note",
  entity_id: 7,
  feature_id: "profile.helper_memory",
  label: { tr: "Not kaydedildi: Pazartesi sabahları B blok", en: "Note saved: Monday mornings block B" },
  at: iso(5 * 60_000),
  status: "done",
  undoable: true,
  undo_token: "tok-41",
  undo_expires_at: iso(-60 * 60_000),
  ...over,
});

let rows: RecentAction[] = [];
const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "local", provider_label: null, fallback_active: false, message: null, ...over });
const undoneCard = HelperCard.parse({ ...fixtures.result, action: "remember_note", message: { tr: "Geri alındı; not silindi.", en: "Undone; the note was deleted." }, undo_token: null, undo_expires_at: null, entity: null, follow_ups: [] });

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  push.mockReset();
  vi.restoreAllMocks();
  vi.mocked(toast).mockClear();
  rows = [
    row({}),
    row({ id: 40, action: "create_booking", kind: "booking", entity_id: 913, feature_id: "my_bookings", label: { tr: "Rezervasyon yapıldı: A 102 · 19.02.2026 08:40", en: "Booked: A 102 · 19.02.2026 08:40" }, at: iso(26 * 3600_000), undo_token: "tok-40" }),
    row({ id: 39, action: "cancel_my_booking", kind: "booking", label: { tr: "Rezervasyon iptal edildi: B 201", en: "Booking cancelled: B 201" }, status: "undone", undoable: false, undo_token: null, undo_expires_at: null }),
    row({ id: 38, action: "decide_approval", kind: "approval_request", label: { tr: "Talep onaylandı: C 101", en: "Request approved: C 101" }, undoable: false, undo_token: null, undo_expires_at: null }),
  ];
  vi.spyOn(helperApi, "recent").mockImplementation(async () => rows);
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
});

describe("whenLabel", () => {
  it("reads the server's naive time as UTC and says it relative to now", () => {
    const now = Date.parse("2026-02-16T10:00:00Z");
    expect(whenLabel("2026-02-16T09:59:40", "tr", now)).toBe("az önce");
    expect(whenLabel("2026-02-16T09:55:00", "tr", now)).toBe("5 dakika önce");
    expect(whenLabel("2026-02-16T07:00:00", "tr", now)).toBe("3 saat önce");
    expect(whenLabel("2026-02-15T09:00:00", "tr", now)).toBe("dün");
    expect(whenLabel("2026-02-16T09:55:00Z", "en", now)).toBe("5 minutes ago");
    expect(whenLabel("not a date", "tr", now)).toBe("");
  });
});

describe("Son işlemler in the sheet", () => {
  it("lists label, when and status; undoable rows have Geri al", async () => {
    renderHelper(<RecentActions />);
    const group = await screen.findByTestId("helper-recent");
    expect(within(group).getByRole("heading", { name: "Son işlemler" })).toBeInTheDocument();
    expect(helperApi.recent).toHaveBeenCalledWith(5);
    const first = screen.getByTestId("helper-recent-41");
    expect(first).toHaveTextContent("Not kaydedildi: Pazartesi sabahları B blok");
    expect(first).toHaveTextContent("5 dakika önce · Yapıldı");
    expect(screen.getByTestId("helper-recent-40")).toHaveTextContent("dün · Yapıldı");
    expect(screen.getByTestId("helper-recent-39")).toHaveTextContent("Geri alındı");
    expect(screen.queryByTestId("helper-recent-undo-39")).toBeNull();
    expect(screen.queryByTestId("helper-recent-undo-38")).toBeNull();
    expect(screen.getByTestId("helper-recent-undo-41")).toHaveAccessibleName("Geri al: Not kaydedildi: Pazartesi sabahları B blok");
  });

  it("Geri al posts the row's undo token, refetches and keeps the focus on the row", async () => {
    const undo = vi.spyOn(helperApi, "undo").mockImplementation(async () => {
      rows = rows.map((r) => (r.id === 41 ? { ...r, status: "undone", undoable: false, undo_token: null } : r));
      return undoneCard;
    });
    const { qc } = renderHelper(<RecentActions />);
    const inval = vi.spyOn(qc, "invalidateQueries");
    fireEvent.click(await screen.findByTestId("helper-recent-undo-41"));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("tok-41"));
    await waitFor(() => expect(screen.getByTestId("helper-recent-41")).toHaveTextContent("Geri alındı"));
    expect(screen.queryByTestId("helper-recent-undo-41")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("helper-recent-status-41")));
    expect(toast).toHaveBeenCalledWith("Geri alındı; not silindi.");
    // a note's undo also refreshes Profil › Yardımcı
    expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.recent });
    expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.notes });
    expect(inval).toHaveBeenCalledWith({ queryKey: helperKeys.memory });
  });

  it("a 409 shows the server's text under the row", async () => {
    vi.spyOn(helperApi, "undo").mockRejectedValue(new HttpError(409, "too_old", { code: "too_old", message_tr: "Bu işlem artık geri alınamaz: ders başladı.", message_en: "This can no longer be undone: the class has started." }));
    renderHelper(<RecentActions />);
    fireEvent.click(await screen.findByTestId("helper-recent-undo-40"));
    expect(await screen.findByTestId("helper-recent-error-40")).toHaveTextContent("Bu işlem artık geri alınamaz: ders başladı.");
    expect(document.activeElement).not.toBe(document.body);
  });

  it("is hidden while the list is empty", async () => {
    rows = [];
    renderHelper(<RecentActions />);
    await waitFor(() => expect(helperApi.recent).toHaveBeenCalled());
    expect(screen.queryByTestId("helper-recent")).toBeNull();
  });

  it("English", async () => {
    renderHelper(<RecentActions />, { locale: "en" });
    expect(await screen.findByTestId("helper-recent-41")).toHaveTextContent("Note saved: Monday mornings block B");
    expect(screen.getByRole("heading", { name: "Recent actions" })).toBeInTheDocument();
    expect(screen.getByTestId("helper-recent-39")).toHaveTextContent("Undone");
  });
});

function renderPalette(query: string) {
  return renderHelper(
    <Command shouldFilter={false} label="palette">
      <CommandList>
        <HelperPaletteTop query={query} />
        <div data-testid="data-groups" />
        <HelperPaletteBottom query={query} />
      </CommandList>
    </Command>,
  );
}

describe("Son işlemler in the empty palette", () => {
  it("shows at most 3 rows first, before the starters; a row opens its page", async () => {
    renderPalette("");
    const group = await screen.findByTestId("palette-group-recent");
    expect(group).toHaveTextContent("Son işlemler");
    expect(within(group).getAllByTestId(/^palette-recent-\d+$/)).toHaveLength(3);
    await screen.findByTestId("palette-group-starters");
    const order = [...document.querySelectorAll("[data-testid^='palette-group-']")].map((el) => el.getAttribute("data-testid"));
    expect(order).toEqual(["palette-group-recent", "palette-group-starters"]);
    expect(screen.getByTestId("palette-recent-40")).toHaveTextContent("Rezervasyon yapıldı: A 102 · 19.02.2026 08:40");
    expect(screen.getByTestId("palette-recent-40")).toHaveTextContent("dün · Yapıldı");
    fireEvent.click(screen.getByTestId("palette-recent-40"));
    expect(push).toHaveBeenCalledWith("/my-bookings");
  });

  it("Geri al in a palette row posts the token without opening the page", async () => {
    const undo = vi.spyOn(helperApi, "undo").mockResolvedValue(undoneCard);
    renderPalette("");
    const btn = await screen.findByTestId("palette-recent-undo-41");
    expect(btn).toHaveAccessibleName("Geri al: Not kaydedildi: Pazartesi sabahları B blok");
    fireEvent.click(btn);
    await waitFor(() => expect(undo).toHaveBeenCalledWith("tok-41"));
    expect(push).not.toHaveBeenCalled();
  });

  it("a 409 in the palette shows the server's text", async () => {
    vi.spyOn(helperApi, "undo").mockRejectedValue(new HttpError(409, "already_undone", { code: "already_undone", message_tr: "Bu işlem zaten geri alınmış.", message_en: "Already undone." }));
    renderPalette("");
    fireEvent.click(await screen.findByTestId("palette-recent-undo-41"));
    expect(await screen.findByTestId("palette-recent-error-41")).toHaveTextContent("Bu işlem zaten geri alınmış.");
  });

  it("is not shown with a query, nor while the list is empty", async () => {
    vi.spyOn(helperApi, "search").mockResolvedValue({ q: "tatil", question: false, pages: [], where: [], data: {}, skipped: [], timing_ms: 1 });
    const { unmount } = renderPalette("tatil");
    await waitFor(() => expect(helperApi.search).toHaveBeenCalled());
    expect(screen.queryByTestId("palette-group-recent")).toBeNull();
    unmount();
    rows = [];
    renderPalette("");
    await screen.findByTestId("palette-group-starters");
    expect(screen.queryByTestId("palette-group-recent")).toBeNull();
  });
});
