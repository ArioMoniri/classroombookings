/** WG-07 hints: a strip only for an eligible hint on its page, "Anladım" = seen (persisted on the server), no hints when off, the "Yeni" badge, the nav popover keeps focus. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DESKTOP_MEDIA, PHONE_MEDIA, makeState, mockMedia, renderWelcome, resetWelcomeStore } from "../test-helpers";
import { WelcomePageSlot } from "../page-slot";
import { useWelcomeStore } from "../welcome-store";
import { FeatureHintPopover } from "./feature-hint";
import { NewBadge } from "./new-badge";

const nav = vi.hoisted(() => ({ pathname: "/admin/ai", push: vi.fn() }));
const api = vi.hoisted(() => ({ events: [] as unknown[] }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname, useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push: nav.push, replace: vi.fn() }) }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { body?: unknown } = {}) => {
      if (path === "/welcome/events") api.events.push(opts.body);
      if (path === "/auth/me") return { id: 1, permissions: [] };
      if (path === "/welcome") throw new real.HttpError(503, "down");
      return undefined;
    },
  };
});

const admin = makeState({ audiences: ["admin"], primary: "admin", hints: [{ key: "hint.admin_ai" }, { key: "hint.admin_ops" }] });

beforeEach(() => {
  resetWelcomeStore();
  mockMedia(DESKTOP_MEDIA);
  api.events = [];
  nav.pathname = "/admin/ai";
});

describe("hints", () => {
  it("the admin sees the /admin/ai strip (role=status, no focus move); 'Anladım' marks it seen and hides it", async () => {
    const before = document.activeElement;
    renderWelcome(<WelcomePageSlot />, { state: admin });
    const strip = screen.getByTestId("hint-admin_ai");
    expect(strip).toHaveAttribute("role", "status");
    expect(strip).toHaveTextContent("Yeni: Yapay zekâ ayarları.");
    expect(strip).toHaveTextContent("Tüm yenilikler");
    expect(document.activeElement).toBe(before);
    // on the feature's own page there is nothing to "try"
    expect(screen.queryByTestId("hint-try-admin_ai")).toBeNull();
    fireEvent.click(screen.getByTestId("hint-dismiss-admin_ai"));
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "hint.admin_ai", event: "seen" }));
    expect(screen.queryByTestId("hint-admin_ai")).toBeNull();
  });

  it("a staff account (no admin hint in its payload) never sees admin hints", () => {
    renderWelcome(<WelcomePageSlot />, { state: makeState({ audiences: ["staff"], primary: "staff", hints: [{ key: "hint.quick_reserve" }] }) });
    expect(screen.queryByTestId("hint-admin_ai")).toBeNull();
  });

  it("hints switched off: no strip and no badge", () => {
    const off = makeState({ ...admin, enabled: { sheet: true, tour: true, checklist: true, hints: false } });
    renderWelcome(
      <>
        <WelcomePageSlot />
        <NewBadge href="/admin/ai" />
      </>,
      { state: off },
    );
    expect(screen.queryByTestId("hint-admin_ai")).toBeNull();
    expect(screen.queryByTestId("new-badge-admin_ai")).toBeNull();
  });

  it("the 'Yeni' badge sits on the entry of an unseen hint", () => {
    renderWelcome(<NewBadge href="/admin/ops" />, { state: admin });
    expect(screen.getByTestId("new-badge-admin_ops")).toHaveTextContent("Yeni");
  });

  it("phone: the quick-reserve hint is an inline card at the top of /bookings with 'Dene'", async () => {
    mockMedia(PHONE_MEDIA);
    nav.pathname = "/bookings";
    renderWelcome(<WelcomePageSlot />, { state: makeState({ audiences: ["staff"], primary: "staff", hints: [{ key: "hint.quick_reserve" }] }) });
    fireEvent.click(screen.getByTestId("hint-try-quick_reserve"));
    expect(nav.push).toHaveBeenCalledWith("/reserve");
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "hint.quick_reserve", event: "seen" }));
  });

  it("desktop nav popover: non-modal, keeps focus, Esc = Anladım", async () => {
    nav.pathname = "/bookings";
    const entry = document.createElement("a");
    entry.href = "/reserve";
    entry.textContent = "Hızlı rezervasyon";
    entry.setAttribute("data-tour", "nav-reserve");
    entry.getBoundingClientRect = () => ({ x: 0, y: 0, top: 0, left: 0, right: 200, bottom: 40, width: 200, height: 40, toJSON: () => ({}) }) as DOMRect;
    document.body.appendChild(entry);
    const keep = document.createElement("input");
    document.body.appendChild(keep);
    keep.focus();
    act(() => useWelcomeStore.setState({ autoHint: "hint.quick_reserve" }));
    renderWelcome(<FeatureHintPopover />, { state: makeState({ audiences: ["staff"], primary: "staff", hints: [{ key: "hint.quick_reserve" }] }) });
    const pop = await screen.findByTestId("hint-quick_reserve", {}, { timeout: 2000 });
    expect(pop).toHaveAttribute("role", "dialog");
    expect(pop).toHaveAttribute("aria-modal", "false");
    expect(document.activeElement).toBe(keep);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(api.events).toContainEqual({ guide_key: "hint.quick_reserve", event: "seen" }));
    await waitFor(() => expect(screen.queryByTestId("hint-quick_reserve")).toBeNull());
    entry.remove();
    keep.remove();
  });
});
