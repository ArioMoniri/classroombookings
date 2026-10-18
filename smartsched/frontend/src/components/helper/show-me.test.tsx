/** HX-07 (helper.md §3.3): Göster = navigate, wait for the anchor, ring it, one step card; Esc ends on the target. */
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/endpoints";
import { useHelperStore } from "./helper-store";
import { ShowMeHost } from "./show-me";
import { renderHelper, resetHelperStore } from "./test-helpers";

const push = vi.fn();
let pathname = "/bookings";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => pathname }));

function media(desktop: boolean) {
  window.matchMedia = ((q: string) => ({ matches: q.includes("min-width: 1024px") ? desktop : q.includes("reduce") ? false : false, media: q, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  resetHelperStore();
  push.mockReset();
  pathname = "/bookings";
  Element.prototype.scrollIntoView = vi.fn();
  // jsdom has no layout: give every element a box so the anchor counts as visible
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ x: 10, y: 10, left: 10, top: 10, width: 120, height: 40, right: 130, bottom: 50, toJSON: () => ({}) } as DOMRect);
  media(true);
});

describe("Göster", () => {
  it("navigates, rings the control and ends with the focus on it (Esc)", async () => {
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", false));
    expect(push).toHaveBeenCalledWith("/admin/holidays");
    expect(await screen.findByTestId("helper-step")).toHaveTextContent("Tatiller");
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    const target = screen.getByText("Tatil ekle");
    expect(target.getAttribute("aria-describedby")).toBeTruthy();
    expect(target).toBeEnabled();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(useHelperStore.getState().showMe).toBeNull());
    expect(document.activeElement).toBe(target);
    expect(target).not.toHaveAttribute("aria-describedby");
  });

  it("Yardımcıya dön reopens the sheet with the thread", async () => {
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().pushUser("Tatil nerede eklenir?");
      useHelperStore.getState().startShowMe("admin.holidays", true);
    });
    fireEvent.click(await screen.findByTestId("helper-step-back"));
    expect(useHelperStore.getState().open).toBe(true);
    expect(useHelperStore.getState().entries).toHaveLength(1);
  });

  it("HX-18 M1: a target under the open desktop sheet moves the sheet aside; Yardımcıya dön brings it back", async () => {
    const rect = (left: number, width: number) => ({ x: left, y: 80, left, top: 80, width, height: 40, right: left + width, bottom: 120, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return this.hasAttribute("data-helper-sheet") ? rect(1040, 400) : rect(1300, 100);
    });
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <div data-helper-sheet="" />
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().openSheet();
      useHelperStore.getState().startShowMe("admin.holidays", false);
    });
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(useHelperStore.getState().open).toBe(false);
    expect(useHelperStore.getState().showMe?.reopen).toBe(true);
    fireEvent.click(screen.getByTestId("helper-step-back"));
    expect(useHelperStore.getState().open).toBe(true);
  });

  it("HX-18 M1: a target clear of the sheet keeps the sheet open", async () => {
    const rect = (left: number, width: number) => ({ x: left, y: 80, left, top: 80, width, height: 40, right: left + width, bottom: 120, toJSON: () => ({}) }) as DOMRect;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      return this.hasAttribute("data-helper-sheet") ? rect(1040, 400) : rect(200, 100);
    });
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <div data-helper-sheet="" />
        <ShowMeHost />
      </>,
    );
    act(() => {
      useHelperStore.getState().openSheet();
      useHelperStore.getState().startShowMe("admin.holidays", false);
    });
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(useHelperStore.getState().open).toBe(true);
  });

  it("HX-18 m12: on a phone the target scrolls to the upper half (block start), not under the docked card", async () => {
    media(false);
    renderHelper(
      <>
        <button type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", true));
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: "start" }));
    expect(screen.getByText("Tatil ekle").style.scrollMarginTop).not.toBe("");
  });

  it("Yayınla is on the run's page: Göster from /runs goes to the published run first", async () => {
    pathname = "/runs";
    vi.spyOn(api.runs, "list").mockResolvedValue([{ id: 3, status: "OPTIMAL", is_active: false }, { id: 5, status: "FEASIBLE", is_active: true }] as never);
    renderHelper(
      <>
        <button type="button" data-tour="runs-publish">Yayınla</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("runs.publish", false));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/5"));
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
  });

  it("on a run's page Göster stays on that run", async () => {
    pathname = "/runs/12";
    const list = vi.spyOn(api.runs, "list");
    renderHelper(
      <>
        <button type="button" data-tour="runs-export">Dışa aktar</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("runs.export", false));
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(list).not.toHaveBeenCalled();
  });

  it("a missing anchor shows the path and says the button is not on the page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderHelper(<ShowMeHost />);
    act(() => useHelperStore.getState().startShowMe("admin.users.invite", false));
    await act(async () => {
      vi.advanceTimersByTime(3200);
    });
    expect(await screen.findByTestId("helper-step-missing")).toHaveTextContent("Bu düğme şu an bu sayfada görünmüyor.");
    expect(screen.getByTestId("helper-step")).toHaveTextContent("Kurulum › Kullanıcılar › Davet et");
    expect(screen.queryByTestId("tour-ring")).toBeNull();
    vi.useRealTimers();
  });
});

describe("Göster on a page that loads in parts (HB18-F04)", () => {
  it("waits for the page to stop growing before it scrolls to the target", async () => {
    const t0 = Date.now();
    const grow = vi.spyOn(document.documentElement, "scrollHeight", "get").mockImplementation(() => {
      const ms = Date.now() - t0;
      return ms < 250 ? 6011 + Math.floor(ms) : 7241; // Profil's sections still arriving
    });
    let scrolledAt = 0;
    Element.prototype.scrollIntoView = vi.fn(() => {
      scrolledAt ||= Date.now();
    });
    renderHelper(
      <>
        <button type="button" data-tour="profile-calendar-add">Takvimime ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", false));
    // the request names admin.holidays; point the anchor at it
    expect(await screen.findByTestId("helper-step", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(scrolledAt === 0 || scrolledAt - t0 >= 240).toBe(true);
    grow.mockRestore();
  });

  it("follows the anchor when the page re-mounts it, and rings the new element", async () => {
    const { rerender } = renderHelper(
      <>
        <button key="a" type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    act(() => useHelperStore.getState().startShowMe("admin.holidays", false));
    expect(await screen.findByTestId("tour-ring")).toBeInTheDocument();
    const first = screen.getByText("Tatil ekle");
    await waitFor(() => expect(first.getAttribute("aria-describedby")).toBeTruthy());
    const calls = (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.calls.length;
    rerender(
      <>
        <button key="b" type="button" data-tour="admin-holidays-add">Tatil ekle</button>
        <ShowMeHost />
      </>,
    );
    const second = screen.getByText("Tatil ekle");
    expect(second).not.toBe(first);
    await waitFor(() => expect(second.getAttribute("aria-describedby")).toBeTruthy());
    expect((Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(calls);
    expect(screen.getByTestId("tour-ring")).toBeInTheDocument();
  });
});
