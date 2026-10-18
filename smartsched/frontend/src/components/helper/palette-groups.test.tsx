/**
 * HX-02 (helper.md §2.3): "Ara veya sor" groups in the palette — order, role filter, question detection,
 * Shift+Enter = Göster, the ask row hidden in index mode, shortcuts only for permitted actions, starters when empty.
 */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Command, CommandList } from "@/components/ui/command";
import { helperApi, type HelperSearch, type HelperStatus } from "@/lib/api/helper";
import fixtures from "./__fixtures__/cards.json";
import { useHelperStore } from "./helper-store";
import { HelperPaletteBottom, HelperPaletteTop } from "./palette-groups";
import { renderHelper, resetHelperStore } from "./test-helpers";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/admin" }));
let perms: string[] = [];
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: (p: string | readonly string[] | undefined) => !p || (Array.isArray(p) ? p : [p]).some((x) => perms.includes(x as string)), perms }) }));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));

const nav = (feature_id: string, kind: "page" | "control", title: string, path: string[]) => ({ ...fixtures.nav, id: `${feature_id.replace(/[^a-z]/g, "").slice(0, 6)}aaaaaa`.replace(/[^a-f0-9]/g, "a").slice(0, 12), feature_id, kind, anchor: null, title: { tr: title, en: title }, path: { tr: path, en: path }, steps: { tr: [], en: [] } });

const periods: HelperSearch = {
  q: "periods",
  question: false,
  pages: [nav("admin.schedules", "page", "Ders saatleri", ["Yönetim", "Dönem ve saatler", "Ders saatleri"])],
  where: [nav("admin.users.invite", "control", "Davet et", ["Yönetim", "Kullanıcılar", "Davet et"])],
  data: {},
  skipped: [],
  timing_ms: 3,
} as unknown as HelperSearch;

const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "local", provider_label: null, fallback_active: false, message: null, ...over });

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

const order = () => [...document.querySelectorAll("[data-testid^='palette-group-'], [data-testid='data-groups']")].map((el) => el.getAttribute("data-testid"));

beforeEach(() => {
  // jsdom has no scrolling (cmdk scrolls the selected row into view)
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  push.mockReset();
  perms = ["setup.schedules", "setup.users", "setup.settings"];
  vi.restoreAllMocks();
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([{ name: "create_booking", kind: "write", risk: "R1", card: "confirm", summary: { tr: "Rezerve et", en: "Book a room" } }]);
  vi.spyOn(helperApi, "search").mockResolvedValue(periods);
});

describe("palette groups", () => {
  it("orders Sayfalar ve ayarlar → Nerede? → data → Kısayollar → Yardımcıya sor (no AI call to search)", async () => {
    renderPalette("periods");
    expect(await screen.findByTestId("palette-page-admin.schedules")).toHaveTextContent("Ders saatleri");
    expect(screen.getByTestId("palette-page-admin.schedules")).toHaveTextContent("Yönetim › Dönem ve saatler › Ders saatleri");
    await screen.findByTestId("palette-ask");
    expect(order()).toEqual(["palette-group-pages", "palette-group-where", "data-groups", "palette-group-ask"]);
    expect(helperApi.search).toHaveBeenCalledWith("periods", undefined, expect.anything());
  });

  it("puts the ask row first when the query reads as a question", async () => {
    vi.spyOn(helperApi, "search").mockResolvedValue({ ...periods, q: "tatil nasıl eklenir?", question: true });
    renderPalette("tatil nasıl eklenir?");
    await screen.findByTestId("palette-ask");
    expect(order()[0]).toBe("palette-group-ask");
    expect(screen.getByTestId("palette-ask")).toHaveAccessibleName("Yardımcıya sor: tatil nasıl eklenir?, yapay zekâ, Yerel model");
  });

  it("hides the ask row in index mode; Nerede? stays", async () => {
    vi.spyOn(helperApi, "status").mockResolvedValue(status({ mode: "index", reason: "not_routed" }));
    renderPalette("periods");
    expect(await screen.findByTestId("palette-where-admin.users.invite")).toBeInTheDocument();
    await waitFor(() => expect(helperApi.status).toHaveBeenCalled());
    expect(screen.queryByTestId("palette-ask")).toBeNull();
  });

  it("never lists a page the person cannot open (double filter)", async () => {
    perms = ["book_single.create"];
    renderPalette("kullanıcı davet");
    await waitFor(() => expect(helperApi.search).toHaveBeenCalled());
    await screen.findByTestId("palette-ask");
    expect(screen.queryByTestId("palette-where-admin.users.invite")).toBeNull();
    expect(screen.queryByTestId("palette-page-admin.schedules")).toBeNull();
  });

  it("Enter on a Nerede? row rings the control; Enter on a page opens it; Shift+Enter on a page = Göster", async () => {
    const withAnchor = { ...periods, pages: [{ ...periods.pages[0]!, anchor: "admin-periods" }], where: [{ ...periods.where[0]!, anchor: "admin-users-invite" }] } as HelperSearch;
    vi.spyOn(helperApi, "search").mockResolvedValue(withAnchor);
    renderPalette("periods");
    fireEvent.click(await screen.findByTestId("palette-where-admin.users.invite"));
    expect(useHelperStore.getState().showMe?.featureId).toBe("admin.users.invite");
    useHelperStore.getState().endShowMe();
    fireEvent.click(screen.getByTestId("palette-page-admin.schedules"));
    expect(push).toHaveBeenCalledWith("/admin/schedules");
    // the first row (the page) is selected: Shift+Enter shows it instead
    const input = document.querySelector<HTMLElement>("[cmdk-root]")!;
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(useHelperStore.getState().showMe?.featureId).toBe("admin.schedules");
  });

  it("offers a shortcut only for an action the person may run", async () => {
    vi.spyOn(helperApi, "search").mockResolvedValue({ ...periods, pages: [], where: [], q: "yarın 10 a 204" });
    const { unmount } = renderPalette("yarın 10 a 204");
    expect(await screen.findByTestId("palette-shortcut-create_booking")).toHaveTextContent("Salon ayır: A 204 · yarın · 10:00");
    fireEvent.click(screen.getByTestId("palette-shortcut-create_booking"));
    await waitFor(() => expect(useHelperStore.getState().pendingAction).toEqual({ action: "create_booking", args: { room: "A 204", date: expect.any(String) }, hints: { time: "10:00" } }));
    unmount();
    resetHelperStore();
    vi.spyOn(helperApi, "actions").mockResolvedValue([]);
    renderPalette("yarın 10 a 204");
    await screen.findByTestId("palette-ask");
    expect(screen.queryByTestId("palette-shortcut-create_booking")).toBeNull();
  });

  it("shows the role starters with an empty query", async () => {
    renderPalette("");
    expect(await screen.findByTestId("palette-group-starters")).toHaveTextContent("Tatil nerede eklenir?");
  });
});
