/**
 * HX-16 (helper.md §2.4 footer, §17.1 #7; API.md HB-D §2): the "Bu sayfa: …" chip. The page title comes from the
 * feature index (only a page the person may open); one tap removes it. While it is on, `POST /helper/turn` carries
 * `context: {route: pathname + hash, entity_kind?, entity_id?}` (the same zod rules as the server: kind room | booking |
 * approval_request, id ≥ 1, route ≤ 200); once removed, or without a known page, no context is sent.
 */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { helperApi, TurnContext, type HelperStatus } from "@/lib/api/helper";
import { HelperSheet } from "./helper-sheet";
import { useHelperStore } from "./helper-store";
import { pageContextFor, toTurnContext } from "./page-context";
import type { TurnEvent } from "./stream";
import { renderHelper, resetHelperStore } from "./test-helpers";

let pathname = "/reserve";
let perms: string[] = ["book_single.create"];
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => pathname, useSearchParams: () => new URLSearchParams() }));
const can = (p: string | readonly string[] | undefined) => !p || (Array.isArray(p) ? p : [p]).length === 0 || (Array.isArray(p) ? p : [p]).some((x) => perms.includes(x as string));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ can, perms }),
  useMeFull: () => ({ data: { id: 1, permissions: [] }, isLoading: false }),
}));
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: undefined }) }));
const stream = vi.fn<(text: string, lang: string, on: (e: TurnEvent) => void, opts?: { context?: TurnContext }) => Promise<void>>();
vi.mock("./stream", async (orig) => ({ ...(await orig<typeof import("./stream")>()), streamTurn: (text: string, lang: string, on: (e: TurnEvent) => void, opts?: { context?: TurnContext }) => stream(text, lang, on, opts) }));

window.matchMedia = ((q: string) => ({ matches: q.includes("min-width: 1024px"), media: q, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;

const status = (over: Partial<HelperStatus> = {}): HelperStatus => ({ mode: "ai", enabled: true, reason: null, provider_kind: "local", provider_label: null, fallback_active: false, message: null, ...over });

beforeEach(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  resetHelperStore();
  pathname = "/reserve";
  perms = ["book_single.create"];
  window.history.replaceState({}, "", "/reserve");
  stream.mockReset();
  stream.mockImplementation(async (_t, _l, on) => {
    on({ type: "run_started", turnId: "abcdef0123456789" });
    on({ type: "run_finished", mode: "ai", outcome: "answered", fallback: null, reason: null });
  });
  vi.restoreAllMocks();
  vi.spyOn(helperApi, "status").mockResolvedValue(status());
  vi.spyOn(helperApi, "actions").mockResolvedValue([]);
  vi.spyOn(helperApi, "recent").mockResolvedValue([]);
  vi.spyOn(helperApi, "memory").mockResolvedValue({ institution_enabled: true, enabled: true, notes: 0, max_notes: 20, max_chars: 200, retention_days: 180, history_days: 30 });
});

describe("pageContextFor", () => {
  const all = () => true;
  it("names the page from the feature index and sends pathname + hash", () => {
    expect(pageContextFor({ pathname: "/reserve", hash: "", search: "" }, all)).toMatchObject({ route: "/reserve", featureId: "reserve", title: { tr: "Hızlı rezervasyon" } });
    expect(pageContextFor({ pathname: "/profile", hash: "#ai-usage", search: "?x=1" }, all)).toMatchObject({ route: "/profile#ai-usage", featureId: "profile.ai_usage" });
    // a page among its tabs (same route) is the page itself
    expect(pageContextFor({ pathname: "/profile", hash: "", search: "" }, all)).toMatchObject({ route: "/profile", featureId: "profile" });
    expect(pageContextFor({ pathname: "/admin/users/", hash: "", search: "" }, all)).toMatchObject({ route: "/admin/users/", featureId: "admin.users" });
  });

  it("a detail view adds its entity; the title is the parent page's", () => {
    expect(pageContextFor({ pathname: "/rooms/12", hash: "", search: "" }, all)).toMatchObject({ route: "/rooms/12", featureId: "rooms", title: { tr: "Derslikler" }, entity: { kind: "room", id: 12 } });
    expect(pageContextFor({ pathname: "/bookings", hash: "", search: "?display=room&room=7" }, all)).toMatchObject({ featureId: "bookings", entity: { kind: "room", id: 7 } });
    expect(pageContextFor({ pathname: "/approvals", hash: "", search: "?request=41" }, all)).toMatchObject({ featureId: "approvals", entity: { kind: "approval_request", id: 41 } });
    expect(pageContextFor({ pathname: "/approvals", hash: "", search: "?request=0" }, all)?.entity).toBeUndefined();
  });

  it("no chip for an unknown page, a page the person may not open, or a route over 200 characters", () => {
    expect(pageContextFor({ pathname: "/nowhere", hash: "", search: "" }, all)).toBeNull();
    expect(pageContextFor({ pathname: "/admin/users", hash: "", search: "" }, () => false)).toBeNull();
    expect(pageContextFor({ pathname: `/admin/users/${"x".repeat(200)}`, hash: "", search: "" }, all)).toBeNull();
  });

  it("the wire shape is the server's zod: route, kind and id only", () => {
    const ctx = pageContextFor({ pathname: "/rooms/12", hash: "", search: "" }, all)!;
    expect(toTurnContext(ctx)).toEqual({ route: "/rooms/12", entity_kind: "room", entity_id: 12 });
    expect(toTurnContext(pageContextFor({ pathname: "/reserve", hash: "", search: "" }, all)!)).toEqual({ route: "/reserve" });
    expect(TurnContext.safeParse({ route: "/x", entity_kind: "user", entity_id: 1 }).success).toBe(false);
    expect(TurnContext.safeParse({ route: "/x", entity_kind: "room", entity_id: 0 }).success).toBe(false);
    expect(TurnContext.safeParse({ route: "x".repeat(201) }).success).toBe(false);
    expect(TurnContext.safeParse({ route: "/x", text: "page text" }).success).toBe(false);
  });
});

async function ask(text: string) {
  const field = await screen.findByRole("textbox", { name: "Yardımcıya yazın" });
  fireEvent.change(field, { target: { value: text } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => expect(stream).toHaveBeenCalled());
}

describe("Bu sayfa chip in the sheet", () => {
  it("shows the page's title and sends the context while it is on", async () => {
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet());
    expect(await screen.findByTestId("helper-context-chip")).toHaveTextContent("Bu sayfa: Hızlı rezervasyon");
    await ask("bu sayfada ne yapabilirim?");
    expect(stream.mock.calls[0]![3]).toEqual({ context: { route: "/reserve" } });
  });

  it("one tap removes it: the focus goes to the composer and no context is sent", async () => {
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet());
    const remove = await screen.findByRole("button", { name: "Bu sayfayı soruya ekleme: Hızlı rezervasyon" });
    fireEvent.click(remove);
    expect(screen.queryByTestId("helper-context-chip")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Yardımcıya yazın" })));
    expect(screen.getByTestId("helper-context-live")).toHaveTextContent("Sayfa bilgisi soruya eklenmeyecek.");
    await ask("salon bul");
    expect(stream.mock.calls[0]![3]?.context).toBeUndefined();
  });

  it("a room page sends the room as the entity", async () => {
    pathname = "/rooms/12";
    perms = ["planning.view"];
    window.history.replaceState({}, "", "/rooms/12");
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet());
    expect(await screen.findByTestId("helper-context-chip")).toHaveTextContent("Bu sayfa: Derslikler");
    await ask("bu odada yarın boş saat var mı?");
    expect(stream.mock.calls[0]![3]).toEqual({ context: { route: "/rooms/12", entity_kind: "room", entity_id: 12 } });
  });

  it("no chip and no context on a page the index does not know", async () => {
    pathname = "/nowhere";
    window.history.replaceState({}, "", "/nowhere");
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet());
    await ask("merhaba");
    expect(screen.queryByTestId("helper-context-chip")).toBeNull();
    expect(stream.mock.calls[0]![3]?.context).toBeUndefined();
  });

  it("no chip in Rehber modu (index mode ignores the context)", async () => {
    vi.spyOn(helperApi, "status").mockResolvedValue(status({ mode: "index", reason: "not_routed", provider_kind: null }));
    renderHelper(<HelperSheet />);
    act(() => useHelperStore.getState().openSheet());
    await screen.findByTestId("helper-guide-input");
    expect(screen.queryByTestId("helper-context-chip")).toBeNull();
  });

  it("English", async () => {
    renderHelper(<HelperSheet />, { locale: "en" });
    act(() => useHelperStore.getState().openSheet());
    expect(await screen.findByTestId("helper-context-chip")).toHaveTextContent("This page: Quick reserve");
  });
});
